from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from contracts.consistency import ConsistencyType
from contracts.enums import OpinionDirection
from contracts.portfolio import PortfolioActionType
from database.base import Base


class InvestorActionConsistency(Base):
    """Versioned derived analysis relating an effective Opinion to an Action."""

    __tablename__ = "investor_action_consistencies"
    __table_args__ = (
        UniqueConstraint(
            "input_identity",
            name="investor_action_consistency_input_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    opinion_id: Mapped[UUID] = mapped_column(
        ForeignKey("opinions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    opinion_direction: Mapped[OpinionDirection | None] = mapped_column(String(32))
    portfolio_action_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_actions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    action_type: Mapped[PortfolioActionType] = mapped_column(String(32), nullable=False)
    consistency_type: Mapped[ConsistencyType] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    effective_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opinion_analysis_version: Mapped[str] = mapped_column(String(255), nullable=False)
    consistency_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_identity: Mapped[str] = mapped_column(String(512), nullable=False)
