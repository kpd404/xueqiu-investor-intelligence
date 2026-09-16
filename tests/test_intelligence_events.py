from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    IntelligenceEventCreate,
    IntelligenceEventEvidenceCreate,
    IntelligenceEventEvidenceView,
    IntelligenceEventState,
    IntelligenceEventType,
    SignalCreate,
    SignalSeverity,
    SignalState,
    SignalType,
    SignalView,
)
from database.models import Asset
from database.repositories.intelligence_event_evidence import (
    IntelligenceEventEvidenceRepository,
)
from database.repositories.intelligence_events import IntelligenceEventRepository
from intelligence.events import IntelligenceEventAggregator
from signal_engine.repository import SignalRepository

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def _signal(
    asset_id: UUID,
    signal_type: SignalType,
    *,
    investor_id: UUID | None = None,
    offset: int = 0,
    state: SignalState = SignalState.ACTIVE,
) -> SignalView:
    source_type = {
        SignalType.NEW_ATTENTION: "AttentionOccurrence",
        SignalType.THESIS_CHANGE: "ThesisChange",
        SignalType.CROSS_INVESTOR_ALIGNMENT: "CrossInvestorAssetAlignment",
        SignalType.CONSENSUS_CHANGE: "CrossInvestorConsensusEvidence",
    }[signal_type]
    return SignalView(
        id=uuid4(),
        asset_id=asset_id,
        investor_id=investor_id,
        signal_type=signal_type,
        state=state,
        severity=SignalSeverity.LOW,
        source_type=source_type,
        source_id=uuid4(),
        created_at=NOW,
        observed_at=NOW + timedelta(hours=offset),
        metadata={},
    )


def test_intelligence_event_contract_validates_range_and_lifecycle() -> None:
    event = IntelligenceEventCreate(
        asset_id=uuid4(),
        event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
        first_observed_at=NOW,
        last_observed_at=NOW,
    )

    assert event.state is IntelligenceEventState.ACTIVE
    with pytest.raises(ValidationError):
        IntelligenceEventCreate(
            asset_id=event.asset_id,
            event_type=event.event_type,
            first_observed_at=NOW + timedelta(days=1),
            last_observed_at=NOW,
        )


def test_aggregation_rules_are_deterministic_and_type_specific() -> None:
    asset_one, asset_two, asset_three = uuid4(), uuid4(), uuid4()
    investor_one, investor_two = uuid4(), uuid4()
    signals = (
        _signal(
            asset_one,
            SignalType.NEW_ATTENTION,
            investor_id=investor_one,
            offset=1,
        ),
        _signal(
            asset_one,
            SignalType.NEW_ATTENTION,
            investor_id=investor_two,
            offset=2,
        ),
        _signal(asset_two, SignalType.NEW_ATTENTION, investor_id=investor_one, offset=3),
        _signal(asset_two, SignalType.THESIS_CHANGE, investor_id=investor_one, offset=4),
        _signal(asset_three, SignalType.CROSS_INVESTOR_ALIGNMENT, offset=5),
        _signal(asset_three, SignalType.CONSENSUS_CHANGE, offset=6),
        _signal(
            asset_three,
            SignalType.THESIS_CHANGE,
            investor_id=investor_two,
            offset=7,
            state=SignalState.RESOLVED,
        ),
    )

    candidates = IntelligenceEventAggregator._candidates(
        signals,
        asset_ids=None,
        event_types=None,
    )

    by_key = {(item.command.event_type, item.command.asset_id): item for item in candidates}
    assert (IntelligenceEventType.ASSET_ACTIVITY_SPIKE, asset_one) in by_key
    assert (IntelligenceEventType.ASSET_ACTIVITY_SPIKE, asset_two) not in by_key
    assert (IntelligenceEventType.INVESTOR_VIEW_CHANGE, asset_two) in by_key
    assert (IntelligenceEventType.CROSS_INVESTOR_DISCOVERY, asset_three) in by_key
    assert (IntelligenceEventType.CONSENSUS_STATE_CHANGE, asset_three) in by_key
    activity = by_key[(IntelligenceEventType.ASSET_ACTIVITY_SPIKE, asset_one)]
    assert activity.command.first_observed_at < activity.command.last_observed_at
    assert set(activity.signal_ids) == {signals[0].id, signals[1].id}


