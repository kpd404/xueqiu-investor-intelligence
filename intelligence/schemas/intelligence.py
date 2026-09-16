"""Provider-neutral read contracts for the Intelligence Query Layer.

These models are projections only.  They intentionally contain no persistence
identity for a new Signal and no derived score or ranking field.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts import (
    AttentionEvidenceType,
    CombinedAssetDataQuality,
    CombinedAssetTimelineEventType,
    ConsensusEvidenceState,
    DirectionalAlignmentState,
    InvestorIntelligenceDataQuality,
    ObservedAttentionCompleteness,
    OpinionDirection,
    ThesisChangeType,
)


class InvestorAttentionAssetView(BaseModel):
    """Observed Attention for one Investor × Asset listing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    attention_count: int = Field(ge=1)
    first_observed_time: AwareDatetime | None = None
    latest_observed_time: AwareDatetime | None = None
    evidence_types: tuple[AttentionEvidenceType, ...] = ()


class InvestorOpinionAssetView(BaseModel):
    """Observed Opinion summary for one Investor × Asset listing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    opinion_count: int = Field(ge=1)
    direction: OpinionDirection | None = None
    published_time: AwareDatetime | None = None
    opinion_summary: tuple[str, ...] = ()


class InvestorAttentionSummary(BaseModel):
    """Small Attention summary; ordering is explicit, never a score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_attention_assets: int = Field(ge=0)
    recent_attention_assets: tuple[InvestorAttentionAssetView, ...] = ()
    strongest_attention_assets: tuple[InvestorAttentionAssetView, ...] = ()


class InvestorOpinionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_opinion_assets: int = Field(ge=0)
    bullish_count: int = Field(ge=0)
    bearish_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)


class InvestorThesisChangeView(BaseModel):
    """One existing ThesisChange projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    effective_time: AwareDatetime
    change_type: ThesisChangeType
    previous_direction: OpinionDirection | None = None
    current_direction: OpinionDirection
    opinion_id: UUID | None = None
    thesis_change_id: UUID | None = None


class InvestorThesisSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    thesis_change_count: int = Field(ge=0)
    latest_thesis_changes: tuple[InvestorThesisChangeView, ...] = ()


class InvestorSharedSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    shared_attention_assets: tuple[InvestorAttentionAssetView, ...] = ()
    shared_opinion_assets: tuple[InvestorOpinionAssetView, ...] = ()


class InvestorTimelineEvent(BaseModel):
    """Recent event projection retaining existing event-type semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime
    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    event_type: CombinedAssetTimelineEventType
    opinion: bool = False
    direction: OpinionDirection | None = None
    thesis_change: ThesisChangeType | None = None
    raw_event_id: UUID | None = None
    opinion_id: UUID | None = None
    thesis_change_id: UUID | None = None


class InvestorIntelligenceView(BaseModel):
    """Investor-centric observed-evidence query projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    window_start: AwareDatetime
    window_end: AwareDatetime
    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    attention_summary: InvestorAttentionSummary
    opinion_summary: InvestorOpinionSummary
    thesis_summary: InvestorThesisSummary
    shared_summary: InvestorSharedSummary
    timeline: tuple[InvestorTimelineEvent, ...] = ()
    data_quality: InvestorIntelligenceDataQuality

    @model_validator(mode="after")
    def validate_window(self) -> InvestorIntelligenceView:
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if self.data_quality.completeness is not self.completeness:
            raise ValueError("data quality completeness must match the view")
        if any(
            left.timestamp > right.timestamp
            for left, right in zip(self.timeline, self.timeline[1:], strict=False)
        ):
            raise ValueError("timeline must be ordered by observed timestamp")
        return self


class AssetAttentionInvestorView(BaseModel):
    """One Investor's effective Attention evidence for an Asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    attention_count: int = Field(ge=1)
    first_observed_time: AwareDatetime | None = None
    latest_observed_time: AwareDatetime | None = None
    evidence_types: tuple[AttentionEvidenceType, ...] = ()


