"""Read-only Query Layer over persisted Intelligence Feed items."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
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
)
from intelligence.schemas.feed import (
    FeedAssetIdentity,
    FeedInvestorIdentity,
    IntelligenceFeedListResponse,
    IntelligenceFeedResponse,
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
    def list(self): ...


class AssetReader(Protocol):
    def list(self): ...


class InvestorReader(Protocol):
    def list(self): ...


class IntelligenceFeedQueryUoW(Protocol):
    intelligence_feed_items: FeedItemReader
    intelligence_event_priorities: PriorityReader
    intelligence_events: EventReader
    intelligence_event_evidence: EvidenceReader
    signals: SignalReader
    assets: AssetReader
    investors: InvestorReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


IntelligenceFeedQueryUoWFactory = Callable[[], IntelligenceFeedQueryUoW]


class FeedAssetNotFoundError(LookupError):
    """Raised when an explicitly requested Asset does not exist."""


class FeedInvestorNotFoundError(LookupError):
    """Raised when an explicitly requested Investor does not exist."""


class IntelligenceFeedQueryService:
    """Batch read projection for Feed API consumers."""

    def __init__(self, unit_of_work_factory: IntelligenceFeedQueryUoWFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(cls, session_factory: Callable[[], object]) -> IntelligenceFeedQueryService:
        from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

        return cls(lambda: SqlAlchemyIntelligenceFeedUnitOfWork(session_factory))

    def list_feed(
        self,
        *,
        limit: int = 50,
        asset_id: UUID | None = None,
        investor_id: UUID | None = None,
        priority_level: IntelligencePriorityLevel | None = None,
        event_type: IntelligenceEventType | None = None,
        state: FeedState | None = None,
        since: datetime | None = None,
    ) -> IntelligenceFeedListResponse:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if since is not None:
            if since.tzinfo is None or since.utcoffset() is None:
                raise ValueError("since must be timezone-aware")
            since = since.astimezone(UTC)
        with self._unit_of_work_factory() as unit_of_work:
            assets = {asset.id: asset for asset in unit_of_work.assets.list()}
            investors = {investor.id: investor for investor in unit_of_work.investors.list()}
            if asset_id is not None and asset_id not in assets:
                raise FeedAssetNotFoundError(f"asset not found: {asset_id}")
            if investor_id is not None and investor_id not in investors:
                raise FeedInvestorNotFoundError(f"investor not found: {investor_id}")

            feed_items = unit_of_work.intelligence_feed_items.list()
            priorities = {
                item.id: item for item in unit_of_work.intelligence_event_priorities.list()
            }
            events = {item.id: item for item in unit_of_work.intelligence_events.list()}
            links_by_event: dict[UUID, list[IntelligenceEventEvidenceView]] = defaultdict(list)
            for link in unit_of_work.intelligence_event_evidence.list():
                links_by_event[link.event_id].append(link)
            signals = {signal.id: signal for signal in unit_of_work.signals.list()}
            projected = []
            for item in feed_items:
                priority = priorities.get(item.priority_id)
                if priority is None:
                    raise ValueError(f"Priority not found for FeedItem: {item.id}")
                event = events.get(priority.event_id)
                if event is None:
                    raise ValueError(f"IntelligenceEvent not found for Priority: {priority.id}")
                if asset_id is not None and item.asset_id != asset_id:
                    continue
                if priority_level is not None and priority.priority_level is not priority_level:
                    continue
                if event_type is not None and event.event_type is not event_type:
                    continue
                if state is not None and item.state is not state:
                    continue
                if since is not None and item.observed_at < since:
                    continue
                if investor_id is not None:
                    linked_investors = {
                        signals[link.signal_id].investor_id
                        for link in links_by_event.get(event.id, [])
                        if link.signal_id in signals
                        and signals[link.signal_id].investor_id is not None
                    }
                    if investor_id not in linked_investors:
                        continue
                asset = assets.get(item.asset_id)
                if asset is None:
                    raise ValueError(f"Asset not found for FeedItem: {item.id}")
                linked_investors = tuple(
                    FeedInvestorIdentity(
                        investor_id=linked_id,
                        name=investors[linked_id].name,
                    )
                    for linked_id in sorted(
                        {
                            signals[link.signal_id].investor_id
                            for link in links_by_event.get(event.id, [])
                            if link.signal_id in signals
                            and signals[link.signal_id].investor_id in investors
                        },
                        key=lambda value: (investors[value].name, value.int),
                    )
                )
                projected.append(
                    IntelligenceFeedResponse(
                        id=item.id,
                        priority_id=item.priority_id,
                        asset=FeedAssetIdentity(
                            asset_id=asset.id,
                            name=asset.name,
                            market=asset.market,
                            symbol=asset.symbol,
                        ),
                        event_type=event.event_type,
                        priority_level=priority.priority_level,
                        reason=priority.reason,
                        title=item.title,
                        context=item.context,
                        investors=linked_investors,
                        state=item.state,
                        observed_at=item.observed_at,
                        created_at=item.created_at,
                    )
                )

        projected.sort(
            key=lambda item: (
                -item.observed_at.timestamp(),
                item.asset.name,
                item.asset.market,
                item.asset.symbol,
                item.id.int,
            )
        )
        total = len(projected)
        items = tuple(projected[:limit])
        return IntelligenceFeedListResponse(
            items=items,
            total=total,
            limit=limit,
            has_more=total > len(items),
        )

    def get_asset_feed(
        self,
        asset_id: UUID,
        *,
        limit: int = 50,
        priority_level: IntelligencePriorityLevel | None = None,
        event_type: IntelligenceEventType | None = None,
        state: FeedState | None = None,
        since: datetime | None = None,
    ) -> IntelligenceFeedListResponse:
        return self.list_feed(
            limit=limit,
            asset_id=asset_id,
            priority_level=priority_level,
            event_type=event_type,
            state=state,
            since=since,
        )

    def get_investor_feed(
        self,
        investor_id: UUID,
        *,
        limit: int = 50,
        priority_level: IntelligencePriorityLevel | None = None,
        event_type: IntelligenceEventType | None = None,
        state: FeedState | None = None,
        since: datetime | None = None,
    ) -> IntelligenceFeedListResponse:
        return self.list_feed(
            limit=limit,
            investor_id=investor_id,
            priority_level=priority_level,
            event_type=event_type,
            state=state,
            since=since,
        )


__all__ = [
    "FeedAssetNotFoundError",
    "FeedInvestorNotFoundError",
    "IntelligenceFeedQueryService",
]
