from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.portfolio_snapshot import PortfolioSnapshotBatch


class PositionSnapshot(Base):
    """An observed portfolio position at a fact-effective point in time."""

    __tablename__ = "position_snapshots"
    __table_args__ = (
        CheckConstraint(
            "(asset_id IS NOT NULL AND asset_reference_id IS NULL) OR "
            "(asset_id IS NULL AND asset_reference_id IS NOT NULL)",
            name="position_snapshot_asset_identity",
        ),
        Index(
            "position_snapshot_resolved_identity",
            "snapshot_batch_id",
            "asset_id",
            unique=True,
            postgresql_where=text("asset_id IS NOT NULL"),
            sqlite_where=text("asset_id IS NOT NULL"),
        ),
        Index(
            "position_snapshot_unresolved_identity",
            "snapshot_batch_id",
            "asset_reference_id",
            unique=True,
            postgresql_where=text("asset_reference_id IS NOT NULL"),
            sqlite_where=text("asset_reference_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    snapshot_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshot_batches.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    # This remains an opaque reference until a dedicated AssetReference store exists.
    asset_reference_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    weight: Mapped[float | None] = mapped_column(Float)
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    snapshot_batch: Mapped["PortfolioSnapshotBatch"] = relationship(back_populates="positions")
