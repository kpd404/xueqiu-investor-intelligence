from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.collection_run import CollectionRun
    from database.models.raw_event import RawEvent


class CollectionObservationImmutableError(RuntimeError):
    """Raised when a persisted collection observation is mutated or deleted."""


class CollectionObservation(Base):
    """Immutable provenance edge from one CollectionRun to one RawEvent."""

    __tablename__ = "collection_observations"
    __table_args__ = (
        UniqueConstraint(
            "collection_run_id",
            "raw_event_id",
            name="collection_observation_run_event",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    collection_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    raw_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    ingest_disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    observation_sequence: Mapped[int | None] = mapped_column(Integer)
    source_page: Mapped[str | None] = mapped_column(String(2048))
    source_context_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    collection_run: Mapped["CollectionRun"] = relationship(back_populates="observations")
    raw_event: Mapped["RawEvent"] = relationship(back_populates="collection_observations")


@event.listens_for(CollectionObservation, "before_update")
def prevent_collection_observation_update(*_: object) -> None:
    raise CollectionObservationImmutableError(
        "CollectionObservation is append-only and cannot be updated"
    )


@event.listens_for(CollectionObservation, "before_delete")
def prevent_collection_observation_delete(*_: object) -> None:
    raise CollectionObservationImmutableError(
        "CollectionObservation is append-only and cannot be deleted"
    )


__all__ = ["CollectionObservation", "CollectionObservationImmutableError"]
