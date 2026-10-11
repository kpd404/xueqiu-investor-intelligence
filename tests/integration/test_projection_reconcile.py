"""Bounded historical projection coordination with real isolated source readers."""

import pytest
from sqlalchemy import delete

from contracts import FeedState
from database.models import IntelligenceEventPriority, IntelligenceFeedItem, Signal
from operations.projection_reconcile import ProjectionReconciler
from tests.integration.test_cross_materialization_consistency import _mixed
from tests.integration.test_cross_signal_source_chains import CROSS
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history, _protected


@pytest.mark.parametrize("kind", ("thesis", *CROSS))
@pytest.mark.parametrize("state", (FeedState.ACTIVE, FeedState.STALE, FeedState.RESOLVED))
def test_bounded_plan_apply(db_session_factory, production_policies, kind, state):
    factory = db_session_factory
    _, feed = (
        _history(factory, production_policies, state=state)
        if kind == "thesis"
        else _mixed(factory, production_policies, kind, state)
    )
    before = _snapshot(factory)
    protected = _protected(factory)
    service = ProjectionReconciler(factory)
    plan = service.prepare(priority_id=feed.priority_id)
    assert _snapshot(factory) == before
    assert plan["items"][0]["expected_priority"]["evidence_count"] == 1
    assert plan["items"][0]["expected_feed"]["context"]["signal_count"] == 1
    service.apply(plan)
    assert _protected(factory) == protected
    with factory() as session:
        actual = session.get(IntelligenceFeedItem, feed.id)
        assert actual.state == state.value
        assert actual.created_at.replace(tzinfo=feed.created_at.tzinfo) == feed.created_at
        assert actual.context.get("_thesis_lifecycle") == feed.context.get("_thesis_lifecycle")
    stable = _snapshot(factory)
    assert not service.prepare(priority_id=feed.priority_id)["items"][0]["changes"]
    service.apply(service.prepare(priority_id=feed.priority_id))
    assert _snapshot(factory) == stable


def test_stale_plan_rollback_and_boundaries(db_session_factory, production_policies, monkeypatch):
    factory = db_session_factory
    _, feed = _history(factory, production_policies)
    _, other = _history(factory, production_policies)
    service = ProjectionReconciler(factory)
    plan = service.prepare(priority_id=feed.priority_id)
    with factory() as session:
        session.get(IntelligenceEventPriority, feed.priority_id).evidence_count = 3
        session.commit()
    with pytest.raises(ValueError, match="stale"):
        service.apply(plan)
    plan = service.prepare(priority_id=feed.priority_id)
    before = _snapshot(factory)
    from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository

    original = IntelligenceFeedItemRepository.add_if_absent

    def fail(*args, **kwargs):
        raise RuntimeError("injected Feed failure")

    monkeypatch.setattr(IntelligenceFeedItemRepository, "add_if_absent", fail)
    with pytest.raises(RuntimeError, match="injected"):
        service.apply(plan)
    assert _snapshot(factory) == before
    monkeypatch.setattr(IntelligenceFeedItemRepository, "add_if_absent", original)
    service.apply(plan)
    with factory() as session:
        assert session.get(IntelligenceEventPriority, other.priority_id).evidence_count == 2


def test_missing_entity_is_not_created(db_session_factory, production_policies):
    factory = db_session_factory
    _, feed = _history(factory, production_policies)
    with factory() as session:
        session.execute(delete(IntelligenceFeedItem).where(IntelligenceFeedItem.id == feed.id))
        session.commit()
    service = ProjectionReconciler(factory)
    before = _snapshot(factory)
    plan = service.prepare(priority_id=feed.priority_id)
    assert plan["items"][0]["status"] == "ANOMALY"
    with pytest.raises(ValueError, match="cannot"):
        service.apply(plan)
    assert _snapshot(factory) == before


def test_all_invalid_is_skipped(db_session_factory, production_policies):
    factory = db_session_factory
    _, feed = _history(factory, production_policies)
    with factory() as session:
        for signal in session.query(Signal):
            signal.state = "SUPERSEDED"
        session.commit()
    service = ProjectionReconciler(factory)
    before = _snapshot(factory)
    plan = service.prepare(priority_id=feed.priority_id)
    assert plan["items"][0]["status"] == "SKIPPED"
    service.apply(plan)
    assert _snapshot(factory) == before


