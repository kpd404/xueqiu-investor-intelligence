"""Read, plan, and persist deterministic FeedItem lifecycle transitions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    FeedItem,
    FeedState,
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityView,
    IntelligenceEventType,
    IntelligenceEventView,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    SignalView,
)
from contracts.intelligence_feed import (
    THESIS_LIFECYCLE_CONTEXT_KEY,
    ThesisSourceFact,
    feed_display_context,
)
from intelligence.events.evidence import group_effective_thesis_evidence
from intelligence.feed.lifecycle.policy import FeedLifecyclePolicy, FeedLifecycleTransition
from intelligence.feed.lifecycle.thesis_baseline import (
    baseline_progress,
    checkpoint,
    parse_time,
    read_baseline,
)
from intelligence.feed.service import IntelligenceFeedService


class FeedItemLifecycleReader(Protocol):
    def list(self) -> tuple[FeedItem, ...]: ...


class FeedItemLifecycleWriter(FeedItemLifecycleReader, Protocol):
    def update_state(self, feed_item_id: UUID, state: FeedState) -> FeedItem: ...
    def update_thesis_lifecycle(
        self,
        expected: FeedItem,
        state: FeedState,
        baseline: dict[str, object],
    ) -> FeedItem: ...


class LifecyclePriorityReader(Protocol):
    def list(self) -> tuple[IntelligenceEventPriorityView, ...]: ...


class LifecycleEventReader(Protocol):
    def list(self) -> tuple[IntelligenceEventView, ...]: ...


class LifecycleEvidenceReader(Protocol):
    def list(self) -> tuple[IntelligenceEventEvidenceView, ...]: ...


class LifecycleSignalReader(Protocol):
    def list(self) -> tuple[SignalView, ...]: ...


class ThesisLifecycleReader(LifecycleSignalReader, Protocol):
    def list_with_facts(self) -> tuple[tuple[SignalView, ...], dict[UUID, ThesisSourceFact]]: ...
    def known_raw_event_ids(self) -> frozenset[UUID]: ...


class FeedLifecycleUoW(Protocol):
    intelligence_feed_items: FeedItemLifecycleWriter
    intelligence_event_priorities: LifecyclePriorityReader
    intelligence_events: LifecycleEventReader
    intelligence_event_evidence: LifecycleEvidenceReader
    signals: LifecycleSignalReader
    effective_thesis_signals: ThesisLifecycleReader

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
class FeedLifecycleSkip:
    """Diagnostic only: this retained historical item supplied no effective input."""

    feed_item_id: UUID
    event_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class ThesisLifecycleCheckpoint:
    expected: FeedItem
    to_state: FeedState
    baseline: dict[str, object]
    reason: str
    source_facts: tuple[ThesisSourceFact, ...] = ()


@dataclass(frozen=True, slots=True)
class FeedLifecyclePlan:
    """Read-only lifecycle plan produced before any state write."""

    evaluated_at: datetime
    current_counts: dict[FeedState, int]
    predicted_counts: dict[FeedState, int]
    transitions: tuple[FeedLifecycleTransition, ...]
    skipped: tuple[FeedLifecycleSkip, ...] = ()
    checkpoints: tuple[ThesisLifecycleCheckpoint, ...] = ()


@dataclass(frozen=True, slots=True)
class FeedLifecycleResult:
    """Dry-run or idempotent lifecycle execution result."""

    plan: FeedLifecyclePlan
    updated_count: int
    reused_count: int
    dry_run: bool
    baseline_updated_count: int = 0


class FeedLifecycleService:
    """Advance state and private Thesis checkpoints; upstream artifacts stay read-only."""

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
        now_factory: Callable[[], datetime] | None = None,
    ) -> FeedLifecycleService:
        from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

        return cls(
            lambda: SqlAlchemyIntelligenceFeedUnitOfWork(session_factory),
            policy=policy or FeedLifecyclePolicy.from_settings(),
            now_factory=now_factory,
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
        external_plan = plan is not None
        with self._unit_of_work_factory() as unit_of_work:
            if plan is None:
                plan = self._plan(unit_of_work, now=now)
            current_items = {item.id: item for item in unit_of_work.intelligence_feed_items.list()}
            actions = plan.checkpoints
            if external_plan:
                checkpoint_ids = {action.expected.id for action in actions}
                for transition in plan.transitions:
                    item = current_items.get(transition.feed_item_id)
                    if (
                        item is not None
                        and item.event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE
                        and item.id not in checkpoint_ids
                    ):
                        raise ValueError("Thesis lifecycle transition requires a fact checkpoint")
            if actions and external_plan:
                # Re-plan relevant Thesis items at the execution clock. A saved
                # plan is never authority for source validity or baseline progress.
                fresh = self._plan(
                    unit_of_work,
                    now=self._now_factory(),
                    thesis_ids=frozenset(action.expected.id for action in actions),
                )
                current_actions = {action.expected.id: action for action in fresh.checkpoints}
                checked = []
                for action in actions:
                    current = current_items.get(action.expected.id)
                    stored = current.context.get(THESIS_LIFECYCLE_CONTEXT_KEY) if current else None
                    # Already committed checkpoints are idempotent, including
                    # harmless changes to diagnostic evaluation timestamps.
                    if (
                        current is not None
                        and current.state is action.to_state
                        and isinstance(stored, dict)
                    ):
                        if baseline_progress(stored) == baseline_progress(action.baseline):
                            checked.append(action)
                            continue
                    proposal = current_actions.get(action.expected.id)
                    if (
                        current != action.expected
                        or proposal is None
                        or proposal.to_state is not action.to_state
                        or proposal.reason != action.reason
                        or proposal.source_facts != action.source_facts
                    ):
                        raise ValueError(
                            "Thesis lifecycle plan no longer matches evidence, window or baseline"
                        )
                    checked.append(proposal)
                actions = tuple(checked)
                plan = replace(plan, evaluated_at=fresh.evaluated_at, checkpoints=actions)
            updated_count = 0
            reused_count = 0
            baseline_updated_count = 0
            action_ids = {action.expected.id for action in actions}
            for action in actions:
                current = current_items[action.expected.id]
                old_baseline = current.context.get(THESIS_LIFECYCLE_CONTEXT_KEY)
                if (
                    current.state is action.to_state
                    and isinstance(old_baseline, dict)
                    and baseline_progress(old_baseline) == baseline_progress(action.baseline)
                ):
                    reused_count += int(action.expected.state is not action.to_state)
                    continue
                unit_of_work.intelligence_feed_items.update_thesis_lifecycle(
                    current,
                    action.to_state,
                    action.baseline,
                )
                baseline_updated_count += 1
                updated_count += int(current.state is not action.to_state)
            for transition in plan.transitions:
                if transition.feed_item_id in action_ids:
                    continue
                item = current_items.get(transition.feed_item_id)
                if item is None:
                    raise ValueError(
                        f"FeedItem not found for transition: {transition.feed_item_id}"
                    )
                self._policy.validate_transition(
                    transition.from_state, transition.to_state, event_type=item.event_type
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
            if updated_count or baseline_updated_count:
                unit_of_work.commit()
        return FeedLifecycleResult(
            plan=plan,
            updated_count=updated_count,
            reused_count=reused_count,
            dry_run=False,
            baseline_updated_count=baseline_updated_count,
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
        thesis_ids: frozenset[UUID] | None = None,
    ) -> FeedLifecyclePlan:
        evaluated_at = now or self._now_factory()
        evaluated_at = self._normalize_time(evaluated_at, "now")
        feed_items = unit_of_work.intelligence_feed_items.list()
        if thesis_ids is not None:
            feed_items = tuple(item for item in feed_items if item.id in thesis_ids)
        priorities = {
            priority.id: priority for priority in unit_of_work.intelligence_event_priorities.list()
        }
        events = {event.id: event for event in unit_of_work.intelligence_events.list()}
        signals = {signal.id: signal for signal in unit_of_work.signals.list()}
        links = unit_of_work.intelligence_event_evidence.list()
        if thesis_ids is not None:
            selected_events = {
                priorities[item.priority_id].event_id
                for item in feed_items
                if item.priority_id in priorities
            }
            links = tuple(link for link in links if link.event_id in selected_events)
        links_by_event: dict[UUID, list[IntelligenceEventEvidenceView]] = {}
        for link in links:
            if link.event_id not in events:
                raise ValueError(f"IntelligenceEvent not found for evidence: {link.id}")
            if (
                link.signal_id not in signals
                and events[link.event_id].event_type
                is not IntelligenceEventType.INVESTOR_VIEW_CHANGE
            ):
                raise ValueError(f"Signal not found for evidence: {link.id}")
            links_by_event.setdefault(link.event_id, []).append(link)

        effective_thesis = {}
        source_facts = {}
        known_raw_ids = frozenset()
        if any(
            priority.event_id in events
            and events[priority.event_id].event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE
            for item in feed_items
            if (priority := priorities.get(item.priority_id)) is not None
        ):
            effective_views, source_facts = unit_of_work.effective_thesis_signals.list_with_facts()
            effective_thesis = group_effective_thesis_evidence(
                events.values(), links, effective_views
            )
            known_raw_ids = unit_of_work.effective_thesis_signals.known_raw_event_ids()

        transitions: list[FeedLifecycleTransition] = []
        skipped: list[FeedLifecycleSkip] = []
        checkpoints: list[ThesisLifecycleCheckpoint] = []
        for feed_item in feed_items:
            priority = priorities.get(feed_item.priority_id)
            if priority is None:
                raise ValueError(f"Priority not found for FeedItem: {feed_item.id}")
            event = events.get(priority.event_id)
            if event is None:
                raise ValueError(f"IntelligenceEvent not found for Priority: {priority.id}")
            is_thesis = event.event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE
            source_signals = effective_thesis.get(event.id, ()) if is_thesis else ()
            if is_thesis and not source_signals:
                skipped.append(
                    FeedLifecycleSkip(feed_item.id, event.id, "NO_EFFECTIVE_THESIS_EVIDENCE")
                )
                continue
            if feed_item.asset_id != event.asset_id:
                raise ValueError(f"FeedItem asset does not match Event: {feed_item.id}")
            if feed_item.event_type != event.event_type:
                raise ValueError(f"FeedItem event type does not match Event: {feed_item.id}")
            policy_feed = feed_item
            if is_thesis:
                if len(source_signals) != priority.evidence_count:
                    raise ValueError(
                        "Priority evidence count does not match effective Thesis evidence: "
                        f"{priority.id}"
                    )
                if (
                    priority.reason is not IntelligencePriorityReason.THESIS_CHANGE_OBSERVED
                    or priority.priority_level is not IntelligencePriorityLevel.MEDIUM
                ):
                    raise ValueError(
                        f"Thesis Priority must be refreshed before Lifecycle: {priority.id}"
                    )
                observed_at = max(signal.observed_at for signal in source_signals)
                expected_projection = {
                    "reason": priority.reason,
                    "title": IntelligenceFeedService._title(priority.reason),
                    "context": IntelligenceFeedService._context(list(source_signals)),
                    "observed_at": observed_at,
                }
                for field, expected in expected_projection.items():
                    actual = (
                        feed_display_context(feed_item.context)
                        if field == "context"
                        else getattr(feed_item, field)
                    )
                    if actual != expected:
                        raise ValueError(
                            f"Thesis Feed {field} must be refreshed before Lifecycle: "
                            f"{feed_item.id}"
                        )
                policy_feed = feed_item.model_copy(update={"observed_at": observed_at})
            else:
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
                policy_feed,
                priority,
                event,
                now=evaluated_at,
            )
            if is_thesis and feed_item.state is not FeedState.RESOLVED:
                baseline = read_baseline(feed_item, event.id)
                facts = tuple(
                    sorted(
                        {
                            source_facts[signal.id].raw_event_id: source_facts[signal.id]
                            for signal in source_signals
                            if signal.id in source_facts
                        }.values(),
                        key=lambda fact: (fact.published_time, fact.raw_event_id.int),
                    )
                )
                if len(facts) == 0:
                    raise ValueError("Thesis baseline requires traceable RawEvent facts")
                supporting = ()
                reason = "THESIS_BASELINE_OBSERVED"
                if feed_item.state is FeedState.STALE:
                    if baseline is None or baseline.get("reentry_after") is None:
                        reason = "LEGACY_STALE_BASELINE_INITIALIZED"
                        skipped.append(FeedLifecycleSkip(feed_item.id, event.id, reason))
                    elif baseline["high_watermark"] is not None:
                        high_water = parse_time(baseline["high_watermark"])
                        if baseline.get("reentry_after") is not None:
                            high_water = max(high_water, parse_time(baseline["reentry_after"]))
                        supporting = tuple(
                            fact
                            for fact in facts
                            if str(fact.raw_event_id) not in baseline["known_raw_event_ids"]
                            and fact.published_time > high_water
                            and evaluated_at - self._policy.activation_window
                            <= fact.published_time
                            <= evaluated_at
                        )
                        times_match = all(
                            signal.id in source_facts
                            and signal.observed_at == source_facts[signal.id].published_time
                            for signal in source_signals
                        )
                        if (
                            supporting
                            and times_match
                            and observed_at <= evaluated_at
                            and all(fact.published_time <= evaluated_at for fact in facts)
                        ):
                            transition = FeedLifecycleTransition(
                                feed_item.id,
                                FeedState.STALE,
                                FeedState.ACTIVE,
                                ("NEW_EFFECTIVE_THESIS_FACT",),
                                supporting,
                            )
                if transition is not None:
                    reason = transition.reasons[0]
                if transition is not None or feed_item.state is FeedState.STALE:
                    new_baseline = checkpoint(
                        feed_item,
                        event.id,
                        baseline,
                        facts,
                        known_raw_ids,
                        evaluated_at,
                        (transition.from_state.value, transition.to_state.value, reason)
                        if transition
                        else None,
                        supporting if supporting else facts,
                    )
                    if new_baseline != baseline:
                        checkpoints.append(
                            ThesisLifecycleCheckpoint(
                                feed_item,
                                transition.to_state if transition else feed_item.state,
                                new_baseline,
                                reason,
                                supporting if supporting else facts,
                            )
                        )
            if transition is not None:
                self._policy.validate_transition(
                    transition.from_state, transition.to_state, event_type=event.event_type
                )
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
            skipped=tuple(skipped),
            checkpoints=tuple(checkpoints),
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
    "FeedLifecycleSkip",
    "FeedLifecycleUoW",
]
