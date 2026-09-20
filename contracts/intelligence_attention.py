"""Contracts for deterministic human-review attention classification."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class IntelligenceAttentionClass(StrEnum):
    """Presentation/review class for one Asset's observed Intelligence."""

    IMMEDIATE_REVIEW = "IMMEDIATE_REVIEW"
    ACTIVE_REVIEW = "ACTIVE_REVIEW"
    BACKGROUND_MONITORING = "BACKGROUND_MONITORING"
    LIMITED_CONTEXT = "LIMITED_CONTEXT"


class IntelligenceAttentionReason(StrEnum):
    """Deterministic explanation for an attention class."""

    CONSENSUS_STATE_CHANGE = "CONSENSUS_STATE_CHANGE"
    CONSENSUS_FRAGMENTATION = "CONSENSUS_FRAGMENTATION"
    MULTI_INVESTOR_EXPANSION = "MULTI_INVESTOR_EXPANSION"
    THESIS_TRANSITION = "THESIS_TRANSITION"
    HIGH_PRIORITY_EVIDENCE = "HIGH_PRIORITY_EVIDENCE"
    ACTIVE_INTELLIGENCE = "ACTIVE_INTELLIGENCE"
    HISTORICAL_INTELLIGENCE = "HISTORICAL_INTELLIGENCE"
    LIMITED_CONTEXT = "LIMITED_CONTEXT"


class IntelligenceAttentionAssetIdentity(BaseModel):
    """Listing identity carried by the query-time classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class IntelligenceAttentionEvidenceRef(BaseModel):
    """One persisted artifact reference supporting the classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: str = Field(min_length=1, max_length=128)
    source_id: UUID


class IntelligenceAttentionEvidenceSummary(BaseModel):
    """Counts and availability flags, without a severity calculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    active_event_count: int = Field(ge=0)
    active_priority_count: int = Field(ge=0)
    active_feed_count: int = Field(ge=0)
    historical_artifact_count: int = Field(ge=0)
    discovery_candidate_present: bool
    evidence_ref_count: int = Field(ge=0)


class IntelligenceAttentionClassificationView(BaseModel):
    """One deterministic, read-only Asset attention classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset: IntelligenceAttentionAssetIdentity
    attention_class: IntelligenceAttentionClass
    reasons: tuple[IntelligenceAttentionReason, ...] = ()
    evidence_summary: IntelligenceAttentionEvidenceSummary
    evidence_refs: tuple[IntelligenceAttentionEvidenceRef, ...] = ()
    current_patterns: tuple[str, ...] = ()
    current_alignment: str | None = None
    current_consensus: str | None = None
    latest_observed_at: AwareDatetime | None = None
    limitations: tuple[str, ...] = ()


__all__ = [
    "IntelligenceAttentionAssetIdentity",
    "IntelligenceAttentionClass",
    "IntelligenceAttentionClassificationView",
    "IntelligenceAttentionEvidenceRef",
    "IntelligenceAttentionEvidenceSummary",
    "IntelligenceAttentionReason",
]