class _SignalReader:
    def __init__(self, signals: tuple[SignalView, ...]):
        self.signals = signals

    def list(self):
        return self.signals


class _EventWriter:
    def __init__(self):
        self.values = {}

    def get_by_identity(self, event_type, asset_id):
        return self.values.get((event_type, asset_id))

    def add_if_absent(self, command):
        key = (command.event_type.value, command.asset_id)
        existing = self.values.get(key)
        if existing is not None:
            return existing, False
        from contracts import IntelligenceEventView

        event = IntelligenceEventView(id=uuid4(), **command.model_dump())
        self.values[key] = event
        return event, True


class _EvidenceWriter:
    def __init__(self):
        self.values = {}

    def get_by_identity(self, event_id, signal_id):
        return self.values.get((event_id, signal_id))

    def list_by_event(self, event_id):
        return tuple(
            value
            for (current_event_id, _), value in self.values.items()
            if current_event_id == event_id
        )

    def add_if_absent(self, command):
        key = (command.event_id, command.signal_id)
        existing = self.values.get(key)
        if existing is not None:
            return existing, False
        evidence = IntelligenceEventEvidenceView(id=uuid4(), **command.model_dump())
        self.values[key] = evidence
        return evidence, True


class _Uow:
    def __init__(self, signals):
        self.signals = _SignalReader(signals)
        self.intelligence_events = _EventWriter()
        self.intelligence_event_evidence = _EvidenceWriter()
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.commit_count += 1


def test_event_and_evidence_materialization_is_idempotent_and_traceable() -> None:
    asset_id = uuid4()
    signals = (
        _signal(asset_id, SignalType.NEW_ATTENTION, investor_id=uuid4(), offset=1),
        _signal(asset_id, SignalType.NEW_ATTENTION, investor_id=uuid4(), offset=2),
    )
    uow = _Uow(signals)
    aggregator = IntelligenceEventAggregator(lambda: uow)

    dry_run = aggregator.dry_run()
    first = aggregator.aggregate()
    second = aggregator.aggregate_many()

    assert dry_run.dry_run is True
    assert dry_run.created_event_count == 1
    assert dry_run.created_evidence_count == 2
    assert uow.commit_count == 2
    assert first.created_event_count == 1
    assert first.created_evidence_count == 2
    assert second.created_event_count == 0
    assert second.reused_event_count == 1
    assert second.created_evidence_count == 0
    assert second.reused_evidence_count == 2
    assert second.duplicate_count == 0
    first.events[0]
    links = tuple(uow.intelligence_event_evidence.values.values())
    assert {link.signal_id for link in links} == {signal.id for signal in signals}
    assert {link.signal_id for link in links} != {signal.source_id for signal in signals}
    assert all(signal.state is SignalState.ACTIVE for signal in signals)


def test_event_and_evidence_repositories_preserve_unique_links(db_session) -> None:
    asset = Asset(name="Event Asset", market="SH", symbol="600099")
    db_session.add(asset)
    db_session.flush()
    signal_command = SignalCreate(
        asset_id=asset.id,
        signal_type=SignalType.CONSENSUS_CHANGE,
        source_type="CrossInvestorConsensusEvidence",
        source_id=uuid4(),
        created_at=NOW,
        observed_at=NOW,
    )
    signal, _ = SignalRepository(db_session).add_if_absent(signal_command)
    event_command = IntelligenceEventCreate(
        asset_id=asset.id,
        event_type=IntelligenceEventType.CONSENSUS_STATE_CHANGE,
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    event_repository = IntelligenceEventRepository(db_session)
    evidence_repository = IntelligenceEventEvidenceRepository(db_session)
    event, created = event_repository.add_if_absent(event_command)
    link = IntelligenceEventEvidenceCreate(event_id=event.id, signal_id=signal.id)
    first_link, first_created = evidence_repository.add_if_absent(link)
    second_link, second_created = evidence_repository.add_if_absent(link)
    db_session.commit()

    assert created is True
    assert first_created is True
    assert second_created is False
    assert first_link.id == second_link.id
    assert len(evidence_repository.list_by_event(event.id)) == 1
