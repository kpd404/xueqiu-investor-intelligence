from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from contracts.portfolio import PortfolioActionType
from database.base import Base
from database.models._types import utc_now


class PortfolioAction(Base):
    """Derived, provenance-complete action between two snapshot batches."""

    __tablename__ = "portfolio_actions"
    __table_args__ = (
        CheckConstraint(
            "(asset_id IS NOT NULL AND asset_reference_id IS NULL) OR "
            "(asset_id IS NULL AND asset_reference_id IS NOT NULL)",
            name="portfolio_action_asset_identity",
        ),
        Index(
            "portfolio_action_resolved_identity",
            "portfolio_id",
            "previous_snapshot_batch_id",
            "current_snapshot_batch_id",
            "asset_id",
            "action_type",
            unique=True,
            postgresql_where=text("asset_id IS NOT NULL"),
            sqlite_where=text("asset_id IS NOT NULL"),
        ),
        Index(
            "portfolio_action_unresolved_identity",
            "portfolio_id",
            "previous_snapshot_batch_id",
            "current_snapshot_batch_id",
            "asset_reference_id",
            "action_type",
            unique=True,
            postgresql_where=text("asset_reference_id IS NOT NULL"),
            sqlite_where=text("asset_reference_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    asset_reference_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    previous_snapshot_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshot_batches.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    current_snapshot_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshot_batches.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    previous_position_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("position_snapshots.id", ondelete="RESTRICT"), index=True
    )
    current_position_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("position_snapshots.id", ondelete="RESTRICT"), index=True
    )
    # Legacy position column names retained for pre-2E.3-D rows and callers.
    previous_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("position_snapshots.id", ondelete="RESTRICT"), index=True
    )
    current_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("position_snapshots.id", ondelete="RESTRICT"), index=True
    )
    # Values are constrained by the provider-neutral PortfolioActionType contract.
    # A string column keeps the non-native PostgreSQL representation migration-stable.
    action_type: Mapped[PortfolioActionType] = mapped_column(String(19), nullable=False)
    effective_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
