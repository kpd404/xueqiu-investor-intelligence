"""Legacy projection reruns through real services; writes stay in isolated SQLite."""

from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy import event as sqlalchemy_event

from contracts import (
    EventAnalysisStatus,
    FeedState,
    IntelligenceEventPriorityCreate,
    IntelligenceEventType,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    ThesisChangeType,
)
from database.models import (
    Asset,
    IntelligenceEvent,
    IntelligenceEventPriority,
    IntelligenceFeedItem,
    Investor,
)
from database.repositories.intelligence_event_priorities import IntelligenceEventPriorityRepository
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from tests.integration import test_thesis_change_feed as feed_fixtures
from tests.integration import test_thesis_change_signals as signal_fixtures
from tests.integration.test_effective_thesis_feed_query import _get, _legacy_feed, _snapshot
from tests.integration.test_effective_thesis_signals import _persist_signal, _shared_asset_change
from tests.integration.test_thesis_change_feed import _second_material_change
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion, _seed_change

production_policies = signal_fixtures.production_policies
feed_api = feed_fixtures.feed_api


def _protected(factory):
    return {
        name: rows
        for name, rows in _snapshot(factory).items()
        if name not in {"intelligence_event_priorities", "intelligence_feed_items"}
    }


def _history(factory, policies, *, state=FeedState.ACTIVE):
    valid = _seed_change(factory, policies, ThesisChangeType.THESIS_CHANGED)
    invalid = _shared_asset_change(
        factory,
        policies,
        valid.asset_id,
        ThesisChangeType.NEW_THESIS,
        FACT_TIME + timedelta(days=90),
    )
    signals = (
        _persist_signal(factory, valid, observed_at=FACT_TIME + timedelta(days=90)),
        _persist_signal(factory, invalid),
    )
    feed = _legacy_feed(factory, valid.asset_id, signals, state=state)
    # A previous effective Event aggregation already corrected metadata, but
    # retained old links and the too-new last time. Repeating that stage must
    # leave this Event unchanged; this task updates Priority/Feed only.
    plan = IntelligenceEventAggregator.from_production(factory).dry_run()
    with factory() as session:
        priority = session.get(IntelligenceEventPriority, feed.priority_id)
        priority.priority_level = "HIGH"
        priority.evidence_count = 2
        event = session.get(IntelligenceEvent, priority.event_id)
        event.metadata_json = plan.candidates[0].metadata
        event.first_observed_at = FACT_TIME
        session.commit()
    return valid, feed


def _assert_current_equals_stored(factory, api, original):
    item = _get(api)["items"][0]
    with factory() as session:
        feed = session.get(IntelligenceFeedItem, original.id)
        priority = session.get(IntelligenceEventPriority, original.priority_id)
        assert priority.id == original.priority_id
        assert priority.reason == "THESIS_CHANGE_OBSERVED"
        assert priority.priority_level == "MEDIUM"
        assert priority.evidence_count == item["context"]["signal_count"]
        assert feed.id == original.id
        assert feed.priority_id == original.priority_id
        assert feed.reason == item["reason"] == "THESIS_CHANGE_OBSERVED"
        assert feed.title == item["title"] == "A thesis change was observed"
        assert feed.context == item["context"]
        assert feed.state == item["state"] == original.state.value
        assert feed.created_at.replace(tzinfo=original.created_at.tzinfo) == original.created_at
        assert (
            feed.observed_at.replace(tzinfo=FACT_TIME.tzinfo).isoformat().replace("+00:00", "Z")
            == item["observed_at"]
        )
    return item


