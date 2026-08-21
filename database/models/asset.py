from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.investor_asset_state import InvestorAssetState
    from database.models.opinion import Opinion
    from database.models.signal import Signal


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("market", "symbol", name="market_symbol"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(32), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255))
    themes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    opinions: Mapped[list["Opinion"]] = relationship(back_populates="asset")
    investor_states: Mapped[list["InvestorAssetState"]] = relationship(back_populates="asset")
    signals: Mapped[list["Signal"]] = relationship(back_populates="asset")
