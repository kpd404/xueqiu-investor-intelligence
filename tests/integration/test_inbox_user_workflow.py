from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from contracts import FeedState
from tests.integration.test_effective_asset_context import _ready
from tests.integration.test_effective_cross_feed_query import _snapshot
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


@pytest.fixture
def inbox_api(db_session_factory, monkeypatch):
    from backend.app.api.routes.inbox import get_inbox_service
    from intelligence.product.inbox import InboxService

    monkeypatch.setitem(
        app.dependency_overrides, get_inbox_service, lambda: InboxService(db_session_factory)
    )
    with TestClient(app) as client:
        yield client


def test_default_explicit_operations_duplicates_filters_and_source_protection(
    db_session_factory, production_policies, inbox_api
):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    response = inbox_api.get("/api/inbox?filter=UNREAD&limit=1")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["user_state"] == {"read": False, "processed": False}
    endpoint = "/api/inbox/" + str(feed.id) + "/user-state"
    for body in [{"read": True}, {"processed": True}, {"read": False}, {"processed": False}]:
        one = inbox_api.patch(endpoint, json=body)
        assert one.status_code == 200, one.text
        assert inbox_api.patch(endpoint, json=body).json() == one.json()
    inbox_api.patch(endpoint, json={"read": True})
    assert inbox_api.get("/api/inbox?filter=UNREAD").json()["total"] == 0
    assert inbox_api.get("/api/inbox?filter=PENDING").json()["total"] == 1
    inbox_api.patch(endpoint, json={"processed": True})
    assert inbox_api.get("/api/inbox?filter=PENDING").json()["total"] == 0
    assert inbox_api.get("/api/inbox").json()["total"] == 1
    assert (
        inbox_api.patch(
            "/api/inbox/" + str(uuid4()) + "/user-state", json={"read": True}
        ).status_code
        == 404
    )
    assert inbox_api.patch(endpoint, json={}).status_code == 422
    assert inbox_api.patch(endpoint, json={"read": "true"}).status_code == 422
    after = _snapshot(db_session_factory)
    assert {k: v for k, v in after.items() if k != "inbox_user_states"} == {
        k: v for k, v in before.items() if k != "inbox_user_states"
    }


def test_user_state_persists_projection_rerun_and_does_not_restore_invalid_feed(
    db_session_factory, production_policies, inbox_api
):
    from database.models import Signal

    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    endpoint = "/api/inbox/" + str(feed.id) + "/user-state"
    assert inbox_api.patch(endpoint, json={"read": True, "processed": True}).status_code == 200
    _ready(db_session_factory)
    assert inbox_api.get("/api/inbox").json()["items"][0]["user_state"] == {
        "read": True,
        "processed": True,
    }
    with db_session_factory() as s:
        from sqlalchemy import select

        for signal in s.scalars(select(Signal)):
            signal.state = "SUPERSEDED"
        s.commit()
    assert inbox_api.get("/api/inbox").json()["total"] == 0


def test_pagination_state_boundaries_candidate_independence_and_restart(
    db_session_factory, production_policies, inbox_api
):
    from sqlalchemy import select

    from database.models import InboxUserState, IntelligenceFeedItem
    from intelligence.product.inbox import InboxService
    from intelligence.product.research import AddResearch, EditResearch, ResearchService
    from tests.integration.test_research_candidates import body_for

    pairs = [
        _history(db_session_factory, production_policies, state=FeedState.NEW) for _ in range(3)
    ]
    _ready(db_session_factory)
    service = InboxService(db_session_factory)
    result = service.list(limit=1, state=FeedState.ACTIVE)
    assert result["total"] == 3 and result["has_more"]
    next_page = service.list(limit=1, offset=1, state=FeedState.ACTIVE)
    assert next_page["items"][0]["id"] != result["items"][0]["id"] and next_page["total"] == 3
    assert not service.list(limit=1, offset=2, state=FeedState.ACTIVE)["has_more"]
    source, feed = pairs[0]
    candidate = ResearchService(db_session_factory).add(
        AddResearch(**body_for(db_session_factory, source, feed))
    )
    ResearchService(db_session_factory).edit(
        __import__("uuid").UUID(candidate["id"]), EditResearch(status="ARCHIVED")
    )
    with db_session_factory() as s:
        assert not s.scalars(select(InboxUserState)).all()
    inbox_api.patch(
        "/api/inbox/" + str(feed.id) + "/user-state", json={"read": True, "processed": True}
    )
    restarted = InboxService(db_session_factory)
    assert next(v for v in restarted.list()["items"] if v["id"] == str(feed.id))["user_state"] == {
        "read": True,
        "processed": True,
    }
    with db_session_factory() as s:
        saved = s.get(IntelligenceFeedItem, feed.id)
        saved.state = "STALE"
        s.commit()
    inbox_api.patch("/api/inbox/" + str(feed.id) + "/user-state", json={"read": False})
    assert inbox_api.get("/api/inbox").json()["total"] == 2
    with db_session_factory() as s:
        assert s.get(IntelligenceFeedItem, feed.id).state == "STALE"
    with db_session_factory() as s:
        saved = s.get(IntelligenceFeedItem, feed.id)
        saved.state = "RESOLVED"
        s.commit()
    inbox_api.patch("/api/inbox/" + str(feed.id) + "/user-state", json={"processed": False})
    with db_session_factory() as s:
        assert s.get(IntelligenceFeedItem, feed.id).state == "RESOLVED"


def test_transaction_failure_rolls_back(db_session_factory, production_policies, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from intelligence.product.inbox import EditInboxState, InboxService

    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)

    def reject(*args):
        raise RuntimeError("isolated injected commit failure")

    event.listen(Session, "before_commit", reject)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            InboxService(db_session_factory).edit(feed.id, EditInboxState(read=True))
    finally:
        event.remove(Session, "before_commit", reject)
    assert _snapshot(db_session_factory) == before
