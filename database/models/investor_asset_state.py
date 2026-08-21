from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models.enums import AttentionLevel, OpinionDirection, PositionStatus

if TYPE_CHECKING:
    from database.models.asset import Asset
    from database.models.investor import Investor


class InvestorAssetState(Base):
    __tablename__ = "investor_asset_states"
    __table_args__ = (UniqueConstraint("investor_id", "asset_id", name="investor_asset"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    attention_level: Mapped[AttentionLevel] = mapped_column(
        SqlEnum(AttentionLevel, native_enum=False, validate_strings=True),
        default=AttentionLevel.UNKNOWN,
        nullable=False,
    )
    direction: Mapped[OpinionDirection] = mapped_column(
        SqlEnum(OpinionDirection, native_enum=False, validate_strings=True),
        default=OpinionDirection.NEUTRAL,
        nullable=False,
    )
    conviction: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position_status: Mapped[PositionStatus] = mapped_column(
        SqlEnum(PositionStatus, native_enum=False, validate_strings=True),
        default=PositionStatus.NO_POSITION,
        nullable=False,
    )
    last_opinion_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_change_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    investor: Mapped["Investor"] = relationship(back_populates="asset_states")
    asset: Mapped["Asset"] = relationship(back_populates="investor_states")
