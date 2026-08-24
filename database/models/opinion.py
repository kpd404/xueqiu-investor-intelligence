from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now
from database.models.enums import OpinionDirection

if TYPE_CHECKING:
    from database.models.asset import Asset
    from database.models.investor import Investor
    from database.models.raw_event import RawEvent


class Opinion(Base):
    __tablename__ = "opinions"
    __table_args__ = (
        UniqueConstraint("event_id", "asset_id", "model_version", name="event_asset_model"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    direction: Mapped[OpinionDirection] = mapped_column(
        SqlEnum(OpinionDirection, native_enum=False, validate_strings=True), nullable=False
    )
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    thesis: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    catalysts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    time_horizon: Mapped[str | None] = mapped_column(String(64))

    # DATA_MODEL §6 requires these provenance fields on every AI-generated record.
    generated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(255), nullable=False)

    event: Mapped["RawEvent"] = relationship(back_populates="opinions")
    investor: Mapped["Investor"] = relationship(back_populates="opinions")
    asset: Mapped["Asset"] = relationship(back_populates="opinions")
