from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from contracts.analysis import AnalysisSpec, EventAnalysisStatus
from contracts.enums import OpinionDirection


def utc_now() -> datetime:
    return datetime.now(UTC)


class AssetOpinionExtraction(BaseModel):
    """Extractor-owned investment interpretation without trusted identity fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_name: str = Field(min_length=1, max_length=255)
    symbol: str = Field(min_length=1, max_length=64)
    market: str = Field(min_length=1, max_length=32)
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)

    @field_validator("asset_name", "symbol", "market")
    @classmethod
    def normalize_identity_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("asset identity fields must not be blank")
        return normalized

    @field_validator("symbol", "market")
    @classmethod
    def normalize_market_identity(cls, value: str) -> str:
        return value.upper()


class OpinionExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investment_related: bool
    opinions: tuple[AssetOpinionExtraction, ...] = ()
    model_version: str = Field(min_length=1, max_length=255)
    analysis_spec: AnalysisSpec | None = None

    @model_validator(mode="after")
    def validate_opinion_consistency(self) -> Self:
        if self.investment_related != bool(self.opinions):
            raise ValueError("investment_related must match whether opinions are present")
        identities = [(opinion.market, opinion.symbol) for opinion in self.opinions]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate market/symbol opinions are not allowed")
        if (
            self.analysis_spec is not None
            and self.analysis_spec.model_version != self.model_version
        ):
            raise ValueError("analysis_spec.model_version must match model_version")
        return self


class OpinionCreate(BaseModel):
    """System-owned persistence command built after asset resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    analysis_id: UUID | None = None
    investor_id: UUID
    asset_id: UUID
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)
    generated_time: AwareDatetime = Field(default_factory=utc_now)
    model_version: str = Field(min_length=1, max_length=255)


class OpinionWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opinion_ids: tuple[UUID, ...]
    created_count: int = Field(ge=0)


class UnresolvedAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_name: str
    symbol: str
    market: str
    reason: str = "NOT_FOUND_OR_AMBIGUOUS"


class OpinionProcessingStatus(StrEnum):
    PROCESSED = "PROCESSED"
    NO_OPINION = "NO_OPINION"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    FAILED = "FAILED"


class OpinionProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    opinion_ids: tuple[UUID, ...]
    unresolved_assets: tuple[UnresolvedAsset, ...]
    model_version: str
    status: OpinionProcessingStatus
    analysis_id: UUID | None = None
    analysis_version: str | None = None
    analysis_status: EventAnalysisStatus | None = None
