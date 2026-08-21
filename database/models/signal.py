from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now
from database.models.enums import SignalLevel

if TYPE_CHECKING:
    from database.models.asset import Asset


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    signal_score: Mapped[float] = mapped_column(Float, nullable=False)
    signal_level: Mapped[SignalLevel] = mapped_column(
        SqlEnum(SignalLevel, native_enum=False, validate_strings=True), nullable=False
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reasons: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )

    asset: Mapped["Asset"] = relationship(back_populates="signals")
