"""Local user progress, independent of intelligence and system lifecycle."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from database.models._types import utc_now


class InboxUserState(Base):
    __tablename__ = "inbox_user_states"
    feed_id: Mapped[UUID] = mapped_column(
        ForeignKey("intelligence_feed_items.id", ondelete="RESTRICT"), primary_key=True
    )
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
