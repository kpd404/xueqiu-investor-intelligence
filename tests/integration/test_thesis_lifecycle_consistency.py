"""Real mixed-history materialization, lifecycle, and HTTP; no source mocks."""

from datetime import timedelta

import pytest
from sqlalchemy import event as sqlalchemy_event

from contracts import EventAnalysisStatus, FeedState, IntelligenceEventType, ThesisChangeType
from contracts.intelligence_feed import feed_display_context
from database.models import Asset, IntelligenceEventPriority, IntelligenceFeedItem, Investor
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from operations.refresh import OperationalRefreshService
from tests.integration import test_thesis_change_feed as feed_fixtures
from tests.integration import test_thesis_change_signals as signal_fixtures
from tests.integration.test_effective_thesis_feed_query import _get, _legacy_feed, _snapshot
from tests.integration.test_effective_thesis_signals import _persist_signal, _shared_asset_change
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion, _seed_change
from tests.integration.test_thesis_materialization_consistency import _history

production_policies = signal_fixtures.production_policies
feed_api = feed_fixtures.feed_api
NOW = FACT_TIME + timedelta(hours=12)


def _materialize(factory):
    IntelligencePriorityService.from_production(factory).materialize()
    IntelligenceFeedService.from_production(factory).materialize()


def _without_feed_state(factory):
    result = _snapshot(factory)
    result["intelligence_feed_items"] = tuple(
        {
            key: (feed_display_context(value) if key == "context" else value)
            for key, value in row.items()
            if key != "state"
        }
        for row in result["intelligence_feed_items"]
    )
    return result


@pytest.mark.parametrize(
    "initial,days,expected",
    (
        (FeedState.NEW, 0, FeedState.ACTIVE),
        (FeedState.NEW, 90, FeedState.NEW),
        (FeedState.ACTIVE, 90, FeedState.STALE),
        (FeedState.STALE, 0, FeedState.STALE),
        (FeedState.RESOLVED, 0, FeedState.RESOLVED),
    ),
)
def test_full_mixed_history_chain_uses_valid_fact_time_and_only_changes_state(
    db_session_factory, production_policies, feed_api, initial, days, expected
):
    source, old = _history(db_session_factory, production_policies, state=initial)
    before_event = _snapshot(db_session_factory)
    IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    assert _snapshot(db_session_factory) == before_event
    _materialize(db_session_factory)
    before_lifecycle = _snapshot(db_session_factory)
    protected = _without_feed_state(db_session_factory)
    now = NOW + timedelta(days=days)
    lifecycle = FeedLifecycleService.from_production(
        db_session_factory, policy=FeedLifecyclePolicy(), now_factory=lambda: now
    )
    plan = lifecycle.dry_run(now=now)
    assert _snapshot(db_session_factory) == before_lifecycle
    if initial is FeedState.STALE:
        assert plan.plan.skipped[0].reason == "LEGACY_STALE_BASELINE_INITIALIZED"
    else:
        assert plan.plan.skipped == ()
    result = lifecycle.apply(plan=plan.plan)
    assert result.updated_count == int(initial is not expected)
    assert lifecycle.apply(now=now).updated_count == 0
    repeated = lifecycle.apply(plan=result.plan)
    assert repeated.updated_count == 0
    assert _without_feed_state(db_session_factory) == protected
    with db_session_factory() as session:
        stored = session.get(IntelligenceFeedItem, old.id)
        assert stored.state == expected.value
        assert stored.observed_at.replace(tzinfo=FACT_TIME.tzinfo) == source.effective_time
        assert stored.context["signal_count"] == 1
    recent = _get(feed_api, state="ACTIVE", since=(now - timedelta(days=1)).isoformat())
    assert recent["total"] == int(expected is FeedState.ACTIVE)
    current = _get(feed_api)["items"][0]
    assert current["state"] == expected.value
    assert current["reason"] == "THESIS_CHANGE_OBSERVED"
    assert current["context"]["signal_count"] == current["context"]["investor_count"] == 1
    assert current["observed_at"] == FACT_TIME.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("cause", ("legacy_non_material", "late_predecessor"))
@pytest.mark.parametrize("bad_state", (FeedState.NEW, FeedState.ACTIVE))
def test_no_effective_evidence_is_recorded_and_does_not_block_normal_items(
    db_session_factory, production_policies, feed_api, cause, bad_state
):
    if cause == "legacy_non_material":
        source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
        bad = _legacy_feed(
            db_session_factory,
            source.asset_id,
            (_persist_signal(db_session_factory, source),),
            state=bad_state,
        )
    else:
        source, bad = _history(db_session_factory, production_policies, state=bad_state)
        _materialize(db_session_factory)
        with db_session_factory() as session:
            _add_opinion(
                session,
                session.get(Investor, source.investor_id),
                session.get(Asset, source.asset_id),
                production_policies[0].active_spec,
                FACT_TIME - timedelta(hours=12),
                EventAnalysisStatus.SUCCESS,
            )
            session.commit()
    _, normal = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _materialize(db_session_factory)
    protected = _without_feed_state(db_session_factory)
    service = FeedLifecycleService.from_production(db_session_factory, policy=FeedLifecyclePolicy())
    result = service.apply(now=NOW)
    assert result.updated_count == 1
    assert [skip.feed_item_id for skip in result.plan.skipped] == [bad.id]
    assert result.plan.skipped[0].reason == "NO_EFFECTIVE_THESIS_EVIDENCE"
    assert service.apply(now=NOW).updated_count == 0
    with db_session_factory() as session:
        assert session.get(IntelligenceFeedItem, bad.id).state == bad_state.value
        assert session.get(IntelligenceFeedItem, normal.id).state == "ACTIVE"
    assert _without_feed_state(db_session_factory) == protected
    assert [item["id"] for item in _get(feed_api, state="ACTIVE")["items"]] == [str(normal.id)]


