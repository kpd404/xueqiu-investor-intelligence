"""Product-facing composition contracts for Combined Asset Intelligence V0."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.attention import AttentionEvidenceType
from contracts.cross_investor import (
    CrossInvestorAssetAlignmentView,
    CrossInvestorAssetSnapshotView,
    CrossInvestorConsensusEvidenceView,
    OpinionCoverageState,
)
from contracts.enums import OpinionDirection
from contracts.observed_attention import (
    ObservedAttentionCompleteness,
    ObservedAttentionEdge,
    ObservedAttentionSequence,
)
from contracts.thesis_change import ThesisChangeType
from contracts.thesis_evolution import ThesisEvolutionTimeline


class CombinedAttentionOpinionRelation(StrEnum):
    """Observed temporal relation between first Attention and first Opinion."""

    OPINION_AT_FIRST_ATTENTION = "OPINION_AT_FIRST_ATTENTION"
    OPINION_AFTER_ATTENTION = "OPINION_AFTER_ATTENTION"
    ATTENTION_WITHOUT_OPINION = "ATTENTION_WITHOUT_OPINION"
    OPINION_WITHOUT_PRIOR_ATTENTION = "OPINION_WITHOUT_PRIOR_ATTENTION"
    SIMULTANEOUS = "SIMULTANEOUS"


class CombinedAssetTimelineEventType(StrEnum):
    """Presentation events supported by the Combined Asset timeline."""

    ATTENTION_FIRST_OBSERVED = "ATTENTION_FIRST_OBSERVED"
    ATTENTION_OBSERVED = "ATTENTION_OBSERVED"
    OPINION_OBSERVED = "OPINION_OBSERVED"
    THESIS_CHANGE_OBSERVED = "THESIS_CHANGE_OBSERVED"


class CombinedAssetAttentionSummary(BaseModel):
    """Deterministic summary of effective Attention evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attention_investor_count: int = Field(ge=0)
    attention_occurrence_count: int = Field(ge=0)
    earliest_observed_time: AwareDatetime | None = None
    earliest_observed_investor_id: UUID | None = None
    earliest_observed_investor_name: str | None = Field(default=None, max_length=255)
    observed_span_seconds: float | None = Field(default=None, ge=0)
    observed_span_hours: float | None = Field(default=None, ge=0)
    observed_span_days: float | None = Field(default=None, ge=0)
    temporal_edges: tuple[ObservedAttentionEdge, ...] = ()


class CombinedAssetInvestorView(BaseModel):
    """One Investor's independent Attention, Opinion, and Thesis context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    first_attention_time: AwareDatetime | None = None
    latest_attention_time: AwareDatetime | None = None
    attention_occurrence_count: int = Field(ge=0)
    attention_evidence_types: tuple[AttentionEvidenceType, ...] = ()
    first_attention_raw_event_id: UUID | None = None
    opinion_count: int = Field(ge=0)
    first_opinion_time: AwareDatetime | None = None
    latest_opinion_time: AwareDatetime | None = None
    latest_observed_direction: OpinionDirection | None = None
    latest_observed_confidence: float | None = Field(default=None, ge=0, le=1)
    thesis_change_count: int = Field(ge=0)
    latest_thesis_change_type: ThesisChangeType | None = None
    reversal_count: int = Field(ge=0)
    changed_count: int = Field(ge=0)
    extended_count: int = Field(ge=0)
    missing_thesis_comparison_count: int = Field(ge=0)
    thesis_timeline: ThesisEvolutionTimeline | None = None
    attention_opinion_relation: CombinedAttentionOpinionRelation
    attention_to_first_opinion_lag: float | None = None
    attention_to_first_opinion_lag_hours: float | None = None
    attention_to_first_opinion_lag_days: float | None = None


class CombinedAssetDataQuality(BaseModel):
    """Explicit limitations and coverage information for product consumers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    opinion_coverage: OpinionCoverageState | None = None
    missing_thesis_comparison_count: int = Field(ge=0)
    cross_investor_evidence_available: bool
    unresolved_semantic_limitations: tuple[str, ...] = ()


