"""Persistence model linking aggregate events to atomic Signals."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.intelligence_event import IntelligenceEvent
    from database.models.signal import Signal


class IntelligenceEventEvidence(Base):
    """Many-to-many evidence link from an IntelligenceEvent to a Signal."""

    __tablename__ = "intelligence_event_evidence"
    __table_args__ = (
        UniqueConstraint("event_id", "signal_id", name="intelligence_event_evidence_identity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    signal_id: Mapped[UUID] = mapped_column(
        ForeignKey("signals.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    event: Mapped["IntelligenceEvent"] = relationship(back_populates="evidence")
    signal: Mapped["Signal"] = relationship()
