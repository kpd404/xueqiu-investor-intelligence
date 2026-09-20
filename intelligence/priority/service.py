"""Build observation-priority rows from existing Intelligence Events."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityCreate,
    IntelligenceEventPriorityView,
    IntelligenceEventState,
    IntelligenceEventType,
    IntelligenceEventView,
    IntelligencePriorityGenerationResult,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
)
from intelligence.policies.activity import has_multi_investor_activity


class IntelligenceEventReader(Protocol):
    def list(self) -> tuple[IntelligenceEventView, ...]: ...


class IntelligenceEventEvidenceReader(Protocol):
    def list(self) -> tuple[IntelligenceEventEvidenceView, ...]: ...


class IntelligencePriorityReaderWriter(Protocol):
    def list(self) -> tuple[IntelligenceEventPriorityView, ...]: ...

    def add_if_absent(
        self,
        command: IntelligenceEventPriorityCreate,
    ) -> tuple[IntelligenceEventPriorityView, bool]: ...


class IntelligencePriorityUoW(Protocol):
    intelligence_events: IntelligenceEventReader
    intelligence_event_evidence: IntelligenceEventEvidenceReader
    intelligence_event_priorities: IntelligencePriorityReaderWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


IntelligencePriorityUoWFactory = Callable[[], IntelligencePriorityUoW]


class IntelligencePriorityService:
    """Materialize one deterministic priority classification per event."""

    def __init__(self, unit_of_work_factory: IntelligencePriorityUoWFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(cls, session_factory: Callable[[], object]) -> IntelligencePriorityService:
        from database.unit_of_work import SqlAlchemyIntelligencePriorityUnitOfWork

        return cls(lambda: SqlAlchemyIntelligencePriorityUnitOfWork(session_factory))

    def dry_run(
        self,
        *,
        event_ids: Iterable[UUID] | None = None,
        reasons: Iterable[IntelligencePriorityReason] | None = None,
    ) -> IntelligencePriorityGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work.intelligence_events.list(),
                unit_of_work.intelligence_event_evidence.list(),
                event_ids=event_ids,
                reasons=reasons,
            )
            existing_by_event = {
                priority.event_id: priority
                for priority in unit_of_work.intelligence_event_priorities.list()
            }
            existing = tuple(
                existing_by_event[candidate.event_id]
                for candidate in candidates
                if candidate.event_id in existing_by_event
            )
        return IntelligencePriorityGenerationResult(
            candidates=candidates,
            priorities=existing,
            created_count=len(candidates) - len(existing),
            reused_count=len(existing),
            duplicate_count=0,
            dry_run=True,
        )

    def materialize(
        self,
        *,
        event_ids: Iterable[UUID] | None = None,
        reasons: Iterable[IntelligencePriorityReason] | None = None,
    ) -> IntelligencePriorityGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work.intelligence_events.list(),
                unit_of_work.intelligence_event_evidence.list(),
                event_ids=event_ids,
                reasons=reasons,
            )
            priorities: list[IntelligenceEventPriorityView] = []
            created_count = 0
            reused_count = 0
            for candidate in candidates:
                priority, created = unit_of_work.intelligence_event_priorities.add_if_absent(
                    candidate
                )
                priorities.append(priority)
                if created:
                    created_count += 1
                else:
                    reused_count += 1
            unit_of_work.commit()
        return IntelligencePriorityGenerationResult(
            candidates=candidates,
            priorities=tuple(priorities),
            created_count=created_count,
            reused_count=reused_count,
            duplicate_count=0,
            dry_run=False,
        )

    def generate(self, **kwargs) -> IntelligencePriorityGenerationResult:
        return self.materialize(**kwargs)

    def generate_many(self, **kwargs) -> IntelligencePriorityGenerationResult:
        return self.materialize(**kwargs)

    @classmethod
    def _candidates(
        cls,
        events: Iterable[IntelligenceEventView],
        evidence: Iterable[IntelligenceEventEvidenceView],
        *,
        event_ids: Iterable[UUID] | None,
        reasons: Iterable[IntelligencePriorityReason] | None,
    ) -> tuple[IntelligenceEventPriorityCreate, ...]:
        allowed_events = frozenset(event_ids) if event_ids is not None else None
        allowed_reasons = frozenset(reasons) if reasons is not None else None
        evidence_counts: dict[UUID, int] = {}
        for link in evidence:
            evidence_counts[link.event_id] = evidence_counts.get(link.event_id, 0) + 1

        candidates: list[IntelligenceEventPriorityCreate] = []
        for event in events:
            if event.state is not IntelligenceEventState.ACTIVE:
                continue
            if allowed_events is not None and event.id not in allowed_events:
                continue
            classification = cls._classify(event)
            if classification is None:
                continue
            level, reason = classification
            if allowed_reasons is not None and reason not in allowed_reasons:
                continue
            evidence_count = evidence_counts.get(event.id, 0)
            if evidence_count < 1:
                continue
            candidates.append(
                IntelligenceEventPriorityCreate(
                    event_id=event.id,
                    priority_level=level,
                    reason=reason,
                    evidence_count=evidence_count,
                    created_at=datetime.now(UTC),
                )
            )
        return tuple(
            sorted(
                candidates,
                key=lambda value: (value.created_at, value.reason.value, value.event_id.int),
            )
        )

    @staticmethod
    def _classify(
        event: IntelligenceEventView,
    ) -> tuple[IntelligencePriorityLevel, IntelligencePriorityReason] | None:
        metadata = event.metadata
        if event.event_type is IntelligenceEventType.ASSET_ACTIVITY_SPIKE:
            investor_count = len(metadata.get("investor_ids", ()))
            if has_multi_investor_activity(investor_count, threshold=3):
                return (
                    IntelligencePriorityLevel.HIGH,
                    IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION,
                )
            return None
        if event.event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE:
            if int(metadata.get("signal_count", 0)) >= 2:
                return (
                    IntelligencePriorityLevel.MEDIUM,
                    IntelligencePriorityReason.THESIS_ACCELERATION,
                )
            return None
        if event.event_type is IntelligenceEventType.CROSS_INVESTOR_DISCOVERY:
            return (
                IntelligencePriorityLevel.LOW,
                IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
            )
        if event.event_type is IntelligenceEventType.CONSENSUS_STATE_CHANGE:
            return (
                IntelligencePriorityLevel.HIGH,
                IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
            )
        return None


__all__ = ["IntelligencePriorityService", "IntelligencePriorityUoW"]
