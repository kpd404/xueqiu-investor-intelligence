"""Aggregate immutable Signal evidence into traceable Intelligence Events."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    IntelligenceEventCreate,
    IntelligenceEventEvidenceCreate,
    IntelligenceEventGenerationResult,
    IntelligenceEventType,
    SignalState,
    SignalType,
    SignalView,
)


class SignalReader(Protocol):
    def list(self) -> tuple[SignalView, ...]: ...


class IntelligenceEventWriter(Protocol):
    def get_by_identity(
        self,
        event_type: str,
        asset_id: UUID,
    ): ...

    def add_if_absent(self, command: IntelligenceEventCreate): ...


class IntelligenceEventEvidenceWriter(Protocol):
    def get_by_identity(self, event_id: UUID, signal_id: UUID): ...

    def add_if_absent(self, command: IntelligenceEventEvidenceCreate): ...


class IntelligenceEventAggregationUoW(Protocol):
    signals: SignalReader
    intelligence_events: IntelligenceEventWriter
    intelligence_event_evidence: IntelligenceEventEvidenceWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


IntelligenceEventAggregationUoWFactory = Callable[[], IntelligenceEventAggregationUoW]


@dataclass(frozen=True)
class _AggregationCandidate:
    command: IntelligenceEventCreate
    signal_ids: tuple[UUID, ...]


class IntelligenceEventAggregator:
    """Build and persist deterministic event aggregates from active Signals."""

    def __init__(self, unit_of_work_factory: IntelligenceEventAggregationUoWFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(cls, session_factory: Callable[[], object]) -> IntelligenceEventAggregator:
        from database.unit_of_work import SqlAlchemyIntelligenceEventUnitOfWork

        return cls(lambda: SqlAlchemyIntelligenceEventUnitOfWork(session_factory))

    def dry_run(
        self,
        *,
        asset_ids: Iterable[UUID] | None = None,
        event_types: Iterable[IntelligenceEventType] | None = None,
    ) -> IntelligenceEventGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work.signals.list(),
                asset_ids=asset_ids,
                event_types=event_types,
            )
            events = []
            reused_events = 0
            created_evidence = 0
            reused_evidence = 0
            for candidate in candidates:
                existing = unit_of_work.intelligence_events.get_by_identity(
                    candidate.command.event_type.value,
                    candidate.command.asset_id,
                )
                if existing is None:
                    created_event = True
                else:
                    created_event = False
                    events.append(existing)
                    reused_events += 1
                if created_event:
                    created_evidence += len(candidate.signal_ids)
                else:
                    existing_evidence = {
                        link.signal_id
                        for link in unit_of_work.intelligence_event_evidence.list_by_event(
                            existing.id
                        )
                    }
                    created_evidence += sum(
                        signal_id not in existing_evidence for signal_id in candidate.signal_ids
                    )
                    reused_evidence += sum(
                        signal_id in existing_evidence for signal_id in candidate.signal_ids
                    )
        return IntelligenceEventGenerationResult(
            candidates=tuple(candidate.command for candidate in candidates),
            events=tuple(events),
            created_event_count=len(candidates) - reused_events,
            reused_event_count=reused_events,
            created_evidence_count=created_evidence,
            reused_evidence_count=reused_evidence,
            duplicate_count=0,
            dry_run=True,
        )

    def aggregate(
        self,
        *,
        asset_ids: Iterable[UUID] | None = None,
        event_types: Iterable[IntelligenceEventType] | None = None,
    ) -> IntelligenceEventGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work.signals.list(),
                asset_ids=asset_ids,
                event_types=event_types,
            )
            events = []
            created_event_count = 0
            reused_event_count = 0
            created_evidence_count = 0
            reused_evidence_count = 0
            for candidate in candidates:
                event, created = unit_of_work.intelligence_events.add_if_absent(candidate.command)
                events.append(event)
                if created:
                    created_event_count += 1
                else:
                    reused_event_count += 1
                for signal_id in candidate.signal_ids:
                    _, evidence_created = unit_of_work.intelligence_event_evidence.add_if_absent(
                        IntelligenceEventEvidenceCreate(event_id=event.id, signal_id=signal_id)
                    )
                    if evidence_created:
                        created_evidence_count += 1
                    else:
                        reused_evidence_count += 1
            unit_of_work.commit()
        return IntelligenceEventGenerationResult(
            candidates=tuple(candidate.command for candidate in candidates),
            events=tuple(events),
            created_event_count=created_event_count,
            reused_event_count=reused_event_count,
            created_evidence_count=created_evidence_count,
            reused_evidence_count=reused_evidence_count,
            duplicate_count=0,
            dry_run=False,
        )

    def aggregate_many(
        self,
        *,
        asset_ids: Iterable[UUID] | None = None,
        event_types: Iterable[IntelligenceEventType] | None = None,
    ) -> IntelligenceEventGenerationResult:
        return self.aggregate(asset_ids=asset_ids, event_types=event_types)

    @classmethod
    def _candidates(
        cls,
        signals: Iterable[SignalView],
        *,
        asset_ids: Iterable[UUID] | None,
        event_types: Iterable[IntelligenceEventType] | None,
    ) -> tuple[_AggregationCandidate, ...]:
        allowed_assets = frozenset(asset_ids) if asset_ids is not None else None
        allowed_types = (
            frozenset(event_types) if event_types is not None else frozenset(IntelligenceEventType)
        )
        groups: dict[tuple[IntelligenceEventType, UUID], list[SignalView]] = defaultdict(list)
        for signal in signals:
            if signal.state is not SignalState.ACTIVE:
                continue
            if allowed_assets is not None and signal.asset_id not in allowed_assets:
                continue
            event_type = cls._event_type_for_signal(signal.signal_type)
            if event_type is None or event_type not in allowed_types:
                continue
            groups[(event_type, signal.asset_id)].append(signal)

        candidates: list[_AggregationCandidate] = []
        for (event_type, asset_id), grouped in groups.items():
            ordered = tuple(
                sorted(grouped, key=lambda value: (value.observed_at, value.source_id.int))
            )
            if event_type is IntelligenceEventType.ASSET_ACTIVITY_SPIKE:
                investor_ids = {signal.investor_id for signal in ordered if signal.investor_id}
                if len(ordered) < 2 or len(investor_ids) < 2:
                    continue
            signal_ids = tuple(signal.id for signal in ordered)
            metadata = {
                "aggregation_rule": cls._rule_for_event_type(event_type),
                "signal_count": len(signal_ids),
                "signal_ids": [str(signal_id) for signal_id in signal_ids],
                "investor_ids": sorted(
                    {str(signal.investor_id) for signal in ordered if signal.investor_id}
                ),
                "source_signal_types": sorted({signal.signal_type.value for signal in ordered}),
            }
            candidates.append(
                _AggregationCandidate(
                    command=IntelligenceEventCreate(
                        asset_id=asset_id,
                        event_type=event_type,
                        first_observed_at=ordered[0].observed_at,
                        last_observed_at=ordered[-1].observed_at,
                        metadata=metadata,
                    ),
                    signal_ids=signal_ids,
                )
            )
        return tuple(
            sorted(
                candidates,
                key=lambda value: (
                    value.command.first_observed_at,
                    value.command.event_type.value,
                    value.command.asset_id.int,
                ),
            )
        )

    @staticmethod
    def _event_type_for_signal(signal_type: SignalType) -> IntelligenceEventType | None:
        return {
            SignalType.NEW_ATTENTION: IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
            SignalType.THESIS_CHANGE: IntelligenceEventType.INVESTOR_VIEW_CHANGE,
            SignalType.CROSS_INVESTOR_ALIGNMENT: IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
            SignalType.CONSENSUS_CHANGE: IntelligenceEventType.CONSENSUS_STATE_CHANGE,
        }.get(signal_type)

    @staticmethod
    def _rule_for_event_type(event_type: IntelligenceEventType) -> str:
        return {
            IntelligenceEventType.ASSET_ACTIVITY_SPIKE: "multiple_new_attention_investors",
            IntelligenceEventType.INVESTOR_VIEW_CHANGE: "existing_thesis_change",
            IntelligenceEventType.CROSS_INVESTOR_DISCOVERY: "existing_cross_investor_alignment",
            IntelligenceEventType.CONSENSUS_STATE_CHANGE: "existing_consensus_signal",
        }[event_type]


__all__ = ["IntelligenceEventAggregationUoW", "IntelligenceEventAggregator"]
