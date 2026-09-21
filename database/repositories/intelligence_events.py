"""Persistence adapter for aggregated Intelligence Events."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import IntelligenceEventCreate, IntelligenceEventView
from database.models.intelligence_event import IntelligenceEvent


class IntelligenceEventRepository:
    """Idempotent repository for aggregate Intelligence Events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, event_id: UUID) -> IntelligenceEventView | None:
        entity = self._session.get(IntelligenceEvent, event_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_identity(
        self,
        event_type: str,
        asset_id: UUID,
    ) -> IntelligenceEventView | None:
        entity = self._session.scalar(
            select(IntelligenceEvent).where(
                IntelligenceEvent.event_type == event_type,
                IntelligenceEvent.asset_id == asset_id,
            )
        )
        return self._to_view(entity) if entity is not None else None

    def add_if_absent(
        self,
        command: IntelligenceEventCreate,
    ) -> tuple[IntelligenceEventView, bool]:
        existing_entity = self._session.scalar(
            select(IntelligenceEvent).where(
                IntelligenceEvent.event_type == command.event_type.value,
                IntelligenceEvent.asset_id == command.asset_id,
            )
        )
        if existing_entity is not None:
            changed = False
            first_observed_at = min(
                self._as_utc(existing_entity.first_observed_at),
                command.first_observed_at,
            )
            last_observed_at = max(
                self._as_utc(existing_entity.last_observed_at),
                command.last_observed_at,
            )
            if self._as_utc(existing_entity.first_observed_at) != first_observed_at:
                existing_entity.first_observed_at = first_observed_at
                changed = True
            if self._as_utc(existing_entity.last_observed_at) != last_observed_at:
                existing_entity.last_observed_at = last_observed_at
                changed = True
            if existing_entity.metadata_json != command.metadata:
                existing_entity.metadata_json = command.metadata
                changed = True
            if changed:
                self._session.flush()
            return self._to_view(existing_entity), False
        entity = IntelligenceEvent(
            asset_id=command.asset_id,
            event_type=command.event_type.value,
            state=command.state.value,
            first_observed_at=command.first_observed_at,
            last_observed_at=command.last_observed_at,
            metadata_json=command.metadata,
        )
        try:
            with self._session.begin_nested():
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_identity(command.event_type.value, command.asset_id)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def list(self) -> tuple[IntelligenceEventView, ...]:
        statement = select(IntelligenceEvent).order_by(
            IntelligenceEvent.last_observed_at,
            IntelligenceEvent.event_type,
            IntelligenceEvent.asset_id,
            IntelligenceEvent.id,
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    def list_by_asset(self, asset_id: UUID) -> tuple[IntelligenceEventView, ...]:
        statement = (
            select(IntelligenceEvent)
            .where(IntelligenceEvent.asset_id == asset_id)
            .order_by(
                IntelligenceEvent.last_observed_at,
                IntelligenceEvent.event_type,
                IntelligenceEvent.id,
            )
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    @classmethod
    def _to_view(cls, entity: IntelligenceEvent | None) -> IntelligenceEventView | None:
        if entity is None:
            return None
        return IntelligenceEventView(
            id=entity.id,
            asset_id=entity.asset_id,
            event_type=entity.event_type,
            state=entity.state,
            first_observed_at=cls._as_utc(entity.first_observed_at),
            last_observed_at=cls._as_utc(entity.last_observed_at),
            metadata=entity.metadata_json or {},
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["IntelligenceEventRepository"]
