from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from contracts.portfolio import InvestorActionClaimType
from database.base import Base
from database.models._types import utc_now


class InvestorActionClaim(Base):
    """An investor's textual action claim, distinct from Portfolio Fact."""

    __tablename__ = "investor_action_claims"
    __table_args__ = (
        CheckConstraint(
            "NOT (asset_id IS NOT NULL AND asset_reference_id IS NOT NULL)",
            name="investor_action_claim_asset_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    # This remains an opaque reference until a dedicated AssetReference store exists.
    asset_reference_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_events.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    claim_type: Mapped[InvestorActionClaimType] = mapped_column(
        SqlEnum(InvestorActionClaimType, native_enum=False, validate_strings=True), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    published_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    analysis_version: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
