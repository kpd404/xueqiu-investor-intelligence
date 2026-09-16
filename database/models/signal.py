"""Persistence model for deterministic Signal evidence."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    from database.models.asset import Asset
    from database.models.investor import Investor


class Signal(Base):
    """Derived observable-intelligence event; never a recommendation score."""

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("signal_type", "source_id", name="signal_source_identity"),
        Index("ix_signals_asset_observed_at", "asset_id", "observed_at"),
        Index("ix_signals_source", "source_type", "source_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    investor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True
    )
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )

    asset: Mapped["Asset"] = relationship(back_populates="signals")
    investor: Mapped["Investor | None"] = relationship()
