"""Persistence model for the read-side Intelligence Feed projection."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.asset import Asset
    from database.models.intelligence_event_priority import IntelligenceEventPriority


class IntelligenceFeedItem(Base):
    """User-facing deterministic projection of one IntelligenceEvent priority."""

    __tablename__ = "intelligence_feed_items"
    __table_args__ = (
        UniqueConstraint("priority_id", name="intelligence_feed_item_priority_identity"),
        Index("ix_intelligence_feed_items_asset_observed_at", "asset_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    priority_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_event_priorities.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    context: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )

    priority: Mapped["IntelligenceEventPriority"] = relationship()
    asset: Mapped["Asset"] = relationship()
