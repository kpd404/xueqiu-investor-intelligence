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
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityView,
    IntelligenceEventView,
    SignalView,
    ThesisChangeView,
)


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

        return AssetIntelligenceReadScope(
            asset=asset_identity,
            as_of=as_of,
            signals=signals,
            events=events,
            event_evidence=event_evidence,
            priorities=priorities,
            feed_items=feed_items,
            thesis_changes=thesis_changes,
            attention_occurrences=attention_occurrences,
            snapshots=snapshots,
            alignments=alignments,
            consensus_evidences=consensus_evidences,
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
