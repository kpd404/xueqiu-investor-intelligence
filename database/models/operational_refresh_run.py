"""Persistence for full operational refresh execution metadata."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from contracts import OperationalRefreshStatus, OperationalRefreshTrigger
from database.base import Base
from database.models._types import utc_now


class OperationalRefreshRun(Base):
    """One full refresh execution, separate from source CollectionRun facts."""

    __tablename__ = "operational_refresh_runs"
    __table_args__ = (
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=conv("ck_operational_refresh_run_finished_after_started"),
        ),
        Index("ix_operational_refresh_runs_status_started", "status", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    failure_stage: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    summary_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    @property
    def status_enum(self) -> OperationalRefreshStatus:
        return OperationalRefreshStatus(self.status)

    @property
    def trigger_enum(self) -> OperationalRefreshTrigger:
        return OperationalRefreshTrigger(self.trigger)


__all__ = ["OperationalRefreshRun"]
