from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    FeedItemCreate,
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
from database.models import Asset
from database.repositories.intelligence_event_priorities import (
    IntelligenceEventPriorityRepository,
)
from database.repositories.intelligence_events import IntelligenceEventRepository
from intelligence.feed import IntelligenceFeedService

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def _signal(
    event_id: UUID,
    *,
    investor_id: UUID | None = None,
    source_type: str = "AttentionOccurrence",
) -> SignalView:
    return SignalView(
        id=uuid4(),
        asset_id=uuid4(),
        investor_id=investor_id,
        signal_type=SignalType.NEW_ATTENTION,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.LOW,
        source_type=source_type,
        source_id=uuid4(),
        created_at=NOW,
        observed_at=NOW,
        metadata={"event_id": str(event_id)},
    )


def _event(event_type: IntelligenceEventType) -> IntelligenceEventView:
    return IntelligenceEventView(
        id=uuid4(),
        asset_id=uuid4(),
        event_type=event_type,
        state=IntelligenceEventState.ACTIVE,
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(hours=1),
        metadata={},
    )


def _priority(event: IntelligenceEventView) -> IntelligenceEventPriorityView:
    reason_by_event = {
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE: (
            IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION
        ),
        IntelligenceEventType.INVESTOR_VIEW_CHANGE: IntelligencePriorityReason.THESIS_ACCELERATION,
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY: (
            IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY
        ),
        IntelligenceEventType.CONSENSUS_STATE_CHANGE: (
            IntelligencePriorityReason.CONSENSUS_STATE_CHANGE
        ),
    }
    reason = reason_by_event[event.event_type]
    level = {
        IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION: IntelligencePriorityLevel.HIGH,
        IntelligencePriorityReason.THESIS_ACCELERATION: IntelligencePriorityLevel.MEDIUM,
        IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY: IntelligencePriorityLevel.LOW,
        IntelligencePriorityReason.CONSENSUS_STATE_CHANGE: IntelligencePriorityLevel.HIGH,
    }[reason]
    return IntelligenceEventPriorityView(
        id=uuid4(),
        event_id=event.id,
        priority_level=level,
        reason=reason,
        evidence_count=2,
        created_at=NOW,
    )


class _PriorityReader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _EventReader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _EvidenceReader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _SignalReader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _FeedWriter:
    def __init__(self):
        self.values = {}

    def list(self):
        return tuple(self.values.values())

    def add_if_absent(self, command):
        existing = self.values.get(command.priority_id)
        if existing is not None:
            return existing, False
        from contracts import FeedItem

        item = FeedItem(id=uuid4(), **command.model_dump())
        self.values[command.priority_id] = item
        return item, True


class _Uow:
    def __init__(self, priorities, events, links, signals):
        self.intelligence_event_priorities = _PriorityReader(priorities)
        self.intelligence_events = _EventReader(events)
        self.intelligence_event_evidence = _EvidenceReader(links)
        self.signals = _SignalReader(signals)
        self.intelligence_feed_items = _FeedWriter()
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.commit_count += 1


def test_feed_contract_has_explicit_state_and_required_fields() -> None:
    assert set(FeedState) == {
        FeedState.NEW,
        FeedState.ACTIVE,
        FeedState.STALE,
        FeedState.RESOLVED,
    }
    with pytest.raises(ValidationError):
        FeedItemCreate(
            priority_id=uuid4(),
            asset_id=uuid4(),
            event_type=IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
            title="",
            reason=IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
            observed_at=NOW,
            created_at=NOW,
        )


def test_feed_titles_are_deterministic_templates() -> None:
    assert (
        IntelligenceFeedService._title(IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION)
        == "Multiple investors started paying attention"
    )
    assert (
        IntelligenceFeedService._title(IntelligencePriorityReason.THESIS_ACCELERATION)
        == "Multiple thesis changes were observed"
    )


