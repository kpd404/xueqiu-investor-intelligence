"""Contracts for deterministic fact-only Intelligence Patterns."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class IntelligencePatternType(StrEnum):
    NEW_DISCOVERY = "NEW_DISCOVERY"
    ACCELERATING_ACTIVITY = "ACCELERATING_ACTIVITY"
    MULTI_INVESTOR_EXPANSION = "MULTI_INVESTOR_EXPANSION"
    RETURNING_ATTENTION = "RETURNING_ATTENTION"
    THESIS_TRANSITION = "THESIS_TRANSITION"
    CONSENSUS_FORMATION = "CONSENSUS_FORMATION"
    CONSENSUS_FRAGMENTATION = "CONSENSUS_FRAGMENTATION"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class IntelligencePatternDataQualityType(StrEnum):
    HISTORICAL_COMPARISON_UNAVAILABLE = "HISTORICAL_COMPARISON_UNAVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class PatternDataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: IntelligencePatternDataQualityType
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class PatternAssetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class IntelligencePatternEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: IntelligencePatternType
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class PatternTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    first_observed_at: AwareDatetime | None = None
    latest_observed_at: AwareDatetime | None = None


class IntelligencePatternView(BaseModel):
    """One Asset's deterministic observed-activity pattern classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset: PatternAssetIdentity
    patterns: list[IntelligencePatternEvidence] = Field(default_factory=list)
    data_quality: list[PatternDataQuality] = Field(default_factory=list)
    timeline: PatternTimeline
    limitations: list[str] = Field(default_factory=list)


__all__ = [
    "IntelligencePatternDataQualityType",
    "IntelligencePatternEvidence",
    "IntelligencePatternType",
    "IntelligencePatternView",
    "PatternDataQuality",
    "PatternAssetIdentity",
    "PatternTimeline",
]
