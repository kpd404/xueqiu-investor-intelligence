"""Stable query-time contract for the Asset Intelligence Product View."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts import (
    IntelligenceAttentionClass,
    IntelligenceAttentionEvidenceRef,
    IntelligenceAttentionReason,
)
from intelligence.context.schemas import (
    ActivityContext,
    AttentionContext,
    InvestorContext,
    ThesisContext,
    TimelineContext,
)
from intelligence.evolution.schemas import EvolutionStep, EvolutionTimelineRange
from intelligence.schemas.discovery import DiscoveryActivitySummary


class ProductAssetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class ProductReviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attention_class: IntelligenceAttentionClass
    reasons: tuple[IntelligenceAttentionReason, ...] = ()
    latest_observed_at: AwareDatetime | None = None


class ProductDiscoveryView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    is_discoverable: bool
    discovery_reasons: tuple[str, ...] = ()
    activity_summary: DiscoveryActivitySummary | None = None


class ProductCurrentStateView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alignment: str | None = None
    consensus: str | None = None
    patterns: tuple[str, ...] = ()


class ProductContextView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    activity_context: ActivityContext
    investor_context: InvestorContext
    attention_context: AttentionContext
    thesis_context: ThesisContext
    timeline_context: TimelineContext


class ProductNarrativeView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    attention_summary: str = Field(min_length=1)
    thesis_summary: str = Field(min_length=1)
    cross_investor_summary: str = Field(min_length=1)
    consensus_summary: str = Field(min_length=1)


class ProductEvolutionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeline_range: EvolutionTimelineRange
    step_count: int = Field(ge=0)
    recent_steps: tuple[EvolutionStep, ...] = ()


class ProductLifecycleSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    active_count: int = Field(ge=0)
    states: dict[str, int] = Field(default_factory=dict)


class ProductDataQualityView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    historical_completeness: Literal["UNKNOWN"] = "UNKNOWN"
    historical_comparison_supported: bool = False
    absence_inference_supported: bool = False
    limitations: tuple[str, ...] = ()


class ProductTraceabilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref_count: int = Field(ge=0)
    canonical_source_count: int = Field(ge=0)
    source_types: tuple[str, ...] = ()
    signal_count: int = Field(ge=0)
    evidence_refs: tuple[IntelligenceAttentionEvidenceRef, ...] = ()


class AssetIntelligenceView(BaseModel):
    """One stable Product composition; it adds no new Intelligence semantic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset: ProductAssetIdentity
    review: ProductReviewView
    discovery: ProductDiscoveryView
    current_state: ProductCurrentStateView
    context: ProductContextView
    narrative: ProductNarrativeView
    evolution: ProductEvolutionView
    feed: ProductLifecycleSummary
    events: ProductLifecycleSummary
    data_quality: ProductDataQualityView
    traceability_summary: ProductTraceabilitySummary


__all__ = [
    "AssetIntelligenceView",
    "ProductAssetIdentity",
    "ProductContextView",
    "ProductCurrentStateView",
    "ProductDataQualityView",
    "ProductDiscoveryView",
    "ProductEvolutionView",
    "ProductLifecycleSummary",
    "ProductNarrativeView",
    "ProductReviewView",
    "ProductTraceabilitySummary",
]
