from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, Uuid, event
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from contracts.state import StateTransitionType
from database.base import Base
from database.models._types import utc_now

if TYPE_CHECKING:
    pass


class StateChangeImmutableError(RuntimeError):
    """Raised when an append-only state change ledger row is mutated."""


class InvestorAssetStateChange(Base):
    """Append-only material state transition ledger."""

    __tablename__ = "investor_asset_state_changes"
    __table_args__ = (
        UniqueConstraint(
            "triggering_opinion_id",
            "state_policy_version",
            name="state_change_opinion_policy",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("investors.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    transition_type: Mapped[StateTransitionType] = mapped_column(
        SqlEnum(StateTransitionType, native_enum=False, validate_strings=True), nullable=False
    )
    effective_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    before: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    triggering_opinion_id: Mapped[UUID] = mapped_column(
        ForeignKey("opinions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    state_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)


@event.listens_for(InvestorAssetStateChange, "before_update")
def prevent_state_change_update(*_: object) -> None:
    raise StateChangeImmutableError("InvestorAssetStateChange is append-only and cannot be updated")


@event.listens_for(InvestorAssetStateChange, "before_delete")
def prevent_state_change_delete(*_: object) -> None:
    raise StateChangeImmutableError("InvestorAssetStateChange is append-only and cannot be deleted")