@pytest.mark.parametrize("state", (FeedState.ACTIVE, FeedState.STALE, FeedState.RESOLVED))
def test_mixed_history_rerun_corrects_only_priority_and_feed(
    db_session_factory, production_policies, feed_api, state
):
    valid, old_feed = _history(db_session_factory, production_policies, state=state)
    protected = _protected(db_session_factory)
    before = _snapshot(db_session_factory)
    aggregator = IntelligenceEventAggregator.from_production(db_session_factory)
    assert aggregator.aggregate().created_evidence_count == 0
    assert _snapshot(db_session_factory) == before
    priority_service = IntelligencePriorityService.from_production(db_session_factory)
    plan = priority_service.dry_run()
    assert plan.candidates[0].evidence_count == 1
    assert plan.candidates[0].reason is IntelligencePriorityReason.THESIS_CHANGE_OBSERVED
    assert plan.priorities[0].priority_level is IntelligencePriorityLevel.HIGH
    assert _snapshot(db_session_factory) == before
    corrected = priority_service.materialize()
    assert corrected.reused_count == 1 and corrected.created_count == 0
    assert corrected.priorities[0].reason is IntelligencePriorityReason.THESIS_CHANGE_OBSERVED
    assert corrected.priorities[0].created_at == plan.priorities[0].created_at
    feed_service = IntelligenceFeedService.from_production(db_session_factory)
    before_feed = _snapshot(db_session_factory)
    feed_plan = feed_service.dry_run()
    assert feed_plan.candidates[0].context["signal_count"] == 1
    assert feed_plan.candidates[0].observed_at == valid.effective_time
    assert _snapshot(db_session_factory) == before_feed
    assert feed_service.materialize().reused_count == 1
    item = _assert_current_equals_stored(db_session_factory, feed_api, old_feed)
    assert item["context"]["investor_count"] == 1
    assert [value["investor_id"] for value in item["investors"]] == [str(valid.investor_id)]
    assert _get(feed_api, since=(FACT_TIME + timedelta(days=89)).isoformat())["total"] == 0
    stable = _snapshot(db_session_factory)
    priority_service.materialize()
    feed_service.materialize()
    _get(feed_api)
    assert _snapshot(db_session_factory) == stable
    assert _protected(db_session_factory) == protected


@pytest.mark.parametrize("pending", ("count", "classification"))
def test_feed_requires_priority_refresh_in_dry_run_and_materialization(
    db_session_factory, production_policies, pending
):
    _, feed = _history(db_session_factory, production_policies)
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, feed.priority_id)
        if pending == "classification":
            priority.evidence_count = 1
        else:
            priority.reason = "THESIS_CHANGE_OBSERVED"
            priority.priority_level = "MEDIUM"
        session.commit()
    before = _snapshot(db_session_factory)
    service = IntelligenceFeedService.from_production(db_session_factory)
    for operation in (service.dry_run, service.materialize):
        with pytest.raises(
            ValueError,
            match=("must be refreshed" if pending == "classification" else "evidence count"),
        ):
            operation()
        assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("existing", (False, True))
@pytest.mark.parametrize(
    "kind",
    (
        ThesisChangeType.NEW_THESIS,
        ThesisChangeType.THESIS_UNCHANGED,
        ThesisChangeType.INSUFFICIENT_EVIDENCE,
    ),
)
def test_all_invalid_history_does_not_create_or_refresh_projections(
    db_session_factory, production_policies, feed_api, existing, kind
):
    source = _seed_change(db_session_factory, production_policies, kind)
    signal = _persist_signal(db_session_factory, source)
    _legacy_feed(db_session_factory, source.asset_id, (signal,))
    if not existing:
        with db_session_factory() as session:
            session.execute(delete(IntelligenceFeedItem))
            session.execute(delete(IntelligenceEventPriority))
            session.commit()
    before = _snapshot(db_session_factory)
    priority = IntelligencePriorityService.from_production(db_session_factory)
    feed = IntelligenceFeedService.from_production(db_session_factory)
    assert priority.dry_run().candidates == ()
    assert priority.materialize().priorities == ()
    assert feed.dry_run().candidates == ()
    assert feed.materialize().items == ()
    assert _get(feed_api)["total"] == 0
    assert _snapshot(db_session_factory) == before


