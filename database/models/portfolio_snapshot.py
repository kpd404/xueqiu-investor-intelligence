from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from contracts.portfolio import PortfolioSnapshotCompleteness
from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.portfolio import Portfolio
    from database.models.position_snapshot import PositionSnapshot


class PortfolioSnapshotBatch(Base):
    """Immutable fact container for all positions observed at one snapshot time."""

    __tablename__ = "portfolio_snapshot_batches"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "snapshot_time",
            "source",
            "external_id",
            name="portfolio_snapshot_batch_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    completeness: Mapped[PortfolioSnapshotCompleteness] = mapped_column(
        String(16), nullable=False, default=PortfolioSnapshotCompleteness.FULL
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    portfolio: Mapped["Portfolio"] = relationship()
    positions: Mapped[list["PositionSnapshot"]] = relationship(back_populates="snapshot_batch")
