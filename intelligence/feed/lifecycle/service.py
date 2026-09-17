"""Read, plan, and persist deterministic FeedItem lifecycle transitions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    FeedItem,
    FeedState,
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityView,
    IntelligenceEventView,
    SignalView,
)
from intelligence.feed.lifecycle.policy import FeedLifecyclePolicy, FeedLifecycleTransition


class FeedItemLifecycleReader(Protocol):
    def list(self) -> tuple[FeedItem, ...]: ...


class FeedItemLifecycleWriter(FeedItemLifecycleReader, Protocol):
    def update_state(self, feed_item_id: UUID, state: FeedState) -> FeedItem: ...


class LifecyclePriorityReader(Protocol):
    def list(self) -> tuple[IntelligenceEventPriorityView, ...]: ...


class LifecycleEventReader(Protocol):
    def list(self) -> tuple[IntelligenceEventView, ...]: ...


class LifecycleEvidenceReader(Protocol):
    def list(self) -> tuple[IntelligenceEventEvidenceView, ...]: ...


class LifecycleSignalReader(Protocol):
    def list(self) -> tuple[SignalView, ...]: ...


class FeedLifecycleUoW(Protocol):
    intelligence_feed_items: FeedItemLifecycleWriter
    intelligence_event_priorities: LifecyclePriorityReader
    intelligence_events: LifecycleEventReader
    intelligence_event_evidence: LifecycleEvidenceReader
    signals: LifecycleSignalReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


FeedLifecycleUoWFactory = Callable[[], FeedLifecycleUoW]


@dataclass(frozen=True, slots=True)
class FeedLifecyclePlan:
    """Read-only lifecycle plan produced before any state write."""

    evaluated_at: datetime
    current_counts: dict[FeedState, int]
    predicted_counts: dict[FeedState, int]
    transitions: tuple[FeedLifecycleTransition, ...]


@dataclass(frozen=True, slots=True)
class FeedLifecycleResult:
    """Dry-run or idempotent lifecycle execution result."""

    plan: FeedLifecyclePlan
    updated_count: int
    reused_count: int
    dry_run: bool


class FeedLifecycleService:
    """Advance only FeedItem.state; all upstream artifacts remain read-only."""

    def __init__(
        self,
        unit_of_work_factory: FeedLifecycleUoWFactory,
        *,
        policy: FeedLifecyclePolicy | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._policy = policy or FeedLifecyclePolicy()
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
        *,
        policy: FeedLifecyclePolicy | None = None,
    ) -> FeedLifecycleService:
        from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

        return cls(
            lambda: SqlAlchemyIntelligenceFeedUnitOfWork(session_factory),
            policy=policy or FeedLifecyclePolicy.from_settings(),
        )

    @property
    def policy(self) -> FeedLifecyclePolicy:
        return self._policy

    def dry_run(self, *, now: datetime | None = None) -> FeedLifecycleResult:
        with self._unit_of_work_factory() as unit_of_work:
            plan = self._plan(unit_of_work, now=now)
        return FeedLifecycleResult(
            plan=plan,
            updated_count=len(plan.transitions),
            reused_count=0,
            dry_run=True,
        )

    def apply(
        self,
        *,
        now: datetime | None = None,
        plan: FeedLifecyclePlan | None = None,
    ) -> FeedLifecycleResult:
        if now is not None and plan is not None:
            raise ValueError("pass either now or plan, not both")
        with self._unit_of_work_factory() as unit_of_work:
            if plan is None:
                plan = self._plan(unit_of_work, now=now)
            current_items = {item.id: item for item in unit_of_work.intelligence_feed_items.list()}
            updated_count = 0
            reused_count = 0
            for transition in plan.transitions:
                item = current_items.get(transition.feed_item_id)
                if item is None:
                    raise ValueError(
                        f"FeedItem not found for transition: {transition.feed_item_id}"
                    )
                if item.state == transition.from_state:
                    unit_of_work.intelligence_feed_items.update_state(
                        transition.feed_item_id,
                        transition.to_state,
                    )
                    updated_count += 1
                elif item.state == transition.to_state:
                    reused_count += 1
                else:
                    raise ValueError(
                        "FeedItem state changed outside the planned transition: "
                        f"{transition.feed_item_id}"
                    )
            if updated_count:
                unit_of_work.commit()
        return FeedLifecycleResult(
            plan=plan,
            updated_count=updated_count,
            reused_count=reused_count,
            dry_run=False,
        )

    def run(
        self,
        *,
        now: datetime | None = None,
        plan: FeedLifecyclePlan | None = None,
    ) -> FeedLifecycleResult:
        return self.apply(now=now, plan=plan)

    def _plan(
        self,
        unit_of_work: FeedLifecycleUoW,
        *,
        now: datetime | None,
    ) -> FeedLifecyclePlan:
        evaluated_at = now or self._now_factory()
        evaluated_at = self._normalize_time(evaluated_at, "now")
        feed_items = unit_of_work.intelligence_feed_items.list()
        priorities = {
            priority.id: priority for priority in unit_of_work.intelligence_event_priorities.list()
        }
        events = {event.id: event for event in unit_of_work.intelligence_events.list()}
        signals = {signal.id: signal for signal in unit_of_work.signals.list()}
        links = unit_of_work.intelligence_event_evidence.list()
        links_by_event: dict[UUID, list[IntelligenceEventEvidenceView]] = {}
        for link in links:
            if link.event_id not in events:
                raise ValueError(f"IntelligenceEvent not found for evidence: {link.id}")
            if link.signal_id not in signals:
                raise ValueError(f"Signal not found for evidence: {link.id}")
            links_by_event.setdefault(link.event_id, []).append(link)

        transitions: list[FeedLifecycleTransition] = []
        for feed_item in feed_items:
            priority = priorities.get(feed_item.priority_id)
            if priority is None:
                raise ValueError(f"Priority not found for FeedItem: {feed_item.id}")
            event = events.get(priority.event_id)
            if event is None:
                raise ValueError(f"IntelligenceEvent not found for Priority: {priority.id}")
            if feed_item.asset_id != event.asset_id:
                raise ValueError(f"FeedItem asset does not match Event: {feed_item.id}")
            if feed_item.event_type != event.event_type:
                raise ValueError(f"FeedItem event type does not match Event: {feed_item.id}")
            if feed_item.reason != priority.reason:
                raise ValueError(f"FeedItem reason does not match Priority: {priority.id}")
            event_links = links_by_event.get(event.id, [])
            if len(event_links) != priority.evidence_count:
                raise ValueError(
                    f"Priority evidence count does not match Event evidence: {priority.id}"
                )
            for link in event_links:
                signal = signals[link.signal_id]
                if signal.asset_id != event.asset_id:
                    raise ValueError(f"Signal asset does not match Event evidence: {link.id}")
            transition = self._policy.select_transition(
                feed_item,
                priority,
                event,
                now=evaluated_at,
            )
            if transition is not None:
                self._policy.validate_transition(transition.from_state, transition.to_state)
                transitions.append(transition)

        current_counts = Counter(item.state for item in feed_items)
        predicted_counts = Counter(current_counts)
        for transition in transitions:
            predicted_counts[transition.from_state] -= 1
            predicted_counts[transition.to_state] += 1
        return FeedLifecyclePlan(
            evaluated_at=evaluated_at,
            current_counts={state: current_counts.get(state, 0) for state in FeedState},
            predicted_counts={state: predicted_counts.get(state, 0) for state in FeedState},
            transitions=tuple(transitions),
        )

    @staticmethod
    def _normalize_time(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)


__all__ = [
    "FeedLifecyclePlan",
    "FeedLifecycleResult",
    "FeedLifecycleService",
    "FeedLifecycleUoW",
]
