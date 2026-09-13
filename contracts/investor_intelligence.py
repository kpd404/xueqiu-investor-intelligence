"""Provider-neutral, read-only Investor-centric Intelligence contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.attention import AttentionEvidenceType
from contracts.cross_investor import (
    ConsensusEvidenceState,
    DirectionalAlignmentState,
    OpinionCoverageState,
)
from contracts.enums import OpinionDirection
from contracts.observed_attention import ObservedAttentionCompleteness

INVESTOR_INTELLIGENCE_LIMITATION_HISTORICAL_COMPLETENESS = "HISTORICAL_COMPLETENESS_UNKNOWN"
INVESTOR_INTELLIGENCE_LIMITATION_ABSENCE_INFERENCE = "ABSENCE_INFERENCE_UNSUPPORTED"
INVESTOR_INTELLIGENCE_LIMITATION_COLLECTION_PROVENANCE = "COLLECTION_PROVENANCE_UNAVAILABLE"
INVESTOR_INTELLIGENCE_LIMITATION_LATEST_DIRECTION = "LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY"
INVESTOR_INTELLIGENCE_LIMITATION_MISSING_THESIS = "MISSING_THESIS_COMPARISON"
INVESTOR_INTELLIGENCE_LIMITATION_CROSS_INVESTOR = "CROSS_INVESTOR_LINEAGE_UNAVAILABLE"


class InvestorAssetIntelligenceSummary(BaseModel):
    """One Investor's observed evidence summary for one listing identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)

    attention_occurrence_count: int = Field(ge=0)
    first_attention_time: AwareDatetime | None = None
    latest_attention_time: AwareDatetime | None = None
    attention_evidence_types: tuple[AttentionEvidenceType, ...] = ()

    opinion_count: int = Field(ge=0)
    first_opinion_time: AwareDatetime | None = None
    latest_opinion_time: AwareDatetime | None = None
    latest_observed_direction: OpinionDirection | None = None

    thesis_change_count: int = Field(ge=0)
    changed_count: int = Field(ge=0)
    extended_count: int = Field(ge=0)
    reversal_count: int = Field(ge=0)
    missing_thesis_comparison_count: int = Field(ge=0)

    attention_investor_count: int = Field(ge=0)
    opinion_investor_count: int = Field(ge=0)
    shared_attention_investor_count: int = Field(ge=0)
    shared_opinion_investor_count: int = Field(ge=0)
    latest_evidence_time: AwareDatetime | None = None
    alignment: DirectionalAlignmentState | None = None
    consensus: ConsensusEvidenceState | None = None

    @property
    def has_repeated_opinion(self) -> bool:
        """Whether this Investor has more than one observed Opinion on the Asset."""

        return self.opinion_count >= 2


class InvestorOverlapSummary(BaseModel):
    """Set intersection counts with another Investor, without a similarity score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    other_investor_id: UUID
    other_investor_name: str = Field(min_length=1, max_length=255)
    shared_attention_asset_count: int = Field(ge=0)
    shared_opinion_asset_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_non_empty_overlap(self) -> InvestorOverlapSummary:
        if self.shared_attention_asset_count == 0 and self.shared_opinion_asset_count == 0:
            raise ValueError("Investor overlap must contain at least one shared Asset")
        return self


class InvestorIntelligenceDataQuality(BaseModel):
    """Explicit observed-history limitations for an Investor view."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    absence_inference_supported: bool = False
    collection_provenance_available: bool = False
    opinion_coverage: OpinionCoverageState
    missing_thesis_comparison_count: int = Field(ge=0)
    cross_investor_lineage_available: bool = False
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_boundaries(self) -> InvestorIntelligenceDataQuality:
        if self.completeness is ObservedAttentionCompleteness.UNKNOWN and (
            INVESTOR_INTELLIGENCE_LIMITATION_HISTORICAL_COMPLETENESS not in self.limitations
        ):
            raise ValueError("UNKNOWN completeness requires an explicit limitation")
        if not self.absence_inference_supported and (
            INVESTOR_INTELLIGENCE_LIMITATION_ABSENCE_INFERENCE not in self.limitations
        ):
            raise ValueError("unsupported absence inference requires an explicit limitation")
        if not self.collection_provenance_available and (
            INVESTOR_INTELLIGENCE_LIMITATION_COLLECTION_PROVENANCE not in self.limitations
        ):
            raise ValueError("unavailable collection provenance requires an explicit limitation")
        if not self.cross_investor_lineage_available and (
            INVESTOR_INTELLIGENCE_LIMITATION_CROSS_INVESTOR not in self.limitations
        ):
            raise ValueError("unavailable cross-investor lineage requires an explicit limitation")
        if self.missing_thesis_comparison_count and (
            INVESTOR_INTELLIGENCE_LIMITATION_MISSING_THESIS not in self.limitations
        ):
            raise ValueError("missing Thesis comparisons require an explicit limitation")
        return self


