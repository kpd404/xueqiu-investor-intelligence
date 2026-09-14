from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import CollectionObservationCreate, CollectionObservationView
from database.models.collection_observation import CollectionObservation


class CollectionObservationRepository:
    """Persistence adapter for idempotent run-to-RawEvent observations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record_observation(
        self,
        command: CollectionObservationCreate,
    ) -> tuple[CollectionObservationView, bool]:
        existing = self._session.scalar(
            select(CollectionObservation).where(
                CollectionObservation.collection_run_id == command.collection_run_id,
                CollectionObservation.raw_event_id == command.raw_event_id,
            )
        )
        if existing is not None:
            return self._to_view(existing), False

        try:
            with self._session.begin_nested():
                entity = CollectionObservation(
                    collection_run_id=command.collection_run_id,
                    raw_event_id=command.raw_event_id,
                    observed_at=command.observed_at,
                    ingest_disposition=command.ingest_disposition.value,
                    observation_sequence=command.observation_sequence,
                    source_page=command.source_page,
                    source_context_json=command.source_context_json,
                    created_at=command.created_at,
                )
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(CollectionObservation).where(
                    CollectionObservation.collection_run_id == command.collection_run_id,
                    CollectionObservation.raw_event_id == command.raw_event_id,
                )
            )
            if existing is None:
                raise
            return self._to_view(existing), False
        return self._to_view(entity), True

    def get_observation(self, observation_id: UUID) -> CollectionObservationView | None:
        entity = self._session.get(CollectionObservation, observation_id)
        return self._to_view(entity) if entity is not None else None

    def list_by_run(self, collection_run_id: UUID) -> list[CollectionObservationView]:
        statement = (
            select(CollectionObservation)
            .where(CollectionObservation.collection_run_id == collection_run_id)
            .order_by(
                CollectionObservation.observation_sequence,
                CollectionObservation.observed_at,
                CollectionObservation.id,
            )
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_by_raw_event(self, raw_event_id: UUID) -> list[CollectionObservationView]:
        statement = (
            select(CollectionObservation)
            .where(CollectionObservation.raw_event_id == raw_event_id)
            .order_by(CollectionObservation.observed_at, CollectionObservation.id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def get_event_observations(self, raw_event_id: UUID) -> list[CollectionObservationView]:
        """Return every run that observed one immutable RawEvent."""

        return self.list_by_raw_event(raw_event_id)

    def list_all(self) -> list[CollectionObservationView]:
        statement = select(CollectionObservation).order_by(
            CollectionObservation.observed_at,
            CollectionObservation.id,
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @classmethod
    def _to_view(cls, entity: CollectionObservation) -> CollectionObservationView:
        return CollectionObservationView(
            id=entity.id,
            collection_run_id=entity.collection_run_id,
            raw_event_id=entity.raw_event_id,
            observed_at=cls._as_utc(entity.observed_at),
            ingest_disposition=entity.ingest_disposition,
            observation_sequence=entity.observation_sequence,
            source_page=entity.source_page,
            source_context_json=entity.source_context_json,
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["CollectionObservationRepository"]
