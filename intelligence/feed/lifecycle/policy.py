"""Deterministic FeedItem lifecycle policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from contracts import (
    FeedItem,
    FeedState,
    IntelligenceEventPriorityView,
    IntelligenceEventType,
    IntelligenceEventView,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
)


@dataclass(frozen=True, slots=True)
class FeedLifecycleTransition:
    """One allowed state transition selected by the lifecycle policy."""

    feed_item_id: UUID
    from_state: FeedState
    to_state: FeedState
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeedLifecyclePolicy:
    """Configuration and rules for FeedItem state advancement.

    The policy has no persistence side effects. It only evaluates the current
    FeedItem, its Priority/Event context, and the supplied evaluation time.
    """

    activation_window: timedelta = timedelta(days=30)
    stale_window: timedelta = timedelta(days=30)

    def __post_init__(self) -> None:
        if self.activation_window < timedelta(0):
            raise ValueError("activation_window must not be negative")
        if self.stale_window <= timedelta(0):
            raise ValueError("stale_window must be positive")

    @classmethod
    def from_settings(cls, settings: object | None = None) -> FeedLifecyclePolicy:
        if settings is None:
            from config import get_settings

            settings = get_settings()
        return cls(
            activation_window=timedelta(days=settings.feed_activation_window_days),
            stale_window=timedelta(days=settings.feed_stale_window_days),
        )

    def activation_reasons(
        self,
        feed_item: FeedItem,
        priority: IntelligenceEventPriorityView,
        event: IntelligenceEventView,
        *,
        now: datetime,
    ) -> tuple[str, ...]:
        """Return all deterministic reasons that activate a NEW FeedItem."""

        now = self._normalize_time(now, "now")
        reasons: list[str] = []
        if priority.priority_level == IntelligencePriorityLevel.HIGH:
            reasons.append("HIGH_PRIORITY")
        if event.event_type == IntelligenceEventType.CONSENSUS_STATE_CHANGE:
            reasons.append("CONSENSUS_EVENT")
        if event.event_type == IntelligenceEventType.CROSS_INVESTOR_DISCOVERY:
            reasons.append("CROSS_INVESTOR_EVENT")
        if priority.reason == IntelligencePriorityReason.THESIS_ACCELERATION:
            reasons.append("THESIS_ACCELERATION")
        if feed_item.observed_at >= now - self.activation_window:
            reasons.append("WITHIN_ACTIVATION_WINDOW")
        return tuple(reasons)

    def select_transition(
        self,
        feed_item: FeedItem,
        priority: IntelligenceEventPriorityView,
        event: IntelligenceEventView,
        *,
        now: datetime,
    ) -> FeedLifecycleTransition | None:
        """Select at most one lifecycle transition for one FeedItem."""

        now = self._normalize_time(now, "now")
        if feed_item.state == FeedState.NEW:
            reasons = self.activation_reasons(feed_item, priority, event, now=now)
            if reasons:
                return FeedLifecycleTransition(
                    feed_item_id=feed_item.id,
                    from_state=FeedState.NEW,
                    to_state=FeedState.ACTIVE,
                    reasons=reasons,
                )
            return None
        if feed_item.state == FeedState.ACTIVE and feed_item.observed_at < now - self.stale_window:
            return FeedLifecycleTransition(
                feed_item_id=feed_item.id,
                from_state=FeedState.ACTIVE,
                to_state=FeedState.STALE,
                reasons=("STALE_WINDOW",),
            )
        return None

    @staticmethod
    def validate_transition(from_state: FeedState, to_state: FeedState) -> None:
        if from_state == to_state:
            return
        allowed = {
            (FeedState.NEW, FeedState.ACTIVE),
            (FeedState.ACTIVE, FeedState.STALE),
            (FeedState.ACTIVE, FeedState.RESOLVED),
        }
        if (from_state, to_state) not in allowed:
            raise ValueError(f"invalid FeedItem transition: {from_state} -> {to_state}")

    @staticmethod
    def _normalize_time(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)


__all__ = ["FeedLifecyclePolicy", "FeedLifecycleTransition"]
