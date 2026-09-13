"""Thin HTTP response projections for the existing Combined View contract."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from contracts import (
    ConsensusEvidenceState,
    DirectionalAlignmentState,
    ObservedAttentionCompleteness,
)
from contracts.combined_asset_intelligence import (
    CombinedAssetIntelligenceView,
    CombinedAssetTimelineEvent,
)


class AssetIntelligenceSummaryResponse(BaseModel):
    """Bounded Asset list projection without full timelines."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str
    market: str
    symbol: str
    attention_investor_count: int = Field(ge=0)
    attention_occurrence_count: int = Field(ge=0)
    opinion_investor_count: int = Field(ge=0)
    opinion_count: int = Field(ge=0)
    earliest_observed_time: datetime | None
    latest_evidence_time: datetime | None
    latest_alignment: DirectionalAlignmentState | None
    latest_consensus: ConsensusEvidenceState | None
    completeness: ObservedAttentionCompleteness
    data_quality_flags: tuple[str, ...] = ()

    @classmethod
    def from_view(cls, view: CombinedAssetIntelligenceView) -> "AssetIntelligenceSummaryResponse":
        opinion_count = sum(item.opinion_count for item in view.investor_views)
        opinion_investor_count = sum(item.opinion_count > 0 for item in view.investor_views)
        evidence_times = [event.published_time for event in view.event_timeline]
        evidence_times.extend(
            item.latest_attention_time
            for item in view.investor_views
            if item.latest_attention_time is not None
        )
        evidence_times.extend(
            item.latest_opinion_time
            for item in view.investor_views
            if item.latest_opinion_time is not None
        )
        flags = list(view.data_quality.unresolved_semantic_limitations)
        if (
            view.data_quality.missing_thesis_comparison_count
            and "MISSING_THESIS_COMPARISON" not in flags
        ):
            flags.append("MISSING_THESIS_COMPARISON")
        if (
            not view.data_quality.cross_investor_evidence_available
            and "CROSS_INVESTOR_LINEAGE_UNAVAILABLE" not in flags
        ):
            flags.append("CROSS_INVESTOR_LINEAGE_UNAVAILABLE")
        return cls(
            asset_id=view.asset_id,
            asset_name=view.asset_name,
            market=view.market,
            symbol=view.symbol,
            attention_investor_count=view.attention_summary.attention_investor_count,
            attention_occurrence_count=view.attention_summary.attention_occurrence_count,
            opinion_investor_count=opinion_investor_count,
            opinion_count=opinion_count,
            earliest_observed_time=view.attention_summary.earliest_observed_time,
            latest_evidence_time=max(evidence_times) if evidence_times else None,
            latest_alignment=(
                view.alignment.directional_alignment_state if view.alignment else None
            ),
            latest_consensus=view.consensus.consensus_state if view.consensus else None,
            completeness=view.completeness,
            data_quality_flags=tuple(flags),
        )


class AssetIntelligenceListResponse(BaseModel):
    """Paginated Asset summary response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[AssetIntelligenceSummaryResponse, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    has_more: bool


class AssetIntelligenceTimelineResponse(BaseModel):
    """Thin HTTP projection of the Combined View unified event timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str
    market: str
    symbol: str
    window_start: datetime
    window_end: datetime
    completeness: ObservedAttentionCompleteness
    events: tuple[CombinedAssetTimelineEvent, ...]
    missing_thesis_comparison_count: int = Field(ge=0)
    data_quality_flags: tuple[str, ...] = ()

    @classmethod
    def from_view(cls, view: CombinedAssetIntelligenceView) -> "AssetIntelligenceTimelineResponse":
        return cls(
            asset_id=view.asset_id,
            asset_name=view.asset_name,
            market=view.market,
            symbol=view.symbol,
            window_start=view.window_start,
            window_end=view.window_end,
            completeness=view.completeness,
            events=view.event_timeline,
            missing_thesis_comparison_count=(view.data_quality.missing_thesis_comparison_count),
            data_quality_flags=view.data_quality.unresolved_semantic_limitations,
        )
