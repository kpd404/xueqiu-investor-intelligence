from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from contracts.analysis import EventAnalysisStatus
from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.opinion import Opinion
    from database.models.raw_event import RawEvent


class EventAnalysis(Base):
    """Recomputable interpretation lifecycle for one RawEvent and AnalysisSpec."""

    __tablename__ = "event_analyses"
    __table_args__ = (
        UniqueConstraint("event_id", "analysis_version", name="event_analysis_identity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    analysis_version: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[EventAnalysisStatus] = mapped_column(
        SqlEnum(EventAnalysisStatus, native_enum=False, validate_strings=True), nullable=False
    )
    investment_related: Mapped[bool] = mapped_column(Boolean, nullable=False)
    generated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    structured_output: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(255))

    event: Mapped["RawEvent"] = relationship(back_populates="analyses")
    opinions: Mapped[list["Opinion"]] = relationship(back_populates="analysis")
