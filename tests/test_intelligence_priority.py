from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityCreate,
    IntelligenceEventPriorityView,
    IntelligenceEventState,
    IntelligenceEventType,
    IntelligenceEventView,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
)
from database.models import Asset
from database.repositories.intelligence_event_priorities import (
    IntelligenceEventPriorityRepository,
)
from database.repositories.intelligence_events import IntelligenceEventRepository
from intelligence.priority import IntelligencePriorityService

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def _event(
    event_type: IntelligenceEventType,
    *,
    signal_count: int = 1,
    investor_count: int = 0,
    state: IntelligenceEventState = IntelligenceEventState.ACTIVE,
) -> IntelligenceEventView:
    return IntelligenceEventView(
        id=uuid4(),
        asset_id=uuid4(),
        event_type=event_type,
        state=state,
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(hours=1),
        metadata={
            "signal_count": signal_count,
            "investor_ids": [str(uuid4()) for _ in range(investor_count)],
        },
    )


def _link(event_id: UUID, signal_id: UUID | None = None) -> IntelligenceEventEvidenceView:
    return IntelligenceEventEvidenceView(
        id=uuid4(),
        event_id=event_id,
        signal_id=signal_id or uuid4(),
    )


def test_priority_contract_has_explicit_levels_and_reasons() -> None:
    assert set(IntelligencePriorityLevel) == {
        IntelligencePriorityLevel.LOW,
        IntelligencePriorityLevel.MEDIUM,
        IntelligencePriorityLevel.HIGH,
    }
    assert set(IntelligencePriorityReason) == {
        IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION,
        IntelligencePriorityReason.THESIS_ACCELERATION,
        IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
        IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
    }
    with pytest.raises(ValidationError):
        IntelligenceEventPriorityCreate(
            event_id=uuid4(),
            priority_level=IntelligencePriorityLevel.LOW,
            reason=IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
            evidence_count=0,
            created_at=NOW,
        )


def test_priority_rules_are_deterministic_and_do_not_use_inactive_events() -> None:
    assert IntelligencePriorityService._classify(
        _event(IntelligenceEventType.ASSET_ACTIVITY_SPIKE, investor_count=3)
    ) == (
        IntelligencePriorityLevel.HIGH,
        IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION,
    )
    assert (
        IntelligencePriorityService._classify(
            _event(IntelligenceEventType.ASSET_ACTIVITY_SPIKE, investor_count=2)
        )
        is None
    )
    assert IntelligencePriorityService._classify(
        _event(IntelligenceEventType.INVESTOR_VIEW_CHANGE, signal_count=2)
    ) == (
        IntelligencePriorityLevel.MEDIUM,
        IntelligencePriorityReason.THESIS_ACCELERATION,
    )
    assert IntelligencePriorityService._classify(
        _event(IntelligenceEventType.CROSS_INVESTOR_DISCOVERY)
    ) == (
        IntelligencePriorityLevel.LOW,
        IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
    )
    assert IntelligencePriorityService._classify(
        _event(IntelligenceEventType.CONSENSUS_STATE_CHANGE)
    ) == (
        IntelligencePriorityLevel.HIGH,
        IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
    )


class _EventReader:
    def __init__(self, events):
        self.events = tuple(events)

    def list(self):
        return self.events


class _EvidenceReader:
    def __init__(self, evidence):
        self.evidence = tuple(evidence)

    def list(self):
        return self.evidence


class _PriorityWriter:
    def __init__(self):
        self.values = {}

    def list(self):
        return tuple(self.values.values())

    def add_if_absent(self, command):
        existing = self.values.get(command.event_id)
        if existing is not None:
            return existing, False
        priority = IntelligenceEventPriorityView(id=uuid4(), **command.model_dump())
        self.values[command.event_id] = priority
        return priority, True


class _Uow:
    def __init__(self, events, evidence):
        self.intelligence_events = _EventReader(events)
        self.intelligence_event_evidence = _EvidenceReader(evidence)
        self.intelligence_event_priorities = _PriorityWriter()
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.commit_count += 1


def test_priority_traceability_dry_run_and_idempotency() -> None:
    event = _event(IntelligenceEventType.INVESTOR_VIEW_CHANGE, signal_count=2)
    signals = (_link(event.id), _link(event.id))
    uow = _Uow((event,), signals)
    service = IntelligencePriorityService(lambda: uow)

    dry_run = service.dry_run()
    first = service.materialize()
    second = service.generate_many()

    assert dry_run.dry_run is True
    assert dry_run.created_count == 1
    assert dry_run.reused_count == 0
    assert dry_run.candidates[0].event_id == event.id
    assert dry_run.candidates[0].evidence_count == 2
    assert first.created_count == 1
    assert second.created_count == 0
    assert second.reused_count == 1
    assert second.duplicate_count == 0
    assert uow.commit_count == 2
    assert first.priorities[0].event_id == event.id
    assert first.priorities[0].evidence_count == len(signals)
    assert uow.intelligence_events.events == (event,)


def test_priority_repository_has_one_row_per_event(db_session) -> None:
    asset = Asset(name="Priority Asset", market="SH", symbol="600098")
    db_session.add(asset)
    db_session.flush()
    event_repository = IntelligenceEventRepository(db_session)
    event, _ = event_repository.add_if_absent(
        _event(IntelligenceEventType.CROSS_INVESTOR_DISCOVERY).model_copy(
            update={"asset_id": asset.id}
        )
    )
    repository = IntelligenceEventPriorityRepository(db_session)
    command = IntelligenceEventPriorityCreate(
        event_id=event.id,
        priority_level=IntelligencePriorityLevel.LOW,
        reason=IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
        evidence_count=1,
        created_at=NOW,
    )

    first, created = repository.add_if_absent(command)
    second, reused = repository.add_if_absent(command)
    db_session.commit()

    assert created is True
    assert reused is False
    assert first.id == second.id
    refreshed, refreshed_reused = repository.add_if_absent(
        command.model_copy(update={"evidence_count": 3})
    )
    db_session.commit()

    assert refreshed_reused is False
    assert refreshed.id == first.id
    assert refreshed.evidence_count == 3
    assert len(repository.list()) == 1
