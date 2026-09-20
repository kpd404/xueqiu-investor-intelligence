"""Deterministic fact-time Context comparison over existing artifacts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from config import (
    get_production_analysis_policy,
    get_production_thesis_comparison_policy,
)
from contracts import (
    FeedState,
    IntelligenceEventEvidenceView,
    SignalType,
    ThesisChangeView,
)
from intelligence.context.schemas import (
    ActivityContext,
    AttentionContext,
    ContextAssetIdentity,
    CrossInvestorContext,
    IntelligenceContextView,
    InvestorContext,
    ThesisContext,
    TimelineContext,
)
from intelligence.discovery.service import (
    DiscoveryAssetNotFoundError,
    IntelligenceDiscoveryService,
)
from intelligence.read_scope import AssetIntelligenceReadScope
from intelligence.schemas.discovery import IntelligenceDiscoveryCandidate


class _Reader(Protocol):
    def list(self): ...


class _ScopeReader:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def list(self) -> tuple[object, ...]:
        return self._values


class _ScopeAssetReader:
    def __init__(self, scope: AssetIntelligenceReadScope) -> None:
        self._scope = scope

    def list(self) -> tuple[object, ...]:
        return (self._scope.asset,)


class _ScopeThesisReader:
    def __init__(self, scope: AssetIntelligenceReadScope) -> None:
        self._scope = scope

    def list_effective_by_asset(self, asset_id, policy, comparison_version, *, as_of=None):
        if asset_id != self._scope.asset.asset_id:
            return []
        return list(self._scope.thesis_changes)


class _ScopeCrossReader:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def list_by_asset(self, asset_id):
        return [item for item in self._values if item.asset_id == asset_id]


class _ScopeContextUoW:
    def __init__(self, scope: AssetIntelligenceReadScope) -> None:
        self.intelligence_feed_items = _ScopeReader(scope.feed_items)
        self.intelligence_event_priorities = _ScopeReader(scope.priorities)
        self.intelligence_events = _ScopeReader(scope.events)
        self.intelligence_event_evidence = _ScopeReader(scope.event_evidence)
        self.signals = _ScopeReader(scope.signals)
        self.assets = _ScopeAssetReader(scope)
        self.thesis_changes = _ScopeThesisReader(scope)
        self.cross_investor_asset_snapshots = _ScopeCrossReader(scope.snapshots)
        self.cross_investor_asset_alignments = _ScopeCrossReader(scope.alignments)
        self.cross_investor_consensus_evidences = _ScopeCrossReader(scope.consensus_evidences)


class ThesisReader(Protocol):
    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: object,
        comparison_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]: ...


class AssetReader(Protocol):
    def list(self): ...


class CrossReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> list: ...


class IntelligenceContextUoW(Protocol):
    intelligence_feed_items: _Reader
    intelligence_event_priorities: _Reader
    intelligence_events: _Reader
    intelligence_event_evidence: _Reader
    signals: _Reader
    assets: AssetReader
    thesis_changes: ThesisReader
    cross_investor_asset_snapshots: CrossReader
    cross_investor_asset_alignments: CrossReader
    cross_investor_consensus_evidences: CrossReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


IntelligenceContextUoWFactory = Callable[[], IntelligenceContextUoW]


@dataclass(frozen=True, slots=True)
class ContextComparisonWindow:
    as_of: datetime
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime

    @classmethod
    def from_as_of(cls, as_of: datetime, days: int) -> ContextComparisonWindow:
        as_of = _normalize_time(as_of, "as_of")
        current_start = as_of - timedelta(days=days)
        return cls(
            as_of=as_of,
            current_start=current_start,
            current_end=as_of,
            previous_start=as_of - timedelta(days=days * 2),
            previous_end=current_start,
        )


class IntelligenceContextService:
    """Compare observed current/previous windows without inference."""

    def __init__(
        self,
        discovery_service: IntelligenceDiscoveryService,
        unit_of_work_factory: IntelligenceContextUoWFactory,
        *,
        context_window_days: int = 30,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        if context_window_days <= 0:
            raise ValueError("context_window_days must be positive")
        self._discovery_service = discovery_service
        self._unit_of_work_factory = unit_of_work_factory
        self._context_window_days = context_window_days
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
        *,
        context_window_days: int | None = None,
    ) -> IntelligenceContextService:
        from config import get_settings
        from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

        settings = get_settings()
        return cls(
            IntelligenceDiscoveryService.from_production(session_factory),
            lambda: SqlAlchemyIntelligenceFeedUnitOfWork(session_factory),
            context_window_days=(
                context_window_days
                if context_window_days is not None
                else settings.context_window_days
            ),
        )

    def get_asset_context(
        self,
        asset_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> IntelligenceContextView:
        candidate = self._discovery_service.get_candidate_by_asset(asset_id)
        window = self._window(as_of)
        if candidate is None:
            asset = self._discovery_service.get_asset_identity(asset_id)
            return self._empty_context(
                ContextAssetIdentity(
                    asset_id=asset.asset_id,
                    name=asset.name,
                    market=asset.market,
                    symbol=asset.symbol,
                ),
                window,
            )
        return self._get_candidate_context(candidate, window)

    def get_candidate_context(
        self,
        candidate: IntelligenceDiscoveryCandidate,
        *,
        as_of: datetime | None = None,
    ) -> IntelligenceContextView:
        return self._get_candidate_context(candidate, self._window(as_of))

    def get_scope_context(
        self,
        scope: AssetIntelligenceReadScope,
        candidate: IntelligenceDiscoveryCandidate | None,
        *,
        as_of: datetime | None = None,
    ) -> IntelligenceContextView:
        window = self._window(as_of or scope.as_of)
        if candidate is None:
            return self._empty_context(
                ContextAssetIdentity(
                    asset_id=scope.asset.asset_id,
                    name=scope.asset.name,
                    market=scope.asset.market,
                    symbol=scope.asset.symbol,
                ),
                window,
            )
        return self._project(_ScopeContextUoW(scope), candidate, window)

    def batch_get_context(
        self,
        candidates: Iterable[IntelligenceDiscoveryCandidate] | None = None,
        *,
        limit: int = 100,
        as_of: datetime | None = None,
    ) -> tuple[IntelligenceContextView, ...]:
        if candidates is None:
            candidates = self._discovery_service.get_candidates(limit=limit).items
        window = self._window(as_of)
        with self._unit_of_work_factory() as unit_of_work:
            return tuple(self._project(unit_of_work, candidate, window) for candidate in candidates)

    def _get_candidate_context(
        self,
        candidate: IntelligenceDiscoveryCandidate,
        window: ContextComparisonWindow,
    ) -> IntelligenceContextView:
        with self._unit_of_work_factory() as unit_of_work:
            return self._project(unit_of_work, candidate, window)

    def _project(
        self,
        unit_of_work: IntelligenceContextUoW,
        candidate: IntelligenceDiscoveryCandidate,
        window: ContextComparisonWindow,
    ) -> IntelligenceContextView:
        asset_id = candidate.asset.asset_id
        feed_items = [
            item
            for item in unit_of_work.intelligence_feed_items.list()
            if item.state == FeedState.ACTIVE and item.asset_id == asset_id
        ]
        priorities = {item.id: item for item in unit_of_work.intelligence_event_priorities.list()}
        events = {item.id: item for item in unit_of_work.intelligence_events.list()}
        signals = {item.id: item for item in unit_of_work.signals.list()}
        links_by_event: dict[UUID, list[IntelligenceEventEvidenceView]] = defaultdict(list)
        for link in unit_of_work.intelligence_event_evidence.list():
            links_by_event[link.event_id].append(link)

        current_event_ids: set[UUID] = set()
        previous_event_ids: set[UUID] = set()
        first_observed_at = None
        latest_observed_at = None
        for feed_item in feed_items:
            priority = priorities.get(feed_item.priority_id)
            if priority is None:
                raise ValueError(f"Priority not found for FeedItem: {feed_item.id}")
            event = events.get(priority.event_id)
            if event is None:
                raise ValueError(f"IntelligenceEvent not found for Priority: {priority.id}")
            if feed_item.asset_id != event.asset_id or feed_item.event_type != event.event_type:
                raise ValueError(f"FeedItem identity mismatch: {feed_item.id}")
            if feed_item.reason != priority.reason:
                raise ValueError(f"FeedItem reason mismatch: {feed_item.id}")
            event_links = links_by_event.get(event.id, [])
            if len(event_links) != priority.evidence_count:
                raise ValueError(f"Event evidence count mismatch: {event.id}")
            for link in event_links:
                signal = signals.get(link.signal_id)
                if signal is None:
                    raise ValueError(f"Signal not found for evidence: {link.id}")
                if signal.asset_id != asset_id:
                    raise ValueError(f"Signal asset mismatch: {link.id}")
            first_observed_at = (
                feed_item.observed_at
                if first_observed_at is None
                else min(first_observed_at, feed_item.observed_at)
            )
            latest_observed_at = (
                feed_item.observed_at
                if latest_observed_at is None
                else max(latest_observed_at, feed_item.observed_at)
            )
            if window.current_start <= feed_item.observed_at <= window.current_end:
                current_event_ids.add(event.id)
            elif window.previous_start <= feed_item.observed_at < window.previous_end:
                previous_event_ids.add(event.id)

        current_signals = self._signals_for_events(current_event_ids, links_by_event, signals)
        previous_signals = self._signals_for_events(previous_event_ids, links_by_event, signals)
        current_investors = {item.investor_id for item in current_signals if item.investor_id}
        previous_investors = {item.investor_id for item in previous_signals if item.investor_id}
        current_attention = {
            item.id for item in current_signals if item.signal_type == SignalType.NEW_ATTENTION
        }
        previous_attention = {
            item.id for item in previous_signals if item.signal_type == SignalType.NEW_ATTENTION
        }

        policy = get_production_analysis_policy().as_effective_policy()
        comparison_version = get_production_thesis_comparison_policy().active_analysis_version
        thesis_changes = unit_of_work.thesis_changes.list_effective_by_asset(
            asset_id,
            policy,
            comparison_version,
            as_of=window.as_of,
        )
        current_thesis = [
            change
            for change in thesis_changes
            if window.current_start <= change.effective_time <= window.current_end
        ]
        previous_thesis = [
            change
            for change in thesis_changes
            if window.previous_start <= change.effective_time < window.previous_end
        ]

        current_state = self._cross_state(unit_of_work, asset_id, window.current_end)
        historical_state = self._cross_state(unit_of_work, asset_id, window.previous_end)
        if current_state is not None and historical_state is not None:
            cross_limitations: list[str] = []
        else:
            cross_limitations = [
                "Cross-Investor state is unavailable for one or both comparison windows."
            ]

        limitations = [
            (
                f"Comparison uses current and previous "
                f"{self._context_window_days}-day observed-time windows."
            ),
            "Observed evidence only; no absence inference is made.",
            "Historical completeness is UNKNOWN.",
            "Available collection provenance does not establish historical completeness.",
            *cross_limitations,
        ]
        return IntelligenceContextView(
            asset=ContextAssetIdentity(
                asset_id=asset_id,
                name=candidate.asset.name,
                market=candidate.asset.market,
                symbol=candidate.asset.symbol,
            ),
            activity_context=ActivityContext(
                current_signal_count=len({item.id for item in current_signals}),
                previous_signal_count=len({item.id for item in previous_signals}),
                change_description=self._describe_change(
                    "signal activity",
                    len({item.id for item in current_signals}),
                    len({item.id for item in previous_signals}),
                ),
            ),
            investor_context=InvestorContext(
                current_investor_count=len(current_investors),
                previous_investor_count=len(previous_investors),
                new_investors=sorted(
                    current_investors - previous_investors, key=lambda value: value.int
                ),
                returning_investors=sorted(
                    current_investors & previous_investors, key=lambda value: value.int
                ),
            ),
            attention_context=AttentionContext(
                current_attention_count=len(current_attention),
                historical_attention_count=len(previous_attention),
                change_description=self._describe_change(
                    "attention evidence",
                    len(current_attention),
                    len(previous_attention),
                ),
            ),
            thesis_context=ThesisContext(
                current_thesis_changes=len(current_thesis),
                historical_thesis_changes=len(previous_thesis),
                direction_changes=sorted({change.change_type.value for change in current_thesis}),
            ),
            cross_investor_context=CrossInvestorContext(
                current_state=current_state,
                historical_state=historical_state,
            ),
            timeline_context=TimelineContext(
                first_observed_at=first_observed_at,
                latest_observed_at=latest_observed_at,
                current_window_start=window.current_start,
                current_window_end=window.current_end,
                previous_window_start=window.previous_start,
                previous_window_end=window.previous_end,
            ),
            limitations=limitations,
        )

    @staticmethod
    def _signals_for_events(event_ids, links_by_event, signals):
        return [
            signals[link.signal_id]
            for event_id in event_ids
            for link in links_by_event.get(event_id, [])
            if link.signal_id in signals
        ]

    @staticmethod
    def _cross_state(unit_of_work, asset_id: UUID, window_end: datetime) -> str | None:
        snapshots = [
            snapshot
            for snapshot in unit_of_work.cross_investor_asset_snapshots.list_by_asset(asset_id)
            if snapshot.window_end <= window_end
        ]
        if not snapshots:
            return None
        snapshot = max(
            snapshots,
            key=lambda item: (item.window_end, item.as_of, item.id.int),
        )
        alignments = [
            item
            for item in unit_of_work.cross_investor_asset_alignments.list_by_asset(asset_id)
            if item.source_snapshot_id == snapshot.id
        ]
        consensus = [
            item
            for item in unit_of_work.cross_investor_consensus_evidences.list_by_asset(asset_id)
            if item.source_snapshot_id == snapshot.id
        ]
        parts: list[str] = []
        if alignments:
            alignment = max(alignments, key=lambda item: (item.calculated_at, item.id.int))
            parts.append(f"alignment={alignment.directional_alignment_state.value}")
        if consensus:
            evidence = max(consensus, key=lambda item: (item.calculated_at, item.id.int))
            parts.append(f"consensus={evidence.consensus_state.value}")
        return "; ".join(parts) if parts else None

    def _window(self, as_of: datetime | None) -> ContextComparisonWindow:
        return ContextComparisonWindow.from_as_of(
            as_of or self._now_factory(),
            self._context_window_days,
        )

    @staticmethod
    def _describe_change(label: str, current: int, previous: int) -> str:
        if current > previous:
            return f"Observed {label} increased from {previous} to {current}."
        if current < previous:
            return f"Observed {label} decreased from {previous} to {current}."
        return f"Observed {label} remained at {current}."

    @staticmethod
    def _empty_context(
        asset: ContextAssetIdentity,
        window: ContextComparisonWindow,
    ) -> IntelligenceContextView:
        zero = "Observed evidence count is zero in both comparison windows."
        return IntelligenceContextView(
            asset=asset,
            activity_context=ActivityContext(
                current_signal_count=0,
                previous_signal_count=0,
                change_description=zero,
            ),
            investor_context=InvestorContext(
                current_investor_count=0,
                previous_investor_count=0,
            ),
            attention_context=AttentionContext(
                current_attention_count=0,
                historical_attention_count=0,
                change_description=zero,
            ),
            thesis_context=ThesisContext(
                current_thesis_changes=0,
                historical_thesis_changes=0,
            ),
            cross_investor_context=CrossInvestorContext(),
            timeline_context=TimelineContext(
                current_window_start=window.current_start,
                current_window_end=window.current_end,
                previous_window_start=window.previous_start,
                previous_window_end=window.previous_end,
            ),
            limitations=[
                "No ACTIVE DiscoveryCandidate source is available.",
                "Comparison window is explicit, but historical evidence is insufficient.",
                "Observed evidence only; no absence inference is made.",
                "Available collection provenance does not establish historical completeness.",
            ],
        )


def _normalize_time(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "ContextComparisonWindow",
    "DiscoveryAssetNotFoundError",
    "IntelligenceContextService",
]