class CombinedAssetTimelineEvent(BaseModel):
    """One traceable event in the combined product presentation timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    published_time: AwareDatetime
    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    event_type: CombinedAssetTimelineEventType
    evidence_types: tuple[AttentionEvidenceType, ...] = ()
    direction: OpinionDirection | None = None
    thesis_change_type: ThesisChangeType | None = None
    attention_occurrence_id: UUID | None = None
    opinion_id: UUID | None = None
    event_analysis_id: UUID | None = None
    raw_event_id: UUID | None = None
    thesis_change_id: UUID | None = None
    predecessor_opinion_id: UUID | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> "CombinedAssetTimelineEvent":
        if self.event_type in {
            CombinedAssetTimelineEventType.ATTENTION_FIRST_OBSERVED,
            CombinedAssetTimelineEventType.ATTENTION_OBSERVED,
        }:
            if self.attention_occurrence_id is None or self.raw_event_id is None:
                raise ValueError("Attention timeline events require Attention and RawEvent ids")
        else:
            if (
                self.opinion_id is None
                or self.event_analysis_id is None
                or self.raw_event_id is None
            ):
                raise ValueError(
                    "Opinion timeline events require Opinion, Analysis, and RawEvent ids"
                )
        if self.event_type is CombinedAssetTimelineEventType.THESIS_CHANGE_OBSERVED:
            if self.thesis_change_id is None or self.thesis_change_type is None:
                raise ValueError("Thesis timeline events require ThesisChange provenance")
        return self


class CombinedAssetIntelligenceView(BaseModel):
    """Asset-centric read model composed from existing effective evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    window_start: AwareDatetime
    window_end: AwareDatetime
    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    attention_summary: CombinedAssetAttentionSummary
    observed_attention_sequence: ObservedAttentionSequence | None = None
    investor_views: tuple[CombinedAssetInvestorView, ...] = ()
    snapshot: CrossInvestorAssetSnapshotView | None = None
    alignment: CrossInvestorAssetAlignmentView | None = None
    consensus: CrossInvestorConsensusEvidenceView | None = None
    data_quality: CombinedAssetDataQuality
    event_timeline: tuple[CombinedAssetTimelineEvent, ...] = ()

    @property
    def temporal_edges(self) -> tuple[ObservedAttentionEdge, ...]:
        """Compatibility convenience for the Attention summary edge set."""

        return self.attention_summary.temporal_edges

    @model_validator(mode="after")
    def validate_composed_view(self) -> "CombinedAssetIntelligenceView":
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if self.data_quality.completeness is not self.completeness:
            raise ValueError("data quality completeness must match the view")
        if self.observed_attention_sequence is not None:
            if self.observed_attention_sequence.asset_id != self.asset_id:
                raise ValueError("Attention sequence must belong to the view Asset")
        if self.snapshot is not None and self.snapshot.asset_id != self.asset_id:
            raise ValueError("Snapshot must belong to the view Asset")
        if self.alignment is not None and self.alignment.asset_id != self.asset_id:
            raise ValueError("Alignment must belong to the view Asset")
        if self.consensus is not None and self.consensus.asset_id != self.asset_id:
            raise ValueError("Consensus must belong to the view Asset")
        investor_ids = [item.investor_id for item in self.investor_views]
        if len(investor_ids) != len(set(investor_ids)):
            raise ValueError("investor_views must contain one entry per Investor")
        if any(
            left.published_time > right.published_time
            for left, right in zip(self.event_timeline, self.event_timeline[1:], strict=False)
        ):
            raise ValueError("event_timeline must be ordered by published_time")
        if any(
            not self.window_start <= event.published_time <= self.window_end
            for event in self.event_timeline
        ):
            raise ValueError("event_timeline events must fall inside the requested window")
        return self


__all__ = [
    "CombinedAssetAttentionSummary",
    "CombinedAssetDataQuality",
    "CombinedAssetIntelligenceView",
    "CombinedAssetInvestorView",
    "CombinedAssetTimelineEvent",
    "CombinedAssetTimelineEventType",
    "CombinedAttentionOpinionRelation",
]
