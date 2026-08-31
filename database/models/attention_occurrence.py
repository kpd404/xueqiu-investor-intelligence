from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from database.models._types import utc_now


class AttentionOccurrence(Base):
    """Derived Investor × Asset × RawEvent behavior occurrence."""

    __tablename__ = "attention_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "asset_id",
            "attention_policy_version",
            name="event_asset_attention_policy",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    published_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    evidence_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    analysis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("event_analyses.id", ondelete="RESTRICT"), index=True
    )
    opinion_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("opinions.id", ondelete="RESTRICT"), index=True
    )
    attention_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
