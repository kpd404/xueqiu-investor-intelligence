"""Batch, deterministic query service for Discovery candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
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
    IntelligencePriorityReason,
    SignalView,
)
from intelligence.schemas.discovery import (
    DiscoveryActivitySummary,
    DiscoveryAssetIdentity,
    DiscoveryEvidenceSummary,
    IntelligenceDiscoveryCandidate,
    IntelligenceDiscoveryListResponse,
)


class FeedItemReader(Protocol):
    def list(self) -> tuple[FeedItem, ...]: ...


class PriorityReader(Protocol):
    def list(self) -> tuple[IntelligenceEventPriorityView, ...]: ...


class EventReader(Protocol):
    def list(self) -> tuple[IntelligenceEventView, ...]: ...


class EvidenceReader(Protocol):
    def list(self) -> tuple[IntelligenceEventEvidenceView, ...]: ...


class SignalReader(Protocol):
    def list(self) -> tuple[SignalView, ...]: ...


class AssetReader(Protocol):
    def list(self): ...


class IntelligenceDiscoveryQueryUoW(Protocol):
    """Read-only repositories required by the Discovery projection."""

    intelligence_feed_items: FeedItemReader
    intelligence_event_priorities: PriorityReader
    intelligence_events: EventReader
    intelligence_event_evidence: EvidenceReader
    signals: SignalReader
    assets: AssetReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


IntelligenceDiscoveryQueryUoWFactory = Callable[[], IntelligenceDiscoveryQueryUoW]


class DiscoveryAssetNotFoundError(LookupError):
    """Raised when an explicitly requested Asset does not exist."""


_DISCOVERY_REASONS: dict[IntelligenceEventType, str] = {
    IntelligenceEventType.ASSET_ACTIVITY_SPIKE: "MULTI_INVESTOR_ACTIVITY",
    IntelligenceEventType.INVESTOR_VIEW_CHANGE: "THESIS_ACTIVITY",
    IntelligenceEventType.CROSS_INVESTOR_DISCOVERY: "CROSS_INVESTOR_ACTIVITY",
    IntelligenceEventType.CONSENSUS_STATE_CHANGE: "CONSENSUS_ACTIVITY",
}


class _AssetAccumulator:
    def __init__(self, asset_id: UUID) -> None:
        self.asset_id = asset_id
        self.investor_ids: set[UUID] = set()
        self.signal_ids: set[UUID] = set()
        self.event_ids: set[UUID] = set()
        self.feed_ids: set[UUID] = set()
        self.event_types: set[IntelligenceEventType] = set()
        self.priority_reasons: set[IntelligencePriorityReason] = set()
        self.discovery_reasons: set[str] = set()
        self.latest_observed_at = None


class IntelligenceDiscoveryService:
    """Project ACTIVE FeedItems into Asset-grouped discovery candidates.

    This service intentionally does not treat NEW FeedItems as ACTIVE. Feed
    lifecycle transitions belong to the Feed layer; silently widening the
    state set here would change the discovery contract and hide stale data.
    """

    def __init__(self, unit_of_work_factory: IntelligenceDiscoveryQueryUoWFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
    ) -> IntelligenceDiscoveryService:
        from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

        return cls(lambda: SqlAlchemyIntelligenceFeedUnitOfWork(session_factory))

    def get_candidates(
        self,
        *,
        limit: int = 50,
        asset_id: UUID | None = None,
        event_type: IntelligenceEventType | None = None,
    ) -> IntelligenceDiscoveryListResponse:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        with self._unit_of_work_factory() as unit_of_work:
            assets = {asset.id: asset for asset in unit_of_work.assets.list()}
            if asset_id is not None and asset_id not in assets:
                raise DiscoveryAssetNotFoundError(f"asset not found: {asset_id}")

            priorities = {
                priority.id: priority
                for priority in unit_of_work.intelligence_event_priorities.list()
            }
            events = {event.id: event for event in unit_of_work.intelligence_events.list()}
            signals = {signal.id: signal for signal in unit_of_work.signals.list()}
            links_by_event: dict[UUID, list[IntelligenceEventEvidenceView]] = defaultdict(list)
            for link in unit_of_work.intelligence_event_evidence.list():
                links_by_event[link.event_id].append(link)

            accumulators: dict[UUID, _AssetAccumulator] = {}
            for feed_item in unit_of_work.intelligence_feed_items.list():
                # V0 is deliberately strict: only the explicit ACTIVE state is
                # consumable by Discovery. NEW is not an implicit synonym.
                if feed_item.state != FeedState.ACTIVE:
                    continue
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
                    raise ValueError(f"FeedItem reason does not match Priority: {feed_item.id}")
                if event_type is not None and event.event_type != event_type:
                    continue
                if feed_item.asset_id not in assets:
                    raise ValueError(f"Asset not found for FeedItem: {feed_item.id}")
                links = links_by_event.get(event.id, [])
                if len(links) != priority.evidence_count:
                    raise ValueError(
                        f"Priority evidence count does not match Event evidence: {priority.id}"
                    )

                accumulator = accumulators.setdefault(
                    feed_item.asset_id,
                    _AssetAccumulator(feed_item.asset_id),
                )
                accumulator.event_ids.add(event.id)
                accumulator.feed_ids.add(feed_item.id)
                accumulator.event_types.add(event.event_type)
                accumulator.priority_reasons.add(priority.reason)
                accumulator.discovery_reasons.add(_DISCOVERY_REASONS[event.event_type])
                if (
                    accumulator.latest_observed_at is None
                    or feed_item.observed_at > accumulator.latest_observed_at
                ):
                    accumulator.latest_observed_at = feed_item.observed_at

                for link in links:
                    signal = signals.get(link.signal_id)
                    if signal is None:
                        raise ValueError(f"Signal not found for Event evidence: {link.id}")
                    if signal.asset_id != event.asset_id:
                        raise ValueError(f"Signal asset does not match Event evidence: {link.id}")
                    accumulator.signal_ids.add(signal.id)
                    if signal.investor_id is not None:
                        accumulator.investor_ids.add(signal.investor_id)

            candidates = tuple(
                self._to_candidate(accumulator, assets[asset_id])
                for asset_id, accumulator in accumulators.items()
            )

        projected = tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    -candidate.evidence_summary.latest_observed_at.timestamp(),
                    candidate.asset_identity.name,
                    candidate.asset_identity.market,
                    candidate.asset_identity.symbol,
                    candidate.asset_id.int,
                ),
            )
        )
        if asset_id is not None:
            projected = tuple(
                candidate for candidate in projected if candidate.asset_id == asset_id
            )
        total = len(projected)
        items = projected[:limit]
        return IntelligenceDiscoveryListResponse(
            items=items,
            total=total,
            limit=limit,
            has_more=total > len(items),
        )

    def get_asset_candidate(
        self,
        asset_id: UUID,
        *,
        event_type: IntelligenceEventType | None = None,
    ) -> IntelligenceDiscoveryCandidate | None:
        response = self.get_candidates(limit=1, asset_id=asset_id, event_type=event_type)
        return response.items[0] if response.items else None

    @staticmethod
    def _to_candidate(
        accumulator: _AssetAccumulator,
        asset: object,
    ) -> IntelligenceDiscoveryCandidate:
        latest_observed_at = accumulator.latest_observed_at
        if latest_observed_at is None:
            raise ValueError(f"Discovery accumulator has no observed time: {accumulator.asset_id}")
        return IntelligenceDiscoveryCandidate(
            candidate_id=accumulator.asset_id,
            asset_id=accumulator.asset_id,
            asset_identity=DiscoveryAssetIdentity(
                asset_id=asset.id,
                name=asset.name,
                market=asset.market,
                symbol=asset.symbol,
            ),
            activity_summary=DiscoveryActivitySummary(
                investor_count=len(accumulator.investor_ids),
                signal_count=len(accumulator.signal_ids),
                event_count=len(accumulator.event_ids),
                feed_count=len(accumulator.feed_ids),
            ),
            evidence_summary=DiscoveryEvidenceSummary(
                event_types=tuple(sorted(accumulator.event_types, key=lambda value: value.value)),
                priority_reasons=tuple(
                    sorted(accumulator.priority_reasons, key=lambda value: value.value)
                ),
                latest_observed_at=latest_observed_at,
            ),
            discovery_reasons=tuple(sorted(accumulator.discovery_reasons)),
        )


__all__ = [
    "DiscoveryAssetNotFoundError",
    "IntelligenceDiscoveryQueryUoW",
    "IntelligenceDiscoveryService",
]
