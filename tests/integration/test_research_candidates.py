"""User writes in isolated databases; real evidence selection and HTTP."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.api.routes.research_candidates import get_research_service
from backend.app.main import app
from contracts import EventAnalysisStatus, FeedState, SignalState
from database.models import Asset, IntelligenceFeedItem, Investor, ResearchCandidate, Signal
from intelligence.product.evidence import EvidenceReadingService
from intelligence.product.research import ResearchService
from tests.integration.test_effective_asset_context import _ready
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


@pytest.fixture
def research_api(db_session_factory, monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides, get_research_service, lambda: ResearchService(db_session_factory)
    )
    with TestClient(app) as client:
        yield client


def body_for(factory, source, feed):
    view = EvidenceReadingService(factory).read(source.asset_id, feed_id=feed.id)
    group = view.groups[0]
    return dict(
        asset_id=str(source.asset_id),
        submission_id=str(uuid4()),
        feed_id=str(feed.id),
        selections=[dict(event_id=str(group.event_id), signal_id=str(group.signal_id))],
        reason="用户希望核实",
        questions="催化剂有原文支持吗？",
        notes="用户笔记",
    )


def test_real_relationship_duplicate_edit_archive_restore_and_source_protection(
    db_session_factory, production_policies, research_api
):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    body = body_for(db_session_factory, source, feed)
    add = research_api.post("/api/research-candidates", json=body)
    assert add.status_code == 200, add.text
    row = add.json()
    endpoint = "/api/research-candidates/" + row["id"]
    assert row["status"] == "TODO" and len(row["references"]) == 1
    assert research_api.post("/api/research-candidates", json=body).json() == row
    body["submission_id"] = str(uuid4())
    body["reason"] = "不应覆盖原因"
    again = research_api.post("/api/research-candidates", json=body).json()
    assert (
        again["id"] == row["id"]
        and again["reason"] == row["reason"]
        and len(again["references"]) == 1
    )
    # Product and Inbox saving the same actual evidence must not duplicate it.
    product_payload = dict(body, feed_id=None, submission_id=str(uuid4()))
    product_result = research_api.post("/api/research-candidates", json=product_payload)
    assert product_result.status_code == 200, product_result.text
    assert len(product_result.json()["references"]) == 1
    assert product_result.json()["references"][0]["feed_id"] == str(feed.id)
    edited = research_api.patch(
        endpoint, json=dict(questions="验证盈利依据", notes="更正用户判断", status="RESEARCHING")
    ).json()
    assert edited["created_at"] == row["created_at"] and edited["questions"] == "验证盈利依据"
    assert research_api.patch(endpoint, json={"status": "ARCHIVED"}).json()["status"] == "ARCHIVED"
    # Replayed submission never automatically restores archived record.
    assert research_api.post("/api/research-candidates", json=body).json()["status"] == "ARCHIVED"
    assert research_api.patch(endpoint, json={"status": "TODO"}).json()["status"] == "TODO"
    assert research_api.get(endpoint).json()["sources"][0]["status"] == "CURRENT"
    after = _snapshot(db_session_factory)
    assert {k: v for k, v in after.items() if k != "research_candidates"} == {
        k: v for k, v in before.items() if k != "research_candidates"
    }


@pytest.mark.parametrize("field", ["asset_id", "feed_id", "event_id", "signal_id"])
def test_mismatched_source_rejected(db_session_factory, production_policies, research_api, field):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    body = body_for(db_session_factory, source, feed)
    if field in ["event_id", "signal_id"]:
        body["selections"][0][field] = str(uuid4())
    else:
        body[field] = str(uuid4())
    before = _snapshot(db_session_factory)
    result = research_api.post("/api/research-candidates", json=body)
    assert result.status_code in [404, 409], result.text
    with db_session_factory() as s:
        assert not s.scalars(select(ResearchCandidate)).all()
    assert _snapshot(db_session_factory) == before


def test_late_predecessor_retains_exact_historical_content_and_user_record(
    db_session_factory, production_policies, research_api
):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    body = body_for(db_session_factory, source, feed)
    row = research_api.post("/api/research-candidates", json=body).json()
    with db_session_factory() as s:
        _add_opinion(
            s,
            s.get(Investor, source.investor_id),
            s.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            FACT_TIME - timedelta(hours=12),
            EventAnalysisStatus.SUCCESS,
        )
        s.commit()
    before = _snapshot(db_session_factory)
    result = research_api.get("/api/research-candidates/" + row["id"])
    assert result.status_code == 200, result.text
    saved = result.json()
    historical = saved["sources"][0]
    assert historical["status"] == "HISTORICAL"
    assert {o["opinion_id"] for o in historical["evidence"]["groups"][0]["opinions"]} == set(
        row["references"][0]["opinion_ids"]
    )
    assert historical["evidence"]["groups"][0]["basis"] == "HISTORICAL_REFERENCE"
    assert saved["notes"] == row["notes"] and saved["references"] == row["references"]
    assert _snapshot(db_session_factory) == before


def test_api_errors_and_archived_restore_conflict(
    db_session_factory, production_policies, research_api
):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    body = body_for(db_session_factory, source, feed)
    first = research_api.post("/api/research-candidates", json=body).json()
    url = "/api/research-candidates/" + first["id"]
    research_api.patch(url, json={"status": "ARCHIVED"})
    body["submission_id"] = str(uuid4())
    second = research_api.post("/api/research-candidates", json=body).json()
    assert second["id"] != first["id"]
    assert research_api.patch(url, json={"status": "TODO"}).status_code == 409
    assert research_api.patch(url, json={"status": "INVALID"}).status_code == 422
    assert research_api.patch(url, json={"notes": None}).status_code == 409
    assert research_api.get("/api/research-candidates/" + str(uuid4())).status_code == 404
    assert len(research_api.get("/api/research-candidates").json()["items"]) == 2


def test_replay_different_payload_and_partial_invalid_selection_are_rejected(
    db_session_factory, production_policies, research_api
):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    body = body_for(db_session_factory, source, feed)
    invalid = dict(
        body, selections=[*body["selections"], dict(event_id=str(uuid4()), signal_id=str(uuid4()))]
    )
    assert research_api.post("/api/research-candidates", json=invalid).status_code == 409
    assert research_api.get("/api/research-candidates").json()["items"] == []
    assert research_api.post("/api/research-candidates", json=body).status_code == 200
    body["selections"][0]["signal_id"] = str(uuid4())
    assert research_api.post("/api/research-candidates", json=body).status_code == 409


def test_expired_feed_preserves_record_with_historical_reading(
    db_session_factory, production_policies, research_api
):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    body = body_for(db_session_factory, source, feed)
    row = research_api.post("/api/research-candidates", json=body).json()
    with db_session_factory() as session:
        session.get(IntelligenceFeedItem, feed.id).state = "STALE"
        session.commit()
    before = _snapshot(db_session_factory)
    saved = research_api.get("/api/research-candidates/" + row["id"]).json()
    assert saved["sources"][0]["status"] == "HISTORICAL"
    assert saved["status"] == "TODO" and saved["references"] == row["references"]
    assert _snapshot(db_session_factory) == before


def test_missing_saved_source_does_not_delete_or_hide_user_record(
    db_session_factory, production_policies, research_api
):
    from sqlalchemy import delete

    from database.models import Opinion

    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    row = research_api.post(
        "/api/research-candidates", json=body_for(db_session_factory, source, feed)
    ).json()
    with db_session_factory() as session:
        # Deliberately broken isolated source fixture; never run against business data.
        session.execute(delete(Opinion).where(Opinion.id == source.current_opinion_id))
        session.commit()
    before = _snapshot(db_session_factory)
    result = research_api.get("/api/research-candidates/" + row["id"])
    assert result.status_code == 200, result.text
    saved = result.json()
    assert (
        saved["sources"][0]["status"] == "UNAVAILABLE" and saved["sources"][0]["evidence"] is None
    )
    assert saved["notes"] == row["notes"] and saved["references"] == row["references"]
    assert _snapshot(db_session_factory) == before


def test_same_asset_merges_additional_source_without_overwriting_notes(
    db_session_factory, production_policies, research_api
):
    from tests.integration.test_thesis_change_feed import _second_material_change

    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    payload = body_for(db_session_factory, source, feed)
    first = research_api.post("/api/research-candidates", json=payload).json()
    later = _second_material_change(db_session_factory, production_policies, source)
    # Effective history is valid without borrowing an unrelated Event association.
    payload = dict(
        asset_id=str(source.asset_id),
        submission_id=str(uuid4()),
        selections=[dict(thesis_change_id=str(later.id))],
        notes="must not overwrite",
    )
    response = research_api.post("/api/research-candidates", json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["id"] == first["id"] and saved["created_at"] == first["created_at"]
    assert saved["notes"] == first["notes"] and len(saved["references"]) == 2


@pytest.mark.parametrize("kind", ["CROSS_INVESTOR_ALIGNMENT", "CONSENSUS_CHANGE"])
def test_cross_voters_attention_history_and_exact_associations(
    db_session_factory, production_policies, research_api, feed_api, kind
):
    from contracts import SignalType
    from tests.integration.test_effective_cross_feed_query import (
        test_attention_only_contributor_is_not_a_direction_voter,
    )

    test_attention_only_contributor_is_not_a_direction_voter(
        db_session_factory, production_policies, feed_api, SignalType(kind)
    )
    _ready(db_session_factory)
    with db_session_factory() as session:
        signal = session.scalar(select(Signal))
    view = EvidenceReadingService(db_session_factory).read(signal.asset_id)
    g = view.groups[0]
    assert len(g.direction_voter_ids) == 3 and len(g.attention_only_investor_ids) == 1
    payload = dict(
        asset_id=str(signal.asset_id),
        submission_id=str(uuid4()),
        selections=[dict(event_id=str(g.event_id), signal_id=str(g.signal_id))],
    )
    row = research_api.post("/api/research-candidates", json=payload).json()
    assert "id" in row, row
    assert row["references"][0]["source_id"] == str(g.source_id)
    with db_session_factory() as session:
        session.get(Signal, g.signal_id).state = SignalState.SUPERSEDED
        session.commit()
    before = _snapshot(db_session_factory)
    saved = research_api.get("/api/research-candidates/" + row["id"]).json()
    assert saved["sources"][0]["status"] == "HISTORICAL"
    history = saved["sources"][0]["evidence"]["groups"][0]
    assert len(history["direction_voter_ids"]) == len(history["opinions"]) == 3
    assert sum(a["attention_only"] for a in history["attention"]) == 1
    assert _snapshot(db_session_factory) == before
