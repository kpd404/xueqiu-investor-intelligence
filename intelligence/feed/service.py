"""Project IntelligenceEvent priorities into user-consumable Feed items."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    FeedItem,
    FeedItemCreate,
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityView,
    IntelligenceEventView,
    IntelligenceFeedGenerationResult,
    IntelligencePriorityReason,
    SignalView,
)


class PriorityReader(Protocol):
    def list(self) -> tuple[IntelligenceEventPriorityView, ...]: ...


class EventReader(Protocol):
    def list(self) -> tuple[IntelligenceEventView, ...]: ...


class EvidenceReader(Protocol):
    def list(self) -> tuple[IntelligenceEventEvidenceView, ...]: ...


class SignalReader(Protocol):
    def list(self) -> tuple[SignalView, ...]: ...


class FeedWriter(Protocol):
    def list(self) -> tuple[FeedItem, ...]: ...

    def add_if_absent(self, command: FeedItemCreate) -> tuple[FeedItem, bool]: ...


class IntelligenceFeedUoW(Protocol):
    intelligence_event_priorities: PriorityReader
    intelligence_events: EventReader
    intelligence_event_evidence: EvidenceReader
    signals: SignalReader
    intelligence_feed_items: FeedWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


IntelligenceFeedUoWFactory = Callable[[], IntelligenceFeedUoW]


class IntelligenceFeedService:
    """Materialize one deterministic FeedItem for each qualifying Priority."""

    def __init__(self, unit_of_work_factory: IntelligenceFeedUoWFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(cls, session_factory: Callable[[], object]) -> IntelligenceFeedService:
        from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

        return cls(lambda: SqlAlchemyIntelligenceFeedUnitOfWork(session_factory))

    def dry_run(
        self,
        *,
        priority_ids: Iterable[UUID] | None = None,
    ) -> IntelligenceFeedGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work,
                priority_ids=priority_ids,
            )
            existing_by_priority = {
                item.priority_id: item for item in unit_of_work.intelligence_feed_items.list()
            }
            existing = tuple(
                existing_by_priority[candidate.priority_id]
                for candidate in candidates
                if candidate.priority_id in existing_by_priority
            )
        return IntelligenceFeedGenerationResult(
            candidates=candidates,
            items=existing,
            created_count=len(candidates) - len(existing),
            reused_count=len(existing),
            duplicate_count=0,
            dry_run=True,
        )

    def materialize(
        self,
        *,
        priority_ids: Iterable[UUID] | None = None,
    ) -> IntelligenceFeedGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work,
                priority_ids=priority_ids,
            )
            items: list[FeedItem] = []
            created_count = 0
            reused_count = 0
            for candidate in candidates:
                item, created = unit_of_work.intelligence_feed_items.add_if_absent(candidate)
                items.append(item)
                if created:
                    created_count += 1
                else:
                    reused_count += 1
            unit_of_work.commit()
        return IntelligenceFeedGenerationResult(
            candidates=candidates,
            items=tuple(items),
            created_count=created_count,
            reused_count=reused_count,
            duplicate_count=0,
            dry_run=False,
        )

    def generate(self, **kwargs) -> IntelligenceFeedGenerationResult:
        return self.materialize(**kwargs)

    def generate_many(self, **kwargs) -> IntelligenceFeedGenerationResult:
        return self.materialize(**kwargs)

    @classmethod
    def _candidates(
        cls,
        unit_of_work: IntelligenceFeedUoW,
        *,
        priority_ids: Iterable[UUID] | None,
    ) -> tuple[FeedItemCreate, ...]:
        allowed = frozenset(priority_ids) if priority_ids is not None else None
        events = {event.id: event for event in unit_of_work.intelligence_events.list()}
        links_by_event: dict[UUID, list[IntelligenceEventEvidenceView]] = defaultdict(list)
        for link in unit_of_work.intelligence_event_evidence.list():
            links_by_event[link.event_id].append(link)
        signals = {signal.id: signal for signal in unit_of_work.signals.list()}
        candidates: list[FeedItemCreate] = []
        for priority in unit_of_work.intelligence_event_priorities.list():
            if allowed is not None and priority.id not in allowed:
                continue
            event = events.get(priority.event_id)
            if event is None:
                raise ValueError(f"IntelligenceEvent not found for Priority: {priority.id}")
            links = links_by_event.get(event.id, [])
            source_signals = [
                signals[link.signal_id] for link in links if link.signal_id in signals
            ]
            if len(source_signals) != len(links):
                raise ValueError(f"Signal evidence is incomplete for IntelligenceEvent: {event.id}")
            if len(source_signals) != priority.evidence_count:
                raise ValueError(
                    f"Priority evidence count does not match Event evidence: {priority.id}"
                )
            candidates.append(
                FeedItemCreate(
                    priority_id=priority.id,
                    asset_id=event.asset_id,
                    event_type=event.event_type,
                    title=cls._title(priority.reason),
                    context=cls._context(source_signals),
                    reason=priority.reason,
                    observed_at=event.last_observed_at,
                    created_at=datetime.now(UTC),
                )
            )
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.observed_at,
                    item.event_type.value,
                    item.asset_id.int,
                    item.priority_id.int,
                ),
            )
        )

    @staticmethod
    def _title(reason: IntelligencePriorityReason) -> str:
        return {
            IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION: (
                "Multiple investors started paying attention"
            ),
            IntelligencePriorityReason.THESIS_ACCELERATION: "Multiple thesis changes were observed",
            IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY: (
                "Cross-investor attention was observed"
            ),
            IntelligencePriorityReason.CONSENSUS_STATE_CHANGE: (
                "A consensus state change was observed"
            ),
        }[reason]

    @staticmethod
    def _context(signals: list[SignalView]) -> dict[str, object]:
        source_identity = {(signal.source_type, signal.source_id) for signal in signals}
        return {
            "investor_count": len({signal.investor_id for signal in signals if signal.investor_id}),
            "signal_count": len(signals),
            "source_count": len(source_identity),
            "source_types": sorted({signal.source_type for signal in signals}),
        }


__all__ = ["IntelligenceFeedService", "IntelligenceFeedUoW"]
