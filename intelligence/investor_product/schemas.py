"""Query-time Investor Intelligence Product contract."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts import AttentionEvidenceType, OpinionDirection


class InvestorProductIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    name: str = Field(min_length=1, max_length=255)
    source_platform: str = Field(min_length=1, max_length=64)
    source_user_id: str = Field(min_length=1, max_length=255)


class InvestorProductAssetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class InvestorProductAttention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurrence_count: int = Field(ge=0)
    first_observed_at: AwareDatetime | None = None
    latest_observed_at: AwareDatetime | None = None
    evidence_types: tuple[AttentionEvidenceType, ...] = ()


class InvestorProductOpinion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opinion_count: int = Field(ge=0)
    latest_direction: OpinionDirection | None = None
    latest_opinion_at: AwareDatetime | None = None
    latest_opinion_id: UUID | None = None


class InvestorProductThesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    thesis_change_count: int = Field(ge=0)
    latest_change_type: str | None = None
    latest_change_at: AwareDatetime | None = None
    latest_thesis_change_id: UUID | None = None


class InvestorProductRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    has_attention: bool
    has_opinion: bool
    attention_only: bool


class InvestorProductTraceability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attention_occurrence_ids: tuple[UUID, ...] = ()
    raw_event_ids: tuple[UUID, ...] = ()
    opinion_ids: tuple[UUID, ...] = ()
    thesis_change_ids: tuple[UUID, ...] = ()


class InvestorAssetIntelligenceView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset: InvestorProductAssetIdentity
    attention: InvestorProductAttention
    opinion: InvestorProductOpinion
    thesis: InvestorProductThesis
    relationship: InvestorProductRelationship
    latest_observed_at: AwareDatetime | None = None
    traceability: InvestorProductTraceability


class InvestorProductSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_asset_count: int = Field(ge=0)
    opinion_asset_count: int = Field(ge=0)
    thesis_change_count: int = Field(ge=0)
    attention_occurrence_count: int = Field(ge=0)
    opinion_count: int = Field(ge=0)
    latest_observed_at: AwareDatetime | None = None


class InvestorProductCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_assets: tuple[InvestorProductAssetIdentity, ...] = ()
    opinion_assets: tuple[InvestorProductAssetIdentity, ...] = ()
    attention_only_assets: tuple[InvestorProductAssetIdentity, ...] = ()


class InvestorProductActivityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_at: AwareDatetime
    event_type: Literal["ATTENTION_OBSERVED", "OPINION_RECORDED", "THESIS_CHANGE_OBSERVED"]
    asset: InvestorProductAssetIdentity
    source_refs: tuple[tuple[str, UUID], ...] = ()


class InvestorProductDataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    historical_completeness: Literal["UNKNOWN"] = "UNKNOWN"
    historical_comparison_supported: bool = False
    absence_inference_supported: bool = False
    limitations: tuple[str, ...] = ()


class InvestorProductTraceabilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attention_occurrence_ref_count: int = Field(ge=0)
    raw_event_ref_count: int = Field(ge=0)
    opinion_ref_count: int = Field(ge=0)
    thesis_change_ref_count: int = Field(ge=0)
    activity_source_ref_count: int = Field(ge=0)


class InvestorIntelligenceView(BaseModel):
    """Unified Investor Product composition without new Intelligence semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor: InvestorProductIdentity
    window_start: AwareDatetime
    window_end: AwareDatetime
    summary: InvestorProductSummary
    coverage: InvestorProductCoverage
    asset_views: tuple[InvestorAssetIntelligenceView, ...] = ()
    recent_activity: tuple[InvestorProductActivityEvent, ...] = ()
    data_quality: InvestorProductDataQuality
    traceability_summary: InvestorProductTraceabilitySummary


__all__ = [
    "InvestorAssetIntelligenceView",
    "InvestorIntelligenceView",
    "InvestorProductActivityEvent",
    "InvestorProductAttention",
    "InvestorProductCoverage",
    "InvestorProductDataQuality",
    "InvestorProductIdentity",
    "InvestorProductOpinion",
    "InvestorProductRelationship",
    "InvestorProductSummary",
    "InvestorProductThesis",
    "InvestorProductTraceability",
    "InvestorProductTraceabilitySummary",
]
