from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from contracts.attention import PRODUCTION_ATTENTION_POLICY_VERSION
from contracts.behavior import BEHAVIOR_SNAPSHOT_POLICY_VERSION
from database.base import Base


class InvestorBehaviorSnapshot(Base):
    """Derived fact-window metrics for one Investor; not a score or recommendation."""

    __tablename__ = "investor_behavior_snapshots"
    __table_args__ = (
        UniqueConstraint("input_identity", name="investor_behavior_snapshot_input_identity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    attention_asset_count: Mapped[int] = mapped_column(Integer, nullable=False)
    attention_occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    new_attention_count: Mapped[int] = mapped_column(Integer, nullable=False)
    opinion_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bullish_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bearish_count: Mapped[int] = mapped_column(Integer, nullable=False)
    thesis_change_count: Mapped[int] = mapped_column(Integer, nullable=False)
    thesis_reinforced_count: Mapped[int] = mapped_column(Integer, nullable=False)
    thesis_changed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    portfolio_action_count: Mapped[int] = mapped_column(Integer, nullable=False)
    position_increased_count: Mapped[int] = mapped_column(Integer, nullable=False)
    position_decreased_count: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_alignment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_alignment_count: Mapped[int] = mapped_column(Integer, nullable=False)

    active_analysis_version: Mapped[str] = mapped_column(String(255), nullable=False)
    thesis_comparison_version: Mapped[str | None] = mapped_column(String(255))
    consistency_policy_version: Mapped[str | None] = mapped_column(String(64))
    attention_policy_version: Mapped[str] = mapped_column(
        String(64), default=PRODUCTION_ATTENTION_POLICY_VERSION, nullable=False
    )
    behavior_policy_version: Mapped[str] = mapped_column(
        String(64), default=BEHAVIOR_SNAPSHOT_POLICY_VERSION, nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    input_identity: Mapped[str] = mapped_column(String(512), nullable=False)