def test_late_predecessor_invalidation_refreshes_effective_counts_without_source_changes(
    db_session_factory, production_policies, feed_api
):
    first = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    second = _second_material_change(db_session_factory, production_policies, first)
    signals = [_persist_signal(db_session_factory, source) for source in (first, second)]
    stored = _legacy_feed(db_session_factory, first.asset_id, signals)
    priority = IntelligencePriorityService.from_production(db_session_factory)
    feed = IntelligenceFeedService.from_production(db_session_factory)
    priority.materialize()
    feed.materialize()
    with db_session_factory() as session:
        _add_opinion(
            session,
            session.get(Investor, first.investor_id),
            session.get(Asset, first.asset_id),
            production_policies[0].active_spec,
            FACT_TIME - timedelta(hours=12),
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    protected = _protected(db_session_factory)
    assert priority.dry_run().candidates[0].evidence_count == 1
    with pytest.raises(ValueError, match="Priority"):
        feed.dry_run()
    priority.materialize()
    feed.materialize()
    item = _assert_current_equals_stored(db_session_factory, feed_api, stored)
    assert item["context"]["signal_count"] == 1
    assert item["observed_at"] == second.effective_time.isoformat().replace("+00:00", "Z")
    assert _protected(db_session_factory) == protected


@pytest.mark.parametrize("association", ("unlinked", "wrong_asset"))
def test_materialization_does_not_borrow_unlinked_or_other_asset_evidence(
    db_session_factory, production_policies, feed_api, association
):
    anchor = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    if association == "unlinked":
        material = _shared_asset_change(
            db_session_factory,
            production_policies,
            anchor.asset_id,
            ThesisChangeType.THESIS_CHANGED,
            FACT_TIME,
        )
    else:
        material = _seed_change(
            db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED
        )
    good_signal = _persist_signal(db_session_factory, material)
    linked = (
        _persist_signal(db_session_factory, anchor) if association == "unlinked" else good_signal
    )
    _legacy_feed(db_session_factory, anchor.asset_id, (linked,))
    before = _snapshot(db_session_factory)
    assert (
        IntelligencePriorityService.from_production(db_session_factory).materialize().priorities
        == ()
    )
    assert IntelligenceFeedService.from_production(db_session_factory).materialize().items == ()
    assert _get(feed_api)["total"] == 0
    assert _snapshot(db_session_factory) == before


def test_non_active_event_is_not_refreshed(db_session_factory, production_policies):
    _, feed = _history(db_session_factory, production_policies)
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, feed.priority_id)
        session.get(IntelligenceEvent, priority.event_id).state = "RESOLVED"
        session.commit()
    before = _snapshot(db_session_factory)
    assert (
        IntelligencePriorityService.from_production(db_session_factory).materialize().priorities
        == ()
    )
    assert IntelligenceFeedService.from_production(db_session_factory).materialize().items == ()
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize(
    "event_type",
    (
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        IntelligenceEventType.CONSENSUS_STATE_CHANGE,
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
    ),
)
def test_other_types_keep_legacy_repository_and_feed_behavior(
    db_session_factory, production_policies, event_type
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    signal = _persist_signal(db_session_factory, source)
    old = _legacy_feed(db_session_factory, source.asset_id, (signal,), event_type=event_type)
    with db_session_factory() as session:
        event = session.get(
            IntelligenceEvent, session.get(IntelligenceEventPriority, old.priority_id).event_id
        )
        event.metadata_json = {"investor_ids": ["a", "b", "c"]}
        session.commit()
    result = IntelligencePriorityService.from_production(db_session_factory).materialize()
    assert result.priorities[0].reason is IntelligencePriorityReason.THESIS_ACCELERATION
    assert result.priorities[0].evidence_count == 1
    materialized = (
        IntelligenceFeedService.from_production(db_session_factory).materialize().items[0]
    )
    assert materialized.reason is IntelligencePriorityReason.THESIS_ACCELERATION
    assert materialized.observed_at == old.observed_at


def test_thesis_refresh_repository_rejects_other_event_types(
    db_session_factory, production_policies
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    old = _legacy_feed(
        db_session_factory,
        source.asset_id,
        (_persist_signal(db_session_factory, source),),
        event_type=IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
    )
    before = _snapshot(db_session_factory)
    with db_session_factory() as session:
        repository = IntelligenceEventPriorityRepository(session)
        previous = repository.get(old.priority_id)
        command = IntelligenceEventPriorityCreate(
            event_id=previous.event_id,
            priority_level=IntelligencePriorityLevel.MEDIUM,
            reason=IntelligencePriorityReason.THESIS_CHANGE_OBSERVED,
            evidence_count=1,
            created_at=FACT_TIME,
        )
        with pytest.raises(ValueError, match="INVESTOR_VIEW_CHANGE"):
            repository.add_or_refresh_thesis_change(command)
    assert _snapshot(db_session_factory) == before


def test_materialization_dry_runs_and_query_remain_batched_and_read_only(
    db_engine, db_session_factory, production_policies, feed_api
):
    statements = []

    def track(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    def read_plan():
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            IntelligencePriorityService.from_production(db_session_factory).dry_run()
            IntelligenceFeedService.from_production(db_session_factory).dry_run()
            _get(feed_api)
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        return len(statements)

    for index in range(6):
        _history(db_session_factory, production_policies)
        IntelligencePriorityService.from_production(db_session_factory).materialize()
        IntelligenceFeedService.from_production(db_session_factory).materialize()
        if index in (0, 5):
            before = _snapshot(db_session_factory)
            count = read_plan()
            if index == 0:
                first_count = count
            else:
                assert count == first_count == 27
            assert _snapshot(db_session_factory) == before
