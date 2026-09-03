from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from contracts.portfolio import PortfolioStatus
from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.investor import Investor


class Portfolio(Base):
    """An independently identified portfolio belonging to an Investor."""

    __tablename__ = "portfolio"
    __table_args__ = (UniqueConstraint("source", "external_id", name="portfolio_source_external"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PortfolioStatus] = mapped_column(
        SqlEnum(PortfolioStatus, native_enum=False, validate_strings=True),
        default=PortfolioStatus.UNKNOWN,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    investor: Mapped["Investor"] = relationship(back_populates="portfolios")
