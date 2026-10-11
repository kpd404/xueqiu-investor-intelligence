"""Explicit mixed whitelist coordination, without source mocks or providers."""

import pytest
from sqlalchemy import select

from contracts import FeedState
from database.models import IntelligenceFeedItem, Signal
from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository
from operations.projection_reconcile import ProjectionReconciler
from tests.integration.test_cross_materialization_consistency import _mixed
from tests.integration.test_cross_signal_source_chains import CROSS, _legacy
from tests.integration.test_effective_cross_feed_query import _historical_feed
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history, _protected


def _batch(factory, policies):
    _, thesis = _history(factory, policies, state=FeedState.STALE)
    chain, cross = _mixed(factory, policies, CROSS[0], FeedState.RESOLVED)
    consensus = _historical_feed(
        factory, cross.asset_id, [_legacy(factory, chain, CROSS[1])], CROSS[1]
    )
    _, outside = _history(factory, policies)
    return (thesis, cross, consensus), outside


def test_mixed_batch_is_explicit_atomic_and_idempotent(db_session_factory, production_policies):
    factory = db_session_factory
    feeds, outside = _batch(factory, production_policies)
    ids = tuple(f.priority_id for f in feeds)
    service = ProjectionReconciler(factory)
    before = _snapshot(factory)
    protected = _protected(factory)
    plan = service.prepare(priority_ids=ids)
    assert _snapshot(factory) == before
    assert set(plan["scope"]["priority_ids"]) == {str(i) for i in ids}
    assert len(plan["items"]) == 3
    service.apply(plan)
    assert _protected(factory) == protected
    after = _snapshot(factory)
    for table in ("intelligence_event_priorities", "intelligence_feed_items"):
        assert [r for r in before[table] if r["id"] not in {*ids, *(f.id for f in feeds)}] == [
            r for r in after[table] if r["id"] not in {*ids, *(f.id for f in feeds)}
        ]
    with factory() as session:
        for f in feeds:
            row = session.get(IntelligenceFeedItem, f.id)
            assert row.state == f.state.value
            assert row.context.get("_thesis_lifecycle") == f.context.get("_thesis_lifecycle")
    again = service.prepare(priority_ids=ids)
    assert all(i["status"] == "CONSISTENT" and not i["changes"] for i in again["items"])
    service.apply(again)
    assert _snapshot(factory) == after


def test_mid_batch_failure_rolls_back_all_rows(
    db_session_factory, production_policies, monkeypatch
):
    factory = db_session_factory
    feeds, _ = _batch(factory, production_policies)
    service = ProjectionReconciler(factory)
    plan = service.prepare(priority_ids=[f.priority_id for f in feeds])
    before = _snapshot(factory)
    original = IntelligenceFeedItemRepository.add_if_absent
    calls = []

    def fail_second(self, command):
        calls.append(command.priority_id)
        if len(calls) == 2:
            raise RuntimeError("mid-batch Feed failure")
        return original(self, command)

    monkeypatch.setattr(IntelligenceFeedItemRepository, "add_if_absent", fail_second)
    with pytest.raises(RuntimeError, match="mid-batch"):
        service.apply(plan)
    assert len(calls) == 2 and _snapshot(factory) == before


def test_consistent_and_invalid_batch_members_are_not_written(
    db_session_factory, production_policies, monkeypatch
):
    factory = db_session_factory
    _, valid = _history(factory, production_policies)
    service = ProjectionReconciler(factory)
    service.apply(service.prepare(priority_id=valid.priority_id))
    _, invalid = _history(factory, production_policies)
    with factory() as session:
        for signal in session.scalars(select(Signal).where(Signal.asset_id == invalid.asset_id)):
            signal.state = "SUPERSEDED"
        session.commit()
    plan = service.prepare(priority_ids=[valid.priority_id, invalid.priority_id])
    assert {i["status"] for i in plan["items"]} == {"CONSISTENT", "SKIPPED"}
    before = _snapshot(factory)

    def forbidden(*args, **kwargs):
        raise AssertionError("Skipped projection writer invoked")

    monkeypatch.setattr(IntelligenceFeedItemRepository, "add_if_absent", forbidden)
    service.apply(plan)
    assert _snapshot(factory) == before


