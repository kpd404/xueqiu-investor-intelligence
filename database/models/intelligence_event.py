"""Persistence model for aggregated Intelligence Events."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.asset import Asset
    from database.models.intelligence_event_evidence import IntelligenceEventEvidence


class IntelligenceEvent(Base):
    """Aggregate of atomic Signals for one Asset and event type."""

    __tablename__ = "intelligence_events"
    __table_args__ = (
        UniqueConstraint("event_type", "asset_id", name="intelligence_event_identity"),
        Index("ix_intelligence_events_asset_observed_at", "asset_id", "last_observed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )

    asset: Mapped["Asset"] = relationship()
    evidence: Mapped[list["IntelligenceEventEvidence"]] = relationship(
        back_populates="event",
        cascade="save-update, merge",
    )