@pytest.mark.parametrize(
    "field,expected_error",
    (
        ("priority_count", "Priority evidence count"),
        ("priority_reason", "Thesis Priority"),
        ("priority_level", "Thesis Priority"),
        ("feed_reason", "Thesis Feed reason"),
        ("title", "Thesis Feed title"),
        ("context", "Thesis Feed context"),
        ("observed_at", "Thesis Feed observed_at"),
    ),
)
def test_valid_evidence_requires_refreshed_priority_and_feed_projection(
    db_session_factory, production_policies, field, expected_error
):
    _, old = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _materialize(db_session_factory)
    with db_session_factory() as session:
        feed = session.get(IntelligenceFeedItem, old.id)
        priority = session.get(IntelligenceEventPriority, old.priority_id)
        if field == "priority_count":
            priority.evidence_count = 2
        elif field == "priority_reason":
            priority.reason = feed.reason = "THESIS_ACCELERATION"
        elif field == "priority_level":
            priority.priority_level = "HIGH"
        elif field == "feed_reason":
            feed.reason = "THESIS_ACCELERATION"
        elif field == "title":
            feed.title = "Old acceleration claim"
        elif field == "context":
            feed.context = {"signal_count": 2}
        else:
            feed.observed_at = FACT_TIME + timedelta(days=90)
        session.commit()
    before = _snapshot(db_session_factory)
    service = FeedLifecycleService.from_production(db_session_factory, policy=FeedLifecyclePolicy())
    for operation in (service.dry_run, service.apply):
        with pytest.raises(ValueError, match=expected_error):
            operation(now=NOW)
        assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("association", ("unlinked", "wrong_asset"))
def test_lifecycle_does_not_borrow_other_effective_evidence(
    db_session_factory, production_policies, association
):
    anchor = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    if association == "unlinked":
        good = _shared_asset_change(
            db_session_factory,
            production_policies,
            anchor.asset_id,
            ThesisChangeType.THESIS_CHANGED,
            FACT_TIME,
        )
    else:
        good = _seed_change(
            db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED
        )
    good_signal = _persist_signal(db_session_factory, good)
    linked = (
        _persist_signal(db_session_factory, anchor) if association == "unlinked" else good_signal
    )
    old = _legacy_feed(db_session_factory, anchor.asset_id, (linked,), state=FeedState.NEW)
    before = _snapshot(db_session_factory)
    result = FeedLifecycleService.from_production(db_session_factory).apply(now=NOW)
    assert result.updated_count == 0
    assert result.plan.skipped[0].feed_item_id == old.id
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize(
    "kind",
    (
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        IntelligenceEventType.CONSENSUS_STATE_CHANGE,
    ),
)
def test_other_event_types_keep_original_lifecycle_behavior(
    db_session_factory, production_policies, kind
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    old = _legacy_feed(
        db_session_factory,
        source.asset_id,
        (_persist_signal(db_session_factory, source),),
        state=FeedState.NEW,
        event_type=kind,
    )
    with db_session_factory() as session:
        session.get(IntelligenceEventPriority, old.priority_id).evidence_count = 1
        session.commit()
    result = FeedLifecycleService.from_production(db_session_factory).apply(
        now=old.observed_at + timedelta(hours=1)
    )
    assert result.updated_count == 1


def test_lifecycle_and_http_source_reads_are_batched_and_dry_run_is_read_only(
    db_engine, db_session_factory, production_policies, feed_api
):
    statements = []

    def track(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    for index in range(6):
        _history(db_session_factory, production_policies, state=FeedState.NEW)
        _materialize(db_session_factory)
        before = _snapshot(db_session_factory)
        if index in (0, 5):
            statements.clear()
            sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
            try:
                FeedLifecycleService.from_production(db_session_factory).dry_run(now=NOW)
                _get(feed_api)
            finally:
                sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
            assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
            if index == 0:
                first_count = len(statements)
            else:
                assert len(statements) == first_count == 21
        assert _snapshot(db_session_factory) == before


def test_skip_diagnostics_are_exposed_by_isolated_operational_helper(
    db_session_factory, production_policies
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    old = _legacy_feed(
        db_session_factory, source.asset_id, (_persist_signal(db_session_factory, source),)
    )
    before = _snapshot(db_session_factory)
    # Only call this isolated lifecycle helper, never run refresh/collection/LLM.
    summary = OperationalRefreshService(db_session_factory)._apply_feed_lifecycle()
    assert summary["skipped_count"] == 1
    assert summary["skipped"][0]["feed_item_id"] == str(old.id)
    assert summary["skipped"][0]["reason"] == "NO_EFFECTIVE_THESIS_EVIDENCE"
    assert _snapshot(db_session_factory) == before
