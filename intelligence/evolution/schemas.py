"""Contracts for deterministic Asset Intelligence evolution timelines."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EvolutionStepType(StrEnum):
    INITIAL_DISCOVERY = "INITIAL_DISCOVERY"
    INVESTOR_ATTENTION_ADDED = "INVESTOR_ATTENTION_ADDED"
    THESIS_ACTIVITY = "THESIS_ACTIVITY"
    MULTI_INVESTOR_EXPANSION = "MULTI_INVESTOR_EXPANSION"
    CROSS_INVESTOR_STATE = "CROSS_INVESTOR_STATE"
    CONSENSUS_STATE = "CONSENSUS_STATE"
    PATTERN_OBSERVED = "PATTERN_OBSERVED"


class EvolutionSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: str = Field(min_length=1, max_length=128)
    source_id: UUID


class EvolutionAssetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class EvolutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: UUID
    observed_at: AwareDatetime
    step_type: EvolutionStepType
    asset_id: UUID
    investor_id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    facts: list[str] = Field(default_factory=list)
    source_refs: list[EvolutionSourceRef] = Field(default_factory=list)


class EvolutionCurrentState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    patterns: list[str] = Field(default_factory=list)
    alignment_state: str | None = None
    consensus_state: str | None = None


class EvolutionTimelineRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    first_observed_at: AwareDatetime | None = None
    latest_observed_at: AwareDatetime | None = None


class IntelligenceEvolutionView(BaseModel):
    """Ordered, fact-time evolution projection for one Asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset: EvolutionAssetIdentity
    timeline: list[EvolutionStep] = Field(default_factory=list)
    current_state: EvolutionCurrentState
    timeline_range: EvolutionTimelineRange
    limitations: list[str] = Field(default_factory=list)


__all__ = [
    "EvolutionAssetIdentity",
    "EvolutionCurrentState",
    "EvolutionSourceRef",
    "EvolutionStep",
    "EvolutionStepType",
    "EvolutionTimelineRange",
    "IntelligenceEvolutionView",
]
