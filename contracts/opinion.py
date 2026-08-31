from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from contracts.analysis import AnalysisSpec, EventAnalysisStatus
from contracts.asset_resolution import AssetReference
from contracts.enums import OpinionDirection


def utc_now() -> datetime:
    return datetime.now(UTC)


class AssetOpinionExtraction(BaseModel):
    """Extractor-owned investment interpretation without trusted identity fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_name: str = Field(min_length=1, max_length=255)
    symbol: str | None = Field(default=None, max_length=64)
    market: str | None = Field(default=None, max_length=32)
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)

    @field_validator("asset_name", "symbol", "market")
    @classmethod
    def normalize_identity_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("asset identity fields must not be blank")
        return normalized

    @field_validator("symbol", "market")
    @classmethod
    def normalize_market_identity(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    def to_asset_reference(self) -> AssetReference:
        return AssetReference(
            name_hint=self.asset_name,
            symbol_hint=self.symbol,
            market_hint=self.market,
        )


class UnresolvedAssetHint(BaseModel):
    """Textual asset reference that is not safe to resolve to an Asset yet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_name: str = Field(min_length=1, max_length=255)
    symbol: str | None = Field(default=None, max_length=64)
    market: str | None = Field(default=None, max_length=32)
    reason: str = Field(default="NOT_FOUND_OR_AMBIGUOUS", min_length=1, max_length=255)
    direction: OpinionDirection | None = None
    strength: float | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)


class OpinionExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investment_related: bool
    opinions: tuple[AssetOpinionExtraction, ...] = ()
    model_version: str = Field(min_length=1, max_length=255)
    analysis_spec: AnalysisSpec | None = None
    # Provider metadata is attached after model parsing; keep the model schema closed.
    provider_metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )
    unresolved_assets: tuple[UnresolvedAssetHint, ...] = ()

    @model_validator(mode="after")
    def validate_opinion_consistency(self) -> Self:
        if self.investment_related != bool(self.opinions or self.unresolved_assets):
            raise ValueError("investment_related must match opinions or unresolved assets")
        identities = [
            (opinion.market, opinion.symbol)
            if opinion.market is not None or opinion.symbol is not None
            else ("name", opinion.asset_name)
            for opinion in self.opinions
        ]
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

    asset_name: str = Field(min_length=1, max_length=255)
    symbol: str | None = Field(default=None, max_length=64)
    market: str | None = Field(default=None, max_length=32)
    reason: str = Field(default="NOT_FOUND_OR_AMBIGUOUS", min_length=1, max_length=255)
    candidate_asset_ids: tuple[UUID, ...] = ()
    direction: OpinionDirection | None = None
    strength: float | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)

    @classmethod
    def from_extraction(
        cls,
        extraction: AssetOpinionExtraction,
        *,
        reason: str = "NOT_FOUND_OR_AMBIGUOUS",
        candidate_asset_ids: tuple[UUID, ...] = (),
    ) -> "UnresolvedAsset":
        return cls(
            asset_name=extraction.asset_name,
            symbol=extraction.symbol,
            market=extraction.market,
            reason=reason,
            candidate_asset_ids=candidate_asset_ids,
            direction=extraction.direction,
            strength=extraction.strength,
            confidence=extraction.confidence,
            thesis=extraction.thesis,
            catalysts=extraction.catalysts,
            risks=extraction.risks,
            time_horizon=extraction.time_horizon,
        )

    @classmethod
    def from_hint(cls, hint: UnresolvedAssetHint) -> "UnresolvedAsset":
        return cls(**hint.model_dump())

    def to_asset_reference(self) -> AssetReference:
        return AssetReference(
            name_hint=self.asset_name,
            symbol_hint=self.symbol,
            market_hint=self.market,
        )


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
