"""Persistence adapter for deterministic IntelligenceEvent priorities."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    IntelligenceEventPriorityCreate,
    IntelligenceEventPriorityView,
)
from database.models.intelligence_event_priority import IntelligenceEventPriority


class IntelligenceEventPriorityRepository:
    """Idempotent repository for one priority row per IntelligenceEvent."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, priority_id: UUID) -> IntelligenceEventPriorityView | None:
        entity = self._session.get(IntelligenceEventPriority, priority_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_event(self, event_id: UUID) -> IntelligenceEventPriorityView | None:
        entity = self._session.scalar(
            select(IntelligenceEventPriority).where(IntelligenceEventPriority.event_id == event_id)
        )
        return self._to_view(entity) if entity is not None else None

    def add_if_absent(
        self,
        command: IntelligenceEventPriorityCreate,
    ) -> tuple[IntelligenceEventPriorityView, bool]:
        existing = self.get_by_event(command.event_id)
        if existing is not None:
            return existing, False
        entity = IntelligenceEventPriority(
            event_id=command.event_id,
            priority_level=command.priority_level.value,
            reason=command.reason.value,
            evidence_count=command.evidence_count,
            created_at=command.created_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_event(command.event_id)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def list(self) -> tuple[IntelligenceEventPriorityView, ...]:
        statement = select(IntelligenceEventPriority).order_by(
            IntelligenceEventPriority.priority_level,
            IntelligenceEventPriority.reason,
            IntelligenceEventPriority.event_id,
            IntelligenceEventPriority.id,
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    @classmethod
    def _to_view(
        cls,
        entity: IntelligenceEventPriority | None,
    ) -> IntelligenceEventPriorityView | None:
        if entity is None:
            return None
        return IntelligenceEventPriorityView(
            id=entity.id,
            event_id=entity.event_id,
            priority_level=entity.priority_level,
            reason=entity.reason,
            evidence_count=entity.evidence_count,
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["IntelligenceEventPriorityRepository"]
