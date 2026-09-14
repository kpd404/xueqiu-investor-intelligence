from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.collection_observation import CollectionObservation


class CollectionRun(Base):
    """Mutable lifecycle record for one source-independent collection run."""

    __tablename__ = "collection_runs"
    __table_args__ = (
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="collection_run_ended_after_started",
        ),
        Index("ix_collection_runs_source_mode", "source", "collection_mode"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    collection_mode: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    transport: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(128))
    coverage_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    requested_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope_type: Mapped[str | None] = mapped_column(String(128))
    scope_key: Mapped[str | None] = mapped_column(String(255))
    collector_version: Mapped[str | None] = mapped_column(String(128))
    parameters_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    summary_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    observations: Mapped[list["CollectionObservation"]] = relationship(
        back_populates="collection_run"
    )


__all__ = ["CollectionRun"]
