"""Contracts for importing external Portfolio position snapshots."""

from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.portfolio import PortfolioSnapshotCompleteness


def utc_now() -> datetime:
    return datetime.now(UTC)


class PortfolioPositionInput(BaseModel):
    """One externally supplied position inside a portfolio snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_name: str = Field(min_length=1, max_length=255)
    symbol: str | None = Field(default=None, max_length=64)
    market: str | None = Field(default=None, max_length=32)
    weight: float | None = None
    source_reference: str | None = Field(default=None, max_length=2048)

    @field_validator("asset_name", "source_reference")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be blank")
        return normalized

    @field_validator("symbol", "market")
    @classmethod
    def normalize_optional_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PortfolioSnapshotImportCommand(BaseModel):
    """Immutable command for importing one complete external snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    portfolio_name: str = Field(min_length=1, max_length=255)
    investor_id: UUID
    snapshot_time: AwareDatetime
    completeness: PortfolioSnapshotCompleteness = PortfolioSnapshotCompleteness.FULL
    positions: tuple[PortfolioPositionInput, ...] = ()

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("source must not be blank")
        return normalized

    @field_validator("external_id", "portfolio_name")
    @classmethod
    def normalize_identity_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_id and portfolio_name must not be blank")
        return normalized

    @field_validator("snapshot_time")
    @classmethod
    def normalize_snapshot_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class PortfolioSnapshotImportResult(BaseModel):
    """Persistence result for one imported snapshot command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolio_id: UUID
    snapshot_batch_id: UUID
    portfolio_created: bool
    batch_created: bool
    batch_reused: bool
    position_snapshot_ids: tuple[UUID, ...]
    created_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.created_count + self.reused_count != len(self.position_snapshot_ids):
            raise ValueError("snapshot counts must match returned snapshot IDs")
        if self.resolved_count + self.unresolved_count != len(self.position_snapshot_ids):
            raise ValueError("resolution counts must match returned snapshot IDs")
        if self.batch_created == self.batch_reused:
            raise ValueError("exactly one of batch_created or batch_reused must be true")
        return self

    @property
    def snapshot_ids(self) -> tuple[UUID, ...]:
        """Short compatibility alias for callers that use snapshot terminology."""

        return self.position_snapshot_ids

    @property
    def batch_id(self) -> UUID:
        return self.snapshot_batch_id


__all__ = [
    "PortfolioPositionInput",
    "PortfolioSnapshotImportCommand",
    "PortfolioSnapshotImportResult",
]
