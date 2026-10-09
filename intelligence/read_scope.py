"""Shared, immutable, Asset-scoped read inputs for Product composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_production_thesis_comparison_policy,
)
from contracts import (
    AttentionOccurrenceView,
    CrossInvestorAssetAlignmentView,
    CrossInvestorAssetSnapshotView,
    CrossInvestorConsensusEvidenceView,
    FeedItem,
    FeedState,
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityView,
    IntelligenceEventType,
    IntelligenceEventView,
    SignalType,
    SignalView,
    ThesisChangeView,
)
from contracts.intelligence_feed import feed_display_context
from intelligence.events.evidence import (
    CrossDirectionEvidenceReader,
    group_effective_thesis_evidence,
)
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService


@dataclass(frozen=True, slots=True)
class AssetReadIdentity:
    asset_id: UUID
    name: str
    market: str
    symbol: str


@dataclass(frozen=True, slots=True)
class AssetIntelligenceReadScope:
    """Canonical, read-only inputs for one listing-level Asset."""

    asset: AssetReadIdentity
    as_of: datetime
    signals: tuple[SignalView, ...]
    events: tuple[IntelligenceEventView, ...]
    event_evidence: tuple[IntelligenceEventEvidenceView, ...]
    priorities: tuple[IntelligenceEventPriorityView, ...]
    feed_items: tuple[FeedItem, ...]
    thesis_changes: tuple[ThesisChangeView, ...]
    attention_occurrences: tuple[AttentionOccurrenceView, ...]
    snapshots: tuple[CrossInvestorAssetSnapshotView, ...]
    alignments: tuple[CrossInvestorAssetAlignmentView, ...]
    consensus_evidences: tuple[CrossInvestorConsensusEvidenceView, ...]
    context_evidence: dict[UUID, tuple[tuple[SignalView, ...], frozenset[UUID]]] | None = None
    context_cross_sources: tuple[tuple, tuple, tuple] | None = None

    def __post_init__(self) -> None:
        asset_id = self.asset.asset_id
        asset_bound = (
            *self.signals,
            *self.events,
            *self.feed_items,
            *self.thesis_changes,
            *self.attention_occurrences,
            *self.snapshots,
            *self.alignments,
            *self.consensus_evidences,
        )
        if any(item.asset_id != asset_id for item in asset_bound):
            raise ValueError("Asset read scope contains a cross-listing artifact")

        event_ids = {item.id for item in self.events}
        signal_ids = {item.id for item in self.signals}
        priority_ids = {item.id for item in self.priorities}
        if any(
            link.event_id not in event_ids or link.signal_id not in signal_ids
            for link in self.event_evidence
        ):
            raise ValueError("Asset read scope contains orphan Event evidence")
        if any(item.event_id not in event_ids for item in self.priorities):
            raise ValueError("Asset read scope contains orphan Priority")
        if any(item.priority_id not in priority_ids for item in self.feed_items):
            raise ValueError("Asset read scope contains orphan FeedItem")

    @property
    def events_by_id(self) -> dict[UUID, IntelligenceEventView]:
        return {item.id: item for item in self.events}

    @property
    def priorities_by_id(self) -> dict[UUID, IntelligenceEventPriorityView]:
        return {item.id: item for item in self.priorities}

    @property
    def signals_by_id(self) -> dict[UUID, SignalView]:
        return {item.id: item for item in self.signals}

    @property
    def evidence_by_event(self) -> dict[UUID, tuple[IntelligenceEventEvidenceView, ...]]:
        grouped: dict[UUID, list[IntelligenceEventEvidenceView]] = {}
        for link in self.event_evidence:
            grouped.setdefault(link.event_id, []).append(link)
        return {
            event_id: tuple(sorted(links, key=lambda item: (item.signal_id.int, item.id.int)))
            for event_id, links in grouped.items()
        }


class AssetReader(Protocol):
    def get(self, asset_id: UUID): ...


class SignalReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> tuple[SignalView, ...]: ...


class EventReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> tuple[IntelligenceEventView, ...]: ...


class EvidenceReader(Protocol):
    def list_by_event_ids(
        self,
        event_ids: tuple[UUID, ...],
    ) -> tuple[IntelligenceEventEvidenceView, ...]: ...


class PriorityReader(Protocol):
    def list_by_event_ids(
        self,
        event_ids: tuple[UUID, ...],
    ) -> tuple[IntelligenceEventPriorityView, ...]: ...


class FeedReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> tuple[FeedItem, ...]: ...


class _AssetArtifactReader(Protocol):
    def list_by_asset(self, asset_id: UUID): ...


class AssetIntelligenceReadUoW(Protocol):
    assets: AssetReader
    signals: SignalReader
    intelligence_events: EventReader
    intelligence_event_evidence: EvidenceReader
    intelligence_event_priorities: PriorityReader
    intelligence_feed_items: FeedReader
    thesis_changes: object
    attention_occurrences: object
    cross_investor_asset_snapshots: _AssetArtifactReader
    cross_investor_asset_alignments: _AssetArtifactReader
    cross_investor_consensus_evidences: _AssetArtifactReader
    effective_thesis_signals: object
    effective_cross_signals: CrossDirectionEvidenceReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


AssetIntelligenceReadUoWFactory = Callable[[], AssetIntelligenceReadUoW]


class AssetIntelligenceReadScopeNotFoundError(LookupError):
    """Raised when the requested listing-level Asset does not exist."""


class AssetIntelligenceReadScopeLoader:
    """Load one bounded read scope without producing Intelligence semantics."""

    def __init__(
        self,
        unit_of_work_factory: AssetIntelligenceReadUoWFactory,
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
    ) -> AssetIntelligenceReadScopeLoader:
        from database.unit_of_work import SqlAlchemyAssetIntelligenceReadUnitOfWork

        return cls(lambda: SqlAlchemyAssetIntelligenceReadUnitOfWork(session_factory))

    def load(
        self,
        asset_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> AssetIntelligenceReadScope:
        as_of = self._normalize_time(as_of or self._now_factory())
        analysis_policy = get_production_analysis_policy().as_effective_policy()
        attention_policy = get_production_attention_policy_version()
        comparison_version = get_production_thesis_comparison_policy().active_analysis_version

        with self._unit_of_work_factory() as unit_of_work:
            asset = unit_of_work.assets.get(asset_id)
            if asset is None:
                raise AssetIntelligenceReadScopeNotFoundError(f"asset not found: {asset_id}")
            asset_identity = AssetReadIdentity(
                asset_id=asset.id,
                name=asset.name,
                market=asset.market,
                symbol=asset.symbol,
            )
            signals = unit_of_work.signals.list_by_asset(asset_id)
            events = unit_of_work.intelligence_events.list_by_asset(asset_id)
            event_ids = tuple(item.id for item in events)
            event_evidence = unit_of_work.intelligence_event_evidence.list_by_event_ids(event_ids)
            priorities = unit_of_work.intelligence_event_priorities.list_by_event_ids(event_ids)
            feed_items = unit_of_work.intelligence_feed_items.list_by_asset(asset_id)
            groups = prepare_context_evidence(
                unit_of_work, events, event_evidence, signals, feed_items, priorities
            )
            accepted_ids = {
                event_id: {signal.id for signal in values}
                for event_id, (values, _voters) in groups.items()
            }
            consumed_links = tuple(
                link
                for link in event_evidence
                if link.event_id not in groups or link.signal_id in accepted_ids[link.event_id]
            )
            priorities_by_id = {priority.id: priority for priority in priorities}
            events_by_id = {event.id: event for event in events}
            kept_feeds = []
            for feed in feed_items:
                priority = priorities_by_id.get(feed.priority_id)
                if priority is None:
                    raise ValueError(f"Priority not found for FeedItem: {feed.id}")
                group = groups.get(priority.event_id)
                if feed.state is FeedState.ACTIVE and group is not None:
                    if not group[0]:
                        continue
                    event = events_by_id.get(priority.event_id)
                    if event is None:
                        raise ValueError(f"Event not found for Context Priority: {priority.id}")
                    validate_context_projection(feed, priority, event, *group)
                kept_feeds.append(feed)
            corrected = {
                signal.id: signal for group, _voters in groups.values() for signal in group
            }
            signals = tuple(corrected.get(signal.id, signal) for signal in signals)
            thesis_changes = tuple(
                unit_of_work.thesis_changes.list_effective_by_asset(
                    asset_id,
                    analysis_policy,
                    comparison_version,
                    as_of=as_of,
                )
            )
            attention_occurrences = tuple(
                unit_of_work.attention_occurrences.list_effective_by_asset(
                    asset_id,
                    analysis_policy,
                    attention_policy,
                    as_of=as_of,
                )
            )
            snapshots = tuple(unit_of_work.cross_investor_asset_snapshots.list_by_asset(asset_id))
            alignments = tuple(unit_of_work.cross_investor_asset_alignments.list_by_asset(asset_id))
            consensus_evidences = tuple(
                unit_of_work.cross_investor_consensus_evidences.list_by_asset(asset_id)
            )
            context_signals = [signal for values, _voters in groups.values() for signal in values]
            alignment_ids = {
                s.source_id
                for s in context_signals
                if s.signal_type is SignalType.CROSS_INVESTOR_ALIGNMENT
            }
            consensus_ids = {
                s.source_id for s in context_signals if s.signal_type is SignalType.CONSENSUS_CHANGE
            }
            context_consensus = tuple(c for c in consensus_evidences if c.id in consensus_ids)
            alignment_ids.update(c.source_alignment_id for c in context_consensus)
            context_alignments = tuple(a for a in alignments if a.id in alignment_ids)
            snapshot_ids = {a.source_snapshot_id for a in context_alignments} | {
                c.source_snapshot_id for c in context_consensus
            }
            context_snapshots = tuple(s for s in snapshots if s.id in snapshot_ids)

        return AssetIntelligenceReadScope(
            asset=asset_identity,
            as_of=as_of,
            signals=signals,
            events=events,
            event_evidence=consumed_links,
            priorities=priorities,
            feed_items=tuple(kept_feeds),
            thesis_changes=thesis_changes,
            attention_occurrences=attention_occurrences,
            snapshots=snapshots,
            alignments=alignments,
            consensus_evidences=consensus_evidences,
            context_evidence=groups,
            context_cross_sources=(context_snapshots, context_alignments, context_consensus),
        )

    @staticmethod
    def _normalize_time(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value.astimezone(UTC)


__all__ = [
    "AssetIntelligenceReadScope",
    "AssetIntelligenceReadScopeLoader",
    "AssetIntelligenceReadScopeNotFoundError",
    "AssetReadIdentity",
]


def prepare_context_evidence(unit_of_work, events, links, signals, feeds, priorities):
    """Only coordinate existing source readers; keep unsupported Event types raw."""
    types = {
        IntelligenceEventType.INVESTOR_VIEW_CHANGE,
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        IntelligenceEventType.CONSENSUS_STATE_CHANGE,
    }
    priorities = {priority.id: priority for priority in priorities}
    active_events = {
        priorities[feed.priority_id].event_id
        for feed in feeds
        if feed.state is FeedState.ACTIVE and feed.priority_id in priorities
    }
    targets = [event for event in events if event.event_type in types and event.id in active_events]
    groups = {event.id: ((), frozenset()) for event in targets}
    if any(event.event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE for event in targets):
        thesis = group_effective_thesis_evidence(
            targets, links, unit_of_work.effective_thesis_signals.list()
        )
        groups.update(
            {
                event_id: (values, frozenset(signal.investor_id for signal in values))
                for event_id, values in thesis.items()
            }
        )
    cross = [
        event
        for event in targets
        if event.event_type is not IntelligenceEventType.INVESTOR_VIEW_CHANGE
    ]
    if cross:
        groups.update(unit_of_work.effective_cross_signals.group_by_events(cross, links, signals))
    return groups


def validate_context_projection(feed, priority, event, signals, voters):
    """Require already refreshed projections, not a read-side repair."""
    if feed.asset_id != event.asset_id or feed.event_type is not event.event_type:
        raise ValueError(f"Context Feed identity mismatch: {feed.id}")
    if len(signals) != priority.evidence_count:
        raise ValueError(f"Context effective evidence count mismatch: {priority.id}")
    if (priority.priority_level, priority.reason) != IntelligencePriorityService._classify(event):
        raise ValueError(f"Context Priority must be refreshed: {priority.id}")
    context = (
        IntelligenceFeedService._context(signals)
        if event.event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE
        else IntelligenceFeedService._cross_context(signals, voters)
    )
    expected = {
        "reason": priority.reason,
        "title": IntelligenceFeedService._title(priority.reason),
        "context": context,
        "observed_at": max(signal.observed_at for signal in signals),
    }
    for field, value in expected.items():
        actual = feed_display_context(feed.context) if field == "context" else getattr(feed, field)
        if actual != value:
            raise ValueError(f"Context Feed {field} must be refreshed: {feed.id}")
