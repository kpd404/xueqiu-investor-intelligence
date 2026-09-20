"""Persistence adapter for Intelligence Feed items."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import FeedItem, FeedItemCreate, FeedState
from database.models.intelligence_feed_item import IntelligenceFeedItem


class IntelligenceFeedItemRepository:
    """Idempotent repository keyed by the source Priority."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, feed_item_id: UUID) -> FeedItem | None:
        entity = self._session.get(IntelligenceFeedItem, feed_item_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_priority(self, priority_id: UUID) -> FeedItem | None:
        entity = self._session.scalar(
            select(IntelligenceFeedItem).where(IntelligenceFeedItem.priority_id == priority_id)
        )
        return self._to_view(entity) if entity is not None else None

    def add_if_absent(self, command: FeedItemCreate) -> tuple[FeedItem, bool]:
        existing = self.get_by_priority(command.priority_id)
        if existing is not None:
            return existing, False
        entity = IntelligenceFeedItem(
            priority_id=command.priority_id,
            asset_id=command.asset_id,
            event_type=command.event_type.value,
            title=command.title,
            context=command.context,
            reason=command.reason.value,
            state=command.state.value,
            observed_at=command.observed_at,
            created_at=command.created_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_priority(command.priority_id)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def list(self) -> tuple[FeedItem, ...]:
        statement = select(IntelligenceFeedItem).order_by(
            IntelligenceFeedItem.observed_at,
            IntelligenceFeedItem.priority_id,
            IntelligenceFeedItem.id,
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    def list_by_asset(self, asset_id: UUID) -> tuple[FeedItem, ...]:
        statement = (
            select(IntelligenceFeedItem)
            .where(IntelligenceFeedItem.asset_id == asset_id)
            .order_by(
                IntelligenceFeedItem.observed_at,
                IntelligenceFeedItem.priority_id,
                IntelligenceFeedItem.id,
            )
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    def update_state(self, feed_item_id: UUID, state: FeedState) -> FeedItem:
        """Update only lifecycle state; identity and evidence stay fixed."""

        entity = self._session.get(IntelligenceFeedItem, feed_item_id)
        if entity is None:
            raise LookupError(f"FeedItem not found: {feed_item_id}")
        entity.state = state.value
        self._session.flush()
        return self._to_view(entity)

    @classmethod
    def _to_view(cls, entity: IntelligenceFeedItem | None) -> FeedItem | None:
        if entity is None:
            return None
        return FeedItem(
            id=entity.id,
            priority_id=entity.priority_id,
            asset_id=entity.asset_id,
            event_type=entity.event_type,
            title=entity.title,
            context=entity.context or {},
            reason=entity.reason,
            state=entity.state,
            observed_at=cls._as_utc(entity.observed_at),
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["IntelligenceFeedItemRepository"]
