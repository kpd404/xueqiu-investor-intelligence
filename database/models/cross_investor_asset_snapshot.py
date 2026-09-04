from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from contracts.cross_investor import CROSS_INVESTOR_POLICY_VERSION
from database.base import Base
from database.models._types import utc_now


class CrossInvestorAssetSnapshot(Base):
    """Immutable cross-investor evidence aggregation for one Asset window."""

    __tablename__ = "cross_investor_asset_snapshots"
    __table_args__ = (
        UniqueConstraint("input_identity", name="cross_investor_asset_snapshot_input_identity"),
        Index(
            "ix_cross_investor_asset_snapshots_asset_window",
            "asset_id",
            "window_start",
            "window_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    attention_occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    attention_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    new_attention_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)

    opinion_count: Mapped[int] = mapped_column(Integer, nullable=False)
    opinion_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bullish_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bearish_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    neutral_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)

    thesis_change_count: Mapped[int] = mapped_column(Integer, nullable=False)
    thesis_change_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    thesis_reinforced_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    thesis_changed_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)

    portfolio_action_count: Mapped[int] = mapped_column(Integer, nullable=False)
    portfolio_action_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    position_increased_count: Mapped[int] = mapped_column(Integer, nullable=False)
    position_decreased_count: Mapped[int] = mapped_column(Integer, nullable=False)

    consistency_count: Mapped[int] = mapped_column(Integer, nullable=False)
    consistency_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_alignment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_alignment_count: Mapped[int] = mapped_column(Integer, nullable=False)

    contributions: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, default=list, nullable=False
    )

    opinion_analysis_version: Mapped[str] = mapped_column(String(255), nullable=False)
    attention_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    thesis_comparison_version: Mapped[str] = mapped_column(String(255), nullable=False)
    consistency_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    cross_investor_policy_version: Mapped[str] = mapped_column(
        String(64), default=CROSS_INVESTOR_POLICY_VERSION, nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
    input_identity: Mapped[str] = mapped_column(String(64), nullable=False)
