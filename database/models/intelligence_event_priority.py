"""Persistence model for observation-priority classifications."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.intelligence_event import IntelligenceEvent


class IntelligenceEventPriority(Base):
    """One deterministic priority classification for an IntelligenceEvent."""

    __tablename__ = "intelligence_event_priorities"
    __table_args__ = (
        UniqueConstraint("event_id", name="intelligence_event_priority_event_identity"),
        Index("ix_intelligence_event_priorities_level_reason", "priority_level", "reason"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    priority_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )

    event: Mapped["IntelligenceEvent"] = relationship()
