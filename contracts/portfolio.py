"""Provider-neutral contracts for the Portfolio Fact domain."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class PortfolioStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


class PortfolioActionType(StrEnum):
    POSITION_ADDED = "POSITION_ADDED"
    POSITION_REMOVED = "POSITION_REMOVED"
    POSITION_INCREASED = "POSITION_INCREASED"
    POSITION_DECREASED = "POSITION_DECREASED"
    POSITION_UNCHANGED = "POSITION_UNCHANGED"
    POSITION_CHANGE_UNKNOWN = "POSITION_CHANGE_UNKNOWN"


class PortfolioSnapshotCompleteness(StrEnum):
    """How completely a snapshot represents the source portfolio."""

    FULL = "FULL"
    UNKNOWN = "UNKNOWN"


class InvestorActionClaimType(StrEnum):
    BUY = "BUY"
    ADD_POSITION = "ADD_POSITION"
    REDUCE_POSITION = "REDUCE_POSITION"
    SELL = "SELL"
    HOLD = "HOLD"
    UNKNOWN = "UNKNOWN"


class PortfolioDTO(BaseModel):
    """Immutable write contract for one independently identified portfolio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    source: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    status: PortfolioStatus = PortfolioStatus.UNKNOWN
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("portfolio source must not be blank")
        return normalized

    @field_validator("external_id", "name")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("portfolio external_id and name must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        if self.created_at > self.updated_at:
            raise ValueError("created_at must be earlier than or equal to updated_at")
        return self


class PortfolioView(PortfolioDTO):
    id: UUID


class PortfolioSnapshotBatchDTO(BaseModel):
    """Immutable identity for one observed portfolio snapshot batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolio_id: UUID
    snapshot_time: AwareDatetime
    source: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    completeness: PortfolioSnapshotCompleteness = PortfolioSnapshotCompleteness.FULL
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("snapshot source must not be blank")
        return normalized

    @field_validator("external_id")
    @classmethod
    def normalize_external_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("snapshot external_id must not be blank")
        return normalized

    @field_validator("snapshot_time")
    @classmethod
    def normalize_snapshot_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class PortfolioSnapshotBatchView(PortfolioSnapshotBatchDTO):
    id: UUID


class PositionSnapshotDTO(BaseModel):
    """One observed portfolio position, resolved or explicitly unresolved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolio_id: UUID
    snapshot_batch_id: UUID
    asset_id: UUID | None = None
    asset_reference_id: UUID | None = None
    weight: float | None = None
    snapshot_time: AwareDatetime
    source_type: str = Field(min_length=1, max_length=64)
    source_reference: str = Field(min_length=1, max_length=2048)
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("snapshot_time")
    @classmethod
    def normalize_snapshot_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_asset_identity(self) -> Self:
        if (self.asset_id is None) == (self.asset_reference_id is None):
            raise ValueError("exactly one of asset_id or asset_reference_id is required")
        return self

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("source_type must not be blank")
        return normalized

    @field_validator("source_reference")
    @classmethod
    def normalize_source_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_reference must not be blank")
        return normalized


class PositionSnapshotView(PositionSnapshotDTO):
    id: UUID


class PortfolioActionDTO(BaseModel):
    """Derived difference between two portfolio snapshots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolio_id: UUID
    asset_id: UUID | None = None
    asset_reference_id: UUID | None = None
    previous_snapshot_batch_id: UUID
    current_snapshot_batch_id: UUID
    previous_position_snapshot_id: UUID | None = None
    current_position_snapshot_id: UUID | None = None
    action_type: PortfolioActionType
    effective_time: AwareDatetime
    calculated_at: AwareDatetime = Field(default_factory=utc_now)
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_action_identity(self) -> Self:
        if (self.asset_id is None) == (self.asset_reference_id is None):
            raise ValueError("exactly one of asset_id or asset_reference_id is required")
        if self.previous_position_snapshot_id is None and self.current_position_snapshot_id is None:
            raise ValueError("PortfolioAction requires a previous or current position snapshot")
        return self

    @classmethod
    def from_snapshot_time(
        cls,
        *,
        portfolio_id: UUID,
        asset_id: UUID | None = None,
        asset_reference_id: UUID | None = None,
        previous_snapshot_batch_id: UUID | None = None,
        current_snapshot_batch_id: UUID | None = None,
        previous_position_snapshot_id: UUID | None = None,
        current_position_snapshot_id: UUID | None = None,
        action_type: PortfolioActionType,
        snapshot_time: datetime,
        previous_snapshot_id: UUID | None = None,
        current_snapshot_id: UUID | None = None,
        calculated_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> "PortfolioActionDTO":
        return cls(
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            asset_reference_id=asset_reference_id,
            previous_snapshot_batch_id=previous_snapshot_batch_id or previous_snapshot_id,
            current_snapshot_batch_id=current_snapshot_batch_id or current_snapshot_id,
            previous_position_snapshot_id=previous_position_snapshot_id,
            current_position_snapshot_id=current_position_snapshot_id,
            action_type=action_type,
            effective_time=snapshot_time,
            calculated_at=calculated_at or utc_now(),
            created_at=created_at or utc_now(),
        )

    @property
    def previous_snapshot_id(self) -> UUID | None:
        """Compatibility alias for the pre-provenance position field."""

        return self.previous_position_snapshot_id

    @property
    def current_snapshot_id(self) -> UUID | None:
        """Compatibility alias for the pre-provenance position field."""

        return self.current_position_snapshot_id


class PortfolioActionView(PortfolioActionDTO):
    id: UUID


class PositionChangeDetectionResult(BaseModel):
    """Result of one deterministic comparison between two snapshot batches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolio_id: UUID
    previous_snapshot_batch_id: UUID
    current_snapshot_batch_id: UUID
    action_ids: tuple[UUID, ...]
    created_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.created_count + self.reused_count != len(self.action_ids):
            raise ValueError("action counts must match returned action IDs")
        return self


class InvestorActionClaimDTO(BaseModel):
    """A separately persisted investor text claim, not a Portfolio Fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID | None = None
    asset_reference_id: UUID | None = None
    event_id: UUID
    claim_type: InvestorActionClaimType
    confidence: float = Field(ge=0, le=1)
    evidence_text: str = Field(min_length=1)
    published_time: AwareDatetime
    analysis_version: str = Field(min_length=1, max_length=255)
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_identity_and_text(self) -> Self:
        if self.asset_id is not None and self.asset_reference_id is not None:
            raise ValueError("asset_id and asset_reference_id are mutually exclusive")
        return self

    @field_validator("evidence_text", "analysis_version")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("evidence_text and analysis_version must not be blank")
        return normalized


class InvestorActionClaimView(InvestorActionClaimDTO):
    id: UUID


__all__ = [
    "InvestorActionClaimDTO",
    "InvestorActionClaimType",
    "InvestorActionClaimView",
    "PortfolioActionDTO",
    "PortfolioActionType",
    "PortfolioActionView",
    "PositionChangeDetectionResult",
    "PortfolioDTO",
    "PortfolioSnapshotBatchDTO",
    "PortfolioSnapshotBatchView",
    "PortfolioSnapshotCompleteness",
    "PortfolioStatus",
    "PortfolioView",
    "PositionSnapshotDTO",
    "PositionSnapshotView",
]