class InvestorIntelligenceView(BaseModel):
    """Observed evidence for one Investor over one fact-time window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    window_start: AwareDatetime
    window_end: AwareDatetime
    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    first_observed_evidence_time: AwareDatetime | None = None
    latest_observed_evidence_time: AwareDatetime | None = None
    attention_asset_count: int = Field(ge=0)
    opinion_asset_count: int = Field(ge=0)
    repeated_opinion_asset_count: int = Field(ge=0)
    thesis_changed_asset_count: int = Field(ge=0)
    direction_reversal_asset_count: int = Field(ge=0)
    shared_attention_asset_count: int = Field(ge=0)
    shared_opinion_asset_count: int = Field(ge=0)
    asset_views: tuple[InvestorAssetIntelligenceSummary, ...] = ()
    overlap_summaries: tuple[InvestorOverlapSummary, ...] = ()
    data_quality: InvestorIntelligenceDataQuality

    @model_validator(mode="after")
    def validate_view(self) -> InvestorIntelligenceView:
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        asset_ids = [item.asset_id for item in self.asset_views]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("asset_views must contain one entry per Asset listing")
        if self.attention_asset_count != sum(
            item.attention_occurrence_count > 0 for item in self.asset_views
        ):
            raise ValueError("attention_asset_count must match asset views")
        if self.opinion_asset_count != sum(item.opinion_count > 0 for item in self.asset_views):
            raise ValueError("opinion_asset_count must match asset views")
        if self.repeated_opinion_asset_count != sum(
            item.has_repeated_opinion for item in self.asset_views
        ):
            raise ValueError("repeated_opinion_asset_count must match asset views")
        if self.thesis_changed_asset_count != sum(
            item.changed_count > 0 for item in self.asset_views
        ):
            raise ValueError("thesis_changed_asset_count must match asset views")
        if self.direction_reversal_asset_count != sum(
            item.reversal_count > 0 for item in self.asset_views
        ):
            raise ValueError("direction_reversal_asset_count must match asset views")
        if self.shared_attention_asset_count != sum(
            item.attention_occurrence_count > 0 and item.shared_attention_investor_count > 0
            for item in self.asset_views
        ):
            raise ValueError("shared_attention_asset_count must match asset views")
        if self.shared_opinion_asset_count != sum(
            item.opinion_count > 0 and item.shared_opinion_investor_count > 0
            for item in self.asset_views
        ):
            raise ValueError("shared_opinion_asset_count must match asset views")
        if self.data_quality.completeness is not self.completeness:
            raise ValueError("data quality completeness must match the view")
        return self


__all__ = [
    "INVESTOR_INTELLIGENCE_LIMITATION_ABSENCE_INFERENCE",
    "INVESTOR_INTELLIGENCE_LIMITATION_COLLECTION_PROVENANCE",
    "INVESTOR_INTELLIGENCE_LIMITATION_CROSS_INVESTOR",
    "INVESTOR_INTELLIGENCE_LIMITATION_HISTORICAL_COMPLETENESS",
    "INVESTOR_INTELLIGENCE_LIMITATION_LATEST_DIRECTION",
    "INVESTOR_INTELLIGENCE_LIMITATION_MISSING_THESIS",
    "InvestorAssetIntelligenceSummary",
    "InvestorIntelligenceDataQuality",
    "InvestorIntelligenceView",
    "InvestorOverlapSummary",
]