class AssetOpinionView(BaseModel):
    """One existing Opinion; no opinion is inferred by this layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    opinion_id: UUID
    published_time: AwareDatetime
    direction: OpinionDirection
    opinion_summary: tuple[str, ...] = ()


class AssetThesisView(BaseModel):
    """Existing ThesisChange semantic with separate direction fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    effective_time: AwareDatetime
    previous_direction: OpinionDirection | None = None
    current_direction: OpinionDirection
    change_type: ThesisChangeType
    opinion_id: UUID
    thesis_change_id: UUID | None = None


class AssetCrossInvestorView(BaseModel):
    """Persisted Snapshot/Alignment/Consensus read context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID | None = None
    attention_investors: int = Field(ge=0)
    opinion_investors: int = Field(ge=0)
    alignment: DirectionalAlignmentState | None = None
    consensus: ConsensusEvidenceState | None = None
    consensus_evidence_id: UUID | None = None
    evidence_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_consensus_evidence(self) -> AssetCrossInvestorView:
        if self.consensus is None and self.consensus_evidence_id is not None:
            raise ValueError("consensus evidence id requires a consensus state")
        if self.consensus is None and self.evidence_count:
            raise ValueError("evidence_count requires a consensus state")
        return self


class AssetIntelligenceView(BaseModel):
    """Asset-centric query projection over existing effective evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    window_start: AwareDatetime
    window_end: AwareDatetime
    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    investor_attention: tuple[AssetAttentionInvestorView, ...] = ()
    opinions: tuple[AssetOpinionView, ...] = ()
    thesis: tuple[AssetThesisView, ...] = ()
    cross_investor: AssetCrossInvestorView
    data_quality: CombinedAssetDataQuality

    @model_validator(mode="after")
    def validate_view(self) -> AssetIntelligenceView:
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if self.data_quality.completeness is not self.completeness:
            raise ValueError("data quality completeness must match the view")
        if any(
            left.published_time > right.published_time
            for left, right in zip(self.opinions, self.opinions[1:], strict=False)
        ):
            raise ValueError("opinions must be ordered by published_time")
        if any(
            left.effective_time > right.effective_time
            for left, right in zip(self.thesis, self.thesis[1:], strict=False)
        ):
            raise ValueError("thesis entries must be ordered by effective_time")
        return self


class SignalCandidateType(StrEnum):
    """Existing-evidence candidate dimensions; not persisted Signals."""

    NEW_ATTENTION = "NEW_ATTENTION"
    THESIS_CHANGE = "THESIS_CHANGE"
    CROSS_INVESTOR = "CROSS_INVESTOR"
    CONSENSUS_CHANGE = "CONSENSUS_CHANGE"


class SignalCandidateView(BaseModel):
    """Read-only, deterministic candidate projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_type: SignalCandidateType
    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    investor_id: UUID | None = None
    investor_name: str | None = None
    observed_time: AwareDatetime | None = None
    direction: OpinionDirection | None = None
    source_ids: tuple[UUID, ...] = ()


class IntelligenceSearchEntity(BaseModel):
    """One matching Investor or listing-level Asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: str = Field(pattern=r"^(investor|asset)$")
    entity_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str | None = Field(default=None, max_length=32)
    symbol: str | None = Field(default=None, max_length=64)


__all__ = [
    "AssetAttentionInvestorView",
    "AssetCrossInvestorView",
    "AssetIntelligenceView",
    "AssetOpinionView",
    "AssetThesisView",
    "IntelligenceSearchEntity",
    "InvestorAttentionAssetView",
    "InvestorAttentionSummary",
    "InvestorIntelligenceView",
    "InvestorOpinionAssetView",
    "InvestorOpinionSummary",
    "InvestorSharedSummary",
    "InvestorThesisChangeView",
    "InvestorThesisSummary",
    "InvestorTimelineEvent",
    "SignalCandidateType",
    "SignalCandidateView",
]
