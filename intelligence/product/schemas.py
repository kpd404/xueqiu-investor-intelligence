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


class ProductOpinionFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    opinion_id: UUID
    raw_event_id: UUID
    investor_id: UUID
    published_time: AwareDatetime
    role: Literal["THESIS_CURRENT", "THESIS_PREVIOUS", "DIRECTION_VOTE"]


class ProductAttentionFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attention_occurrence_id: UUID
    raw_event_id: UUID
    investor_id: UUID
    published_time: AwareDatetime


class ProductValidatedChain(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event_id: UUID
    signal_id: UUID
    source_type: str
    source_id: UUID
    observed_at: AwareDatetime
    source_window_start: AwareDatetime | None = None
    source_window_end: AwareDatetime | None = None
    source_as_of: AwareDatetime | None = None
    investor_ids: tuple[UUID, ...]
    direction_voter_ids: tuple[UUID, ...] = ()
    attention_only_investor_ids: tuple[UUID, ...] = ()
    opinion_facts: tuple[ProductOpinionFact, ...]
    attention_facts: tuple[ProductAttentionFact, ...] = ()
    evidence_refs: tuple[IntelligenceAttentionEvidenceRef, ...]


class ProductHistoricalAssociation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: UUID
    event_id: UUID
    signal_id: UUID


class ProductValidatedConsumption(BaseModel):
    """Only accepted ACTIVE Feed Thesis/direction associations; no recency window.

    Other Event types retain their existing consumption rules and are not certified
    by this field. Chains preserve each source window; no combined consensus.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    selection_scope: Literal["ACTIVE_FEED_THESIS_AND_DIRECTION_ASSOCIATIONS"] = (
        "ACTIVE_FEED_THESIS_AND_DIRECTION_ASSOCIATIONS"
    )
    signal_count: int = Field(ge=0)
    chains: tuple[ProductValidatedChain, ...]


class ProductTraceabilitySummary(BaseModel):
    """Legacy counts/refs retain their audit meanings, never effective-change counts.

    signal_count counts all persisted Asset Signals (including unlinked/history).
    evidence_refs is the composed Review/Evolution audit reference set, not the
    complete history or current effective set; canonical excludes intermediates.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref_count: int = Field(ge=0)
    canonical_source_count: int = Field(ge=0)
    source_types: tuple[str, ...] = ()
    signal_count: int = Field(ge=0)
    evidence_refs: tuple[IntelligenceAttentionEvidenceRef, ...] = ()
    historical_signal_ids: tuple[UUID, ...] = ()
    historical_associations: tuple[ProductHistoricalAssociation, ...] = ()
    validated_consumption: ProductValidatedConsumption | None = None


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