def test_feed_projection_context_traceability_and_idempotency() -> None:
    event = _event(IntelligenceEventType.ASSET_ACTIVITY_SPIKE)
    priority = _priority(event)
    signals = (
        _signal(event.id, investor_id=uuid4()),
        _signal(event.id, investor_id=uuid4(), source_type="ThesisChange"),
    )
    links = tuple(
        IntelligenceEventEvidenceView(id=uuid4(), event_id=event.id, signal_id=signal.id)
        for signal in signals
    )
    uow = _Uow((priority,), (event,), links, signals)
    service = IntelligenceFeedService(lambda: uow)

    dry_run = service.dry_run()
    first = service.materialize()
    second = service.generate_many()

    assert dry_run.created_count == 1
    assert dry_run.reused_count == 0
    assert first.created_count == 1
    assert second.created_count == 0
    assert second.reused_count == 1
    assert second.duplicate_count == 0
    item = first.items[0]
    assert item.priority_id == priority.id
    assert item.asset_id == event.asset_id
    assert item.event_type is event.event_type
    assert item.state is FeedState.NEW
    assert item.context == {
        "investor_count": 2,
        "signal_count": 2,
        "source_count": 2,
        "source_types": ["AttentionOccurrence", "ThesisChange"],
    }
    assert uow.commit_count == 2


def test_feed_repository_is_unique_by_priority(db_session) -> None:
    asset = Asset(name="Feed Asset", market="SH", symbol="600097")
    db_session.add(asset)
    db_session.flush()
    event, _ = IntelligenceEventRepository(db_session).add_if_absent(
        _event(IntelligenceEventType.CROSS_INVESTOR_DISCOVERY).model_copy(
            update={"asset_id": asset.id}
        )
    )
    priority_repository = IntelligenceEventPriorityRepository(db_session)
    priority, _ = priority_repository.add_if_absent(_priority(event))
    from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository

    repository = IntelligenceFeedItemRepository(db_session)
    command = FeedItemCreate(
        priority_id=priority.id,
        asset_id=asset.id,
        event_type=event.event_type,
        title="Cross-investor attention was observed",
        context={"investor_count": 2, "signal_count": 1, "source_count": 1},
        reason=IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
        observed_at=NOW,
        created_at=NOW,
    )
    first, created = repository.add_if_absent(command)
    second, reused = repository.add_if_absent(command)
    db_session.commit()

    assert created is True
    assert reused is False
    assert first.id == second.id
    assert len(repository.list()) == 1


def test_feed_repository_refreshes_projection_and_preserves_lifecycle_state(db_session) -> None:
    asset = Asset(name="Updated Feed Asset", market="SH", symbol="600101")
    db_session.add(asset)
    db_session.flush()
    event, _ = IntelligenceEventRepository(db_session).add_if_absent(
        _event(IntelligenceEventType.CROSS_INVESTOR_DISCOVERY).model_copy(
            update={"asset_id": asset.id}
        )
    )
    priority, _ = IntelligenceEventPriorityRepository(db_session).add_if_absent(_priority(event))
    from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository

    repository = IntelligenceFeedItemRepository(db_session)
    first_command = FeedItemCreate(
        priority_id=priority.id,
        asset_id=asset.id,
        event_type=event.event_type,
        title="Cross-investor attention was observed",
        context={"signal_count": 1, "source_count": 1},
        reason=IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
        observed_at=NOW,
        created_at=NOW,
    )
    first, created = repository.add_if_absent(first_command)
    active = repository.update_state(first.id, FeedState.ACTIVE)
    refreshed, reused = repository.add_if_absent(
        first_command.model_copy(
            update={
                "context": {"signal_count": 3, "source_count": 3},
                "observed_at": NOW + timedelta(hours=4),
            }
        )
    )
    db_session.commit()

    assert created is True
    assert reused is False
    assert refreshed.id == first.id
    assert refreshed.state is FeedState.ACTIVE
    assert refreshed.state is active.state
    assert refreshed.created_at == first.created_at
    assert refreshed.observed_at == NOW + timedelta(hours=4)
    assert refreshed.context == {"signal_count": 3, "source_count": 3}
    assert len(repository.list()) == 1
