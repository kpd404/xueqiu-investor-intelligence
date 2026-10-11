"""User intent, independent of generated Discovery and Feed lifecycle."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from database.models._types import utc_now


class ResearchCandidate(Base):
    __tablename__ = "research_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('TODO','RESEARCHING','ARCHIVED')", name="research_candidate_status"
        ),
        Index(
            "research_candidate_open_asset",
            "asset_id",
            unique=True,
            sqlite_where=text("status != 'ARCHIVED'"),
            postgresql_where=text("status != 'ARCHIVED'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="TODO")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    questions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    submission_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
