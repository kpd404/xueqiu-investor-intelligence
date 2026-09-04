from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from contracts.cross_investor import (
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    DirectionalAlignmentState,
    OpinionCoverageState,
)
from database.base import Base
from database.models._types import utc_now


class CrossInvestorAssetAlignment(Base):
    """Immutable deterministic coverage and directional-alignment artifact."""

    __tablename__ = "cross_investor_asset_alignments"
    __table_args__ = (
        UniqueConstraint(
            "input_identity",
            name="cross_investor_asset_alignment_input_identity",
        ),
        UniqueConstraint(
            "source_snapshot_id",
            "alignment_policy_version",
            name="cross_investor_asset_alignment_source_policy",
        ),
        Index(
            "ix_cross_investor_asset_alignments_asset_policy",
            "asset_id",
            "alignment_policy_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("cross_investor_asset_snapshots.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    opinion_coverage_state: Mapped[OpinionCoverageState] = mapped_column(String(32), nullable=False)
    directional_alignment_state: Mapped[DirectionalAlignmentState] = mapped_column(
        String(32), nullable=False
    )
    alignment_policy_version: Mapped[str] = mapped_column(
        String(64),
        default=CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
        nullable=False,
    )
    input_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
