"""Persistence adapter for deterministic IntelligenceEvent priorities."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    IntelligenceEventPriorityCreate,
    IntelligenceEventPriorityView,
    IntelligenceEventState,
    IntelligenceEventType,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
)
from database.models.intelligence_event import IntelligenceEvent
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
        entity = self._session.scalar(
            select(IntelligenceEventPriority).where(
                IntelligenceEventPriority.event_id == command.event_id
            )
        )
        if entity is not None:
            if entity.evidence_count != command.evidence_count:
                entity.evidence_count = command.evidence_count
                self._session.flush()
            return self._to_view(entity), False
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
            existing = self._session.scalar(
                select(IntelligenceEventPriority).where(
                    IntelligenceEventPriority.event_id == command.event_id
                )
            )
            if existing is None:
                raise
            if existing.evidence_count != command.evidence_count:
                existing.evidence_count = command.evidence_count
                self._session.flush()
            return self._to_view(existing), False
        return self._to_view(entity), True

    def add_or_refresh_thesis_change(
        self,
        command: IntelligenceEventPriorityCreate,
    ) -> tuple[IntelligenceEventPriorityView, bool]:
        """Correct only this derived classification; keep identity and creation time."""

        event = self._session.get(IntelligenceEvent, command.event_id)
        if (
            event is None
            or event.event_type != IntelligenceEventType.INVESTOR_VIEW_CHANGE.value
            or event.state != IntelligenceEventState.ACTIVE.value
        ):
            raise ValueError("Thesis refresh requires an ACTIVE INVESTOR_VIEW_CHANGE Event")
        if (
            command.reason is not IntelligencePriorityReason.THESIS_CHANGE_OBSERVED
            or command.priority_level is not IntelligencePriorityLevel.MEDIUM
        ):
            raise ValueError("Thesis refresh requires MEDIUM / THESIS_CHANGE_OBSERVED")
        priority, created = self.add_if_absent(command)
        if created:
            return priority, True
        entity = self._session.get(IntelligenceEventPriority, priority.id)
        changed = False
        for field, value in (
            ("reason", command.reason.value),
            ("priority_level", command.priority_level.value),
            ("evidence_count", command.evidence_count),
        ):
            if getattr(entity, field) != value:
                setattr(entity, field, value)
                changed = True
        if changed:
            self._session.flush()
        return self._to_view(entity), False

    def add_or_refresh_cross_direction(
        self,
        command: IntelligenceEventPriorityCreate,
    ) -> tuple[IntelligenceEventPriorityView, bool]:
        """Replace only approved cross-derived fields; preserve identity/created_at."""
        event = self._session.get(IntelligenceEvent, command.event_id)
        levels = {
            IntelligenceEventType.CROSS_INVESTOR_DISCOVERY.value: IntelligencePriorityLevel.LOW,
            IntelligenceEventType.CONSENSUS_STATE_CHANGE.value: IntelligencePriorityLevel.HIGH,
        }
        if (
            event is None
            or event.event_type not in levels
            or event.state != IntelligenceEventState.ACTIVE.value
        ):
            raise ValueError("Cross direction refresh requires an ACTIVE cross-investor Event")
        if (
            command.reason is not IntelligencePriorityReason.CROSS_INVESTOR_DIRECTION_EVIDENCE
            or command.priority_level is not levels[event.event_type]
        ):
            raise ValueError(
                "Cross direction refresh requires the existing level and observed reason"
            )
        priority, created = self.add_if_absent(command)
        if created:
            return priority, True
        entity = self._session.get(IntelligenceEventPriority, priority.id)
        changed = False
        for field, value in (
            ("reason", command.reason.value),
            ("priority_level", command.priority_level.value),
            ("evidence_count", command.evidence_count),
        ):
            if getattr(entity, field) != value:
                setattr(entity, field, value)
                changed = True
        if changed:
            self._session.flush()
        return self._to_view(entity), False

    def list(self) -> tuple[IntelligenceEventPriorityView, ...]:
        statement = select(IntelligenceEventPriority).order_by(
            IntelligenceEventPriority.priority_level,
            IntelligenceEventPriority.reason,
            IntelligenceEventPriority.event_id,
            IntelligenceEventPriority.id,
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    def list_by_event_ids(
        self,
        event_ids: tuple[UUID, ...],
    ) -> tuple[IntelligenceEventPriorityView, ...]:
        if not event_ids:
            return ()
        statement = (
            select(IntelligenceEventPriority)
            .where(IntelligenceEventPriority.event_id.in_(event_ids))
            .order_by(
                IntelligenceEventPriority.priority_level,
                IntelligenceEventPriority.reason,
                IntelligenceEventPriority.event_id,
                IntelligenceEventPriority.id,
            )
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
