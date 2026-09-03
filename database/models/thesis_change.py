from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from contracts.thesis_change import ThesisChangeType
from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.asset import Asset
    from database.models.investor import Investor
    from database.models.opinion import Opinion
    from database.models.raw_event import RawEvent


class ThesisChange(Base):
    """Versioned, traceable comparison artifact for two effective Opinions."""

    __tablename__ = "thesis_changes"
    __table_args__ = (UniqueConstraint("input_identity", name="thesis_change_input_identity"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    previous_opinion_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("opinions.id", ondelete="RESTRICT"), index=True
    )
    current_opinion_id: Mapped[UUID] = mapped_column(
        ForeignKey("opinions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    previous_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("raw_events.id", ondelete="RESTRICT"), index=True
    )
    current_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    effective_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    change_type: Mapped[ThesisChangeType] = mapped_column(
        SqlEnum(ThesisChangeType, native_enum=False, validate_strings=True), nullable=False
    )
    confidence: Mapped[float] = mapped_column(nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    opinion_analysis_version: Mapped[str] = mapped_column(String(255), nullable=False)
    comparison_version: Mapped[str] = mapped_column(String(255), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    input_identity: Mapped[str] = mapped_column(String(512), nullable=False)

    investor: Mapped["Investor"] = relationship()
    asset: Mapped["Asset"] = relationship()
    previous_opinion: Mapped["Opinion | None"] = relationship(foreign_keys=[previous_opinion_id])
    current_opinion: Mapped["Opinion"] = relationship(foreign_keys=[current_opinion_id])
    previous_event: Mapped["RawEvent | None"] = relationship(foreign_keys=[previous_event_id])
    current_event: Mapped["RawEvent"] = relationship(foreign_keys=[current_event_id])
