"""Persistence adapter for IntelligenceEvent → Signal evidence links."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import IntelligenceEventEvidenceCreate, IntelligenceEventEvidenceView
from database.models.intelligence_event_evidence import IntelligenceEventEvidence


class IntelligenceEventEvidenceRepository:
    """Idempotent repository for aggregate-to-atomic evidence links."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_identity(
        self,
        event_id: UUID,
        signal_id: UUID,
    ) -> IntelligenceEventEvidenceView | None:
        entity = self._session.scalar(
            select(IntelligenceEventEvidence).where(
                IntelligenceEventEvidence.event_id == event_id,
                IntelligenceEventEvidence.signal_id == signal_id,
            )
        )
        return self._to_view(entity) if entity is not None else None

    def add_if_absent(
        self,
        command: IntelligenceEventEvidenceCreate,
    ) -> tuple[IntelligenceEventEvidenceView, bool]:
        existing = self.get_by_identity(command.event_id, command.signal_id)
        if existing is not None:
            return existing, False
        entity = IntelligenceEventEvidence(
            event_id=command.event_id,
            signal_id=command.signal_id,
        )
        try:
            with self._session.begin_nested():
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_identity(command.event_id, command.signal_id)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def list_by_event(self, event_id: UUID) -> tuple[IntelligenceEventEvidenceView, ...]:
        statement = select(IntelligenceEventEvidence).where(
            IntelligenceEventEvidence.event_id == event_id
        )
        statement = statement.order_by(
            IntelligenceEventEvidence.signal_id, IntelligenceEventEvidence.id
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    def list_by_event_ids(
        self,
        event_ids: tuple[UUID, ...],
    ) -> tuple[IntelligenceEventEvidenceView, ...]:
        if not event_ids:
            return ()
        statement = (
            select(IntelligenceEventEvidence)
            .where(IntelligenceEventEvidence.event_id.in_(event_ids))
            .order_by(
                IntelligenceEventEvidence.event_id,
                IntelligenceEventEvidence.signal_id,
                IntelligenceEventEvidence.id,
            )
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    def list(self) -> tuple[IntelligenceEventEvidenceView, ...]:
        statement = select(IntelligenceEventEvidence).order_by(
            IntelligenceEventEvidence.event_id,
            IntelligenceEventEvidence.signal_id,
            IntelligenceEventEvidence.id,
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    @classmethod
    def _to_view(
        cls,
        entity: IntelligenceEventEvidence | None,
    ) -> IntelligenceEventEvidenceView | None:
        if entity is None:
            return None
        return IntelligenceEventEvidenceView(
            id=entity.id,
            event_id=entity.event_id,
            signal_id=entity.signal_id,
        )


__all__ = ["IntelligenceEventEvidenceRepository"]