@pytest.mark.parametrize("change", ("source", "target"))
def test_batch_stale_plan_rejected(db_session_factory, production_policies, change):
    factory = db_session_factory
    feeds, _ = _batch(factory, production_policies)
    service = ProjectionReconciler(factory)
    plan = service.prepare(priority_ids=[f.priority_id for f in feeds])
    with factory() as session:
        if change == "source":
            session.scalars(select(Signal)).first().state = "SUPERSEDED"
        else:
            session.get(IntelligenceFeedItem, feeds[-1].id).title = "changed"
        session.commit()
    before = _snapshot(factory)
    with pytest.raises(ValueError, match="stale"):
        service.apply(plan)
    assert _snapshot(factory) == before


def test_explicit_ids_missing_and_duplicate_are_not_silently_lost(
    db_session_factory, production_policies
):
    from uuid import uuid4

    _, feed = _history(db_session_factory, production_policies)
    service = ProjectionReconciler(db_session_factory)
    with pytest.raises(ValueError, match="unique"):
        service.prepare(priority_ids=[feed.priority_id] * 2)
    with pytest.raises(ValueError):
        service.prepare(priority_ids=[])
    plan = service.prepare(priority_ids=[feed.priority_id, uuid4()])
    assert len(plan["items"]) == 2 and any(i["status"] == "ANOMALY" for i in plan["items"])
    before = _snapshot(db_session_factory)
    with pytest.raises(ValueError, match="cannot"):
        service.apply(plan)
    assert _snapshot(db_session_factory) == before


def test_one_batch_reuses_sources_and_fingerprint_reads(
    db_session_factory, production_policies, monkeypatch
):
    from signal_engine.repository import FeedCrossInvestorSignalReader

    factory = db_session_factory
    feeds, _ = _batch(factory, production_policies)
    original = FeedCrossInvestorSignalReader.group_by_events
    calls = []
    from sqlalchemy import event as sql_event

    from database.base import Base

    engine = factory.kw["bind"]

    def normalize(value):
        return " ".join(str(value).split())

    expected = {
        normalize(select(t).compile(dialect=engine.dialect)): t.name
        for t in Base.metadata.sorted_tables
        if t.name not in {"intelligence_event_priorities", "intelligence_feed_items"}
    }
    fingerprint_reads = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if normalize(statement) in expected:
            fingerprint_reads.append(expected[normalize(statement)])

    def track(self, events, links, signals):
        calls.append(tuple(e.id for e in events))
        return original(self, events, links, signals)

    monkeypatch.setattr(FeedCrossInvestorSignalReader, "group_by_events", track)
    sql_event.listen(engine, "before_cursor_execute", count)
    try:
        plan = ProjectionReconciler(factory).prepare(priority_ids=[f.priority_id for f in feeds])
    finally:
        sql_event.remove(engine, "before_cursor_execute", count)
    assert len(calls) == 1 and len(calls[0]) == 2
    assert all(i["effective_evidence"] for i in plan["items"])
    assert all(len(i["effective_investor_ids"]) >= 1 for i in plan["items"])
    from collections import Counter

    assert Counter(fingerprint_reads) == Counter(expected.values())


def test_changed_code_rejects_batch_plan(db_session_factory, production_policies, monkeypatch):
    import operations.projection_reconcile as module

    feeds, _ = _batch(db_session_factory, production_policies)
    service = ProjectionReconciler(db_session_factory)
    plan = service.prepare(priority_ids=[f.priority_id for f in feeds])
    before = _snapshot(db_session_factory)
    monkeypatch.setattr(module, "_code_identity", lambda: {"head": "changed"})
    with pytest.raises(ValueError, match="stale"):
        service.apply(plan)
    assert _snapshot(db_session_factory) == before


def test_batch_zero_network_calls(db_session_factory, production_policies, monkeypatch):
    import httpx

    feeds, _ = _batch(db_session_factory, production_policies)

    def forbidden(*args, **kwargs):
        raise AssertionError("Network/provider forbidden")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    service = ProjectionReconciler(db_session_factory)
    service.apply(service.prepare(priority_ids=[f.priority_id for f in feeds]))
