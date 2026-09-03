from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.investor_asset_state import InvestorAssetState
    from database.models.opinion import Opinion
    from database.models.portfolio import Portfolio
    from database.models.raw_event import RawEvent


class Investor(Base):
    __tablename__ = "investors"
    __table_args__ = (UniqueConstraint("platform", "platform_user_id", name="platform_identity"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(String(2048))
    investment_style: Mapped[str | None] = mapped_column(String(255))
    expertise_domains: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    raw_events: Mapped[list["RawEvent"]] = relationship(back_populates="investor")
    opinions: Mapped[list["Opinion"]] = relationship(back_populates="investor")
    asset_states: Mapped[list["InvestorAssetState"]] = relationship(back_populates="investor")
    portfolios: Mapped[list["Portfolio"]] = relationship(back_populates="investor")
