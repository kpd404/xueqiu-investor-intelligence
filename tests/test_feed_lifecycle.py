from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from contracts import (
    FeedItem,
    FeedState,
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityView,
    IntelligenceEventState,
    IntelligenceEventType,
    IntelligenceEventView,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    SignalSeverity,
    SignalState,
    SignalType,
    SignalView,
)
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService

NOW = datetime(2026, 9, 17, 12, tzinfo=UTC)


class _FeedWriter:
    def __init__(self, items):
        self.items = {item.id: item for item in items}

    def list(self):
        return tuple(self.items.values())

    def update_state(self, feed_item_id: UUID, state: FeedState) -> FeedItem:
        item = self.items[feed_item_id]
        updated = item.model_copy(update={"state": state})
        self.items[feed_item_id] = updated
        return updated


class _Reader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _Uow:
    def __init__(self, values):
        self.intelligence_feed_items = _FeedWriter(values["feeds"])
        self.intelligence_event_priorities = _Reader(values["priorities"])
        self.intelligence_events = _Reader(values["events"])
        self.intelligence_event_evidence = _Reader(values["links"])
        self.signals = _Reader(values["signals"])
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.commit_count += 1


def _entry(
    *,
    state: FeedState,
    event_type: IntelligenceEventType = IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
    reason: IntelligencePriorityReason = IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION,
    level: IntelligencePriorityLevel = IntelligencePriorityLevel.MEDIUM,
    observed_at: datetime = NOW,
):
    asset_id = uuid4()
    event_id = uuid4()
    priority_id = uuid4()
    feed_id = uuid4()
    signal_id = uuid4()
    event = IntelligenceEventView(
        id=event_id,
        asset_id=asset_id,
        event_type=event_type,
        state=IntelligenceEventState.ACTIVE,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        metadata={},
    )
    priority = IntelligenceEventPriorityView(
        id=priority_id,
        event_id=event_id,
        priority_level=level,
        reason=reason,
        evidence_count=1,
        created_at=observed_at,
    )
    signal = SignalView(
        id=signal_id,
        asset_id=asset_id,
        investor_id=uuid4(),
        signal_type=SignalType.NEW_ATTENTION,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.LOW,
        source_type="test",
        source_id=uuid4(),
        created_at=observed_at,
        observed_at=observed_at,
        metadata={},
    )
    link = IntelligenceEventEvidenceView(id=uuid4(), event_id=event_id, signal_id=signal_id)
    feed = FeedItem(
        id=feed_id,
        priority_id=priority_id,
        asset_id=asset_id,
        event_type=event_type,
        title="test",
        context={},
        reason=reason,
        state=state,
        observed_at=observed_at,
        created_at=observed_at,
    )
    return {
        "feed": feed,
        "event": event,
        "priority": priority,
        "signal": signal,
        "link": link,
    }


def _uow_from_entries(entries):
    return _Uow(
        {
            "feeds": tuple(entry["feed"] for entry in entries),
            "events": tuple(entry["event"] for entry in entries),
            "priorities": tuple(entry["priority"] for entry in entries),
            "signals": tuple(entry["signal"] for entry in entries),
            "links": tuple(entry["link"] for entry in entries),
        }
    )


def test_lifecycle_policy_activates_new_items_by_each_deterministic_rule() -> None:
    old = NOW - timedelta(days=60)
    entries = (
        _entry(state=FeedState.NEW, level=IntelligencePriorityLevel.HIGH, observed_at=old),
        _entry(
            state=FeedState.NEW,
            event_type=IntelligenceEventType.CONSENSUS_STATE_CHANGE,
            observed_at=old,
        ),
        _entry(
            state=FeedState.NEW,
            event_type=IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
            observed_at=old,
        ),
        _entry(
            state=FeedState.NEW,
            reason=IntelligencePriorityReason.THESIS_ACCELERATION,
            observed_at=old,
        ),
        _entry(state=FeedState.NEW, observed_at=NOW - timedelta(days=1)),
        _entry(state=FeedState.NEW, observed_at=old),
    )
    uow = _uow_from_entries(entries)
    service = FeedLifecycleService(
        lambda: uow,
        policy=FeedLifecyclePolicy(
            activation_window=timedelta(days=7),
            stale_window=timedelta(days=30),
        ),
    )

    result = service.dry_run(now=NOW)

    assert len(result.plan.transitions) == 5
    assert result.plan.current_counts[FeedState.NEW] == 6
    assert result.plan.predicted_counts[FeedState.NEW] == 1
    assert result.plan.predicted_counts[FeedState.ACTIVE] == 5
    assert uow.commit_count == 0
    assert all(item.state is FeedState.NEW for item in uow.intelligence_feed_items.list())


def test_active_items_stale_only_after_configured_window() -> None:
    entries = (
        _entry(state=FeedState.ACTIVE, observed_at=NOW - timedelta(days=31)),
        _entry(state=FeedState.ACTIVE, observed_at=NOW - timedelta(days=1)),
    )
    uow = _uow_from_entries(entries)
    service = FeedLifecycleService(
        lambda: uow,
        policy=FeedLifecyclePolicy(
            activation_window=timedelta(days=7),
            stale_window=timedelta(days=30),
        ),
    )

    result = service.dry_run(now=NOW)

    assert len(result.plan.transitions) == 1
    assert result.plan.transitions[0].to_state is FeedState.STALE
    assert result.plan.predicted_counts[FeedState.ACTIVE] == 1
    assert result.plan.predicted_counts[FeedState.STALE] == 1


def test_invalid_transitions_and_resolved_state_are_not_automatic() -> None:
    with pytest.raises(ValueError, match="invalid FeedItem transition"):
        FeedLifecyclePolicy.validate_transition(FeedState.NEW, FeedState.RESOLVED)

    entry = _entry(state=FeedState.RESOLVED, observed_at=NOW - timedelta(days=90))
    uow = _uow_from_entries((entry,))
    result = FeedLifecycleService(lambda: uow).dry_run(now=NOW)

    assert result.plan.transitions == ()


def test_lifecycle_apply_is_idempotent_and_changes_only_feed_state() -> None:
    entry = _entry(state=FeedState.NEW, observed_at=NOW)
    uow = _uow_from_entries((entry,))
    service = FeedLifecycleService(
        lambda: uow,
        policy=FeedLifecyclePolicy(
            activation_window=timedelta(days=7),
            stale_window=timedelta(days=30),
        ),
    )

    before = uow.intelligence_feed_items.list()[0]
    first = service.apply(now=NOW)
    second = service.apply(plan=first.plan)
    after = uow.intelligence_feed_items.list()[0]

    assert first.updated_count == 1
    assert second.updated_count == 0
    assert second.reused_count == 1
    assert second.plan is first.plan
    assert uow.commit_count == 1
    assert after.state is FeedState.ACTIVE
    assert after.id == before.id
    assert after.priority_id == before.priority_id
    assert after.asset_id == before.asset_id
    assert after.observed_at == before.observed_at
    assert after.created_at == before.created_at


def test_traceability_failure_blocks_lifecycle_mutation() -> None:
    entry = _entry(state=FeedState.NEW)
    values = {
        "feeds": (entry["feed"],),
        "events": (entry["event"],),
        "priorities": (entry["priority"],),
        "signals": (),
        "links": (entry["link"],),
    }
    uow = _Uow(values)

    with pytest.raises(ValueError, match="Signal not found"):
        FeedLifecycleService(lambda: uow).apply(now=NOW)

    assert uow.commit_count == 0
    assert uow.intelligence_feed_items.list()[0].state is FeedState.NEW