@pytest.mark.parametrize("change", ("source", "feed", "late_input"))
def test_source_or_projection_change_rejects_plan(db_session_factory, production_policies, change):
    factory = db_session_factory
    _, feed = _history(factory, production_policies)
    service = ProjectionReconciler(factory)
    plan = service.prepare(priority_id=feed.priority_id)
    if change == "late_input":
        _history(factory, production_policies)
    else:
        with factory() as session:
            if change == "source":
                session.query(Signal).first().state = "SUPERSEDED"
            else:
                session.get(IntelligenceFeedItem, feed.id).title = "changed projection"
            session.commit()
    before = _snapshot(factory)
    with pytest.raises(ValueError, match="stale"):
        service.apply(plan)
    assert _snapshot(factory) == before


def test_explicit_scope_and_missing_priority(db_session_factory):
    from uuid import uuid4

    service = ProjectionReconciler(db_session_factory)
    with pytest.raises(ValueError, match="Exactly"):
        service.prepare()
    with pytest.raises(LookupError, match="No existing"):
        service.prepare(priority_id=uuid4())


def test_asset_scope_reuses_batch_and_reports_all_dependencies(
    db_session_factory, production_policies, record_property
):
    from sqlalchemy import event as sql_event

    factory = db_session_factory
    _, feed = _history(factory, production_policies)
    statements = []
    engine = factory.kw["bind"]

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    sql_event.listen(engine, "before_cursor_execute", count)
    try:
        plan = ProjectionReconciler(factory).prepare(asset_id=feed.asset_id)
    finally:
        sql_event.remove(engine, "before_cursor_execute", count)
    assert plan["items"][0]["priority_id"] == str(feed.priority_id)
    assert len(plan["items"][0]["dependencies"]) == 2
    assert all(d["source_id"] for d in plan["items"][0]["dependencies"])
    record_property("select_count", len(statements))
    assert len(statements) < 110


@pytest.mark.parametrize("kind", ("thesis", *CROSS))
def test_reconcile_discovery_http_without_provider(
    db_session_factory, production_policies, monkeypatch, kind
):
    import httpx
    from fastapi.testclient import TestClient

    from backend.app.api.dependencies import get_intelligence_discovery_service
    from backend.app.main import app
    from intelligence.discovery.service import IntelligenceDiscoveryService

    factory = db_session_factory
    _, feed = (
        _history(factory, production_policies)
        if kind == "thesis"
        else _mixed(factory, production_policies, kind)
    )
    service = ProjectionReconciler(factory)

    def no_network(*args, **kwargs):
        raise AssertionError("Provider/network forbidden")

    with monkeypatch.context() as guard:
        guard.setattr(httpx.Client, "send", no_network)
        guard.setattr(httpx.AsyncClient, "send", no_network)
        plan = service.prepare(priority_id=feed.priority_id)
        service.apply(plan)
    discovery = IntelligenceDiscoveryService.from_production(factory)
    monkeypatch.setitem(
        app.dependency_overrides, get_intelligence_discovery_service, lambda: discovery
    )
    before = _snapshot(factory)
    with TestClient(app) as client:
        result = client.get("/api/intelligence/discovery")
        assert result.status_code == 200
        assert result.json()["items"][0]["activity_summary"]["signal_count"] == 1
    assert _snapshot(factory) == before


def test_cross_batch_shared_scope_query_count(
    db_session_factory, production_policies, record_property
):
    from sqlalchemy import event as sql_event

    from tests.integration.test_cross_signal_source_chains import _legacy
    from tests.integration.test_effective_cross_feed_query import _historical_feed

    factory = db_session_factory
    chain, feed = _mixed(factory, production_policies, CROSS[0])
    engine = factory.kw["bind"]
    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    def read():
        statements.clear()
        sql_event.listen(engine, "before_cursor_execute", count)
        try:
            return ProjectionReconciler(factory).prepare(asset_id=feed.asset_id)
        finally:
            sql_event.remove(engine, "before_cursor_execute", count)

    first = read()
    first_count = len(statements)
    _historical_feed(factory, feed.asset_id, [_legacy(factory, chain, CROSS[1])], CROSS[1])
    second = read()
    second_count = len(statements)
    assert len(first["items"]) == 1 and len(second["items"]) == 2
    assert all(i["expected_priority"]["evidence_count"] == 1 for i in second["items"])
    assert second_count == first_count
    record_property("one_event_selects", first_count)
    record_property("two_events_shared_scope_selects", second_count)
