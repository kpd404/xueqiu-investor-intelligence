from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid, event
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now
from database.models.enums import EventType

if TYPE_CHECKING:
    from database.models.event_analysis import EventAnalysis
    from database.models.investor import Investor
    from database.models.opinion import Opinion


class RawEventImmutableError(RuntimeError):
    """Raised when application code attempts to mutate a persisted raw fact."""


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(
        SqlEnum(EventType, native_enum=False, validate_strings=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    collected_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    investor: Mapped["Investor"] = relationship(back_populates="raw_events")
    analyses: Mapped[list["EventAnalysis"]] = relationship(back_populates="event")
    opinions: Mapped[list["Opinion"]] = relationship(back_populates="event")


@event.listens_for(RawEvent, "before_update")
def prevent_raw_event_update(*_: object) -> None:
    raise RawEventImmutableError("RawEvent is append-only and cannot be updated")


@event.listens_for(RawEvent, "before_delete")
def prevent_raw_event_delete(*_: object) -> None:
    raise RawEventImmutableError("RawEvent is append-only and cannot be deleted")
