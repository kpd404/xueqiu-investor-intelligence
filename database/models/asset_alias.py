from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base

if TYPE_CHECKING:
    from database.models.asset import Asset


class AssetAlias(Base):
    """An explicit alternate identity for one canonical Asset."""

    __tablename__ = "asset_aliases"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "normalized_alias",
            name="asset_alias_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str | None] = mapped_column(String(32), index=True)

    asset: Mapped["Asset"] = relationship(back_populates="aliases")
