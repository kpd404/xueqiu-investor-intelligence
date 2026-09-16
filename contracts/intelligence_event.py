"""Contracts for deterministic aggregation of atomic Signals."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class IntelligenceEventType(StrEnum):
    ASSET_ACTIVITY_SPIKE = "ASSET_ACTIVITY_SPIKE"
    INVESTOR_VIEW_CHANGE = "INVESTOR_VIEW_CHANGE"
    CROSS_INVESTOR_DISCOVERY = "CROSS_INVESTOR_DISCOVERY"
    CONSENSUS_STATE_CHANGE = "CONSENSUS_STATE_CHANGE"


class IntelligenceEventState(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class IntelligenceEventCreate(BaseModel):
    """One aggregate event derived from one or more existing Signals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    event_type: IntelligenceEventType
    state: IntelligenceEventState = IntelligenceEventState.ACTIVE
    first_observed_at: AwareDatetime
    last_observed_at: AwareDatetime
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_observed_range(self) -> IntelligenceEventCreate:
        if self.first_observed_at > self.last_observed_at:
            raise ValueError("first_observed_at must not be after last_observed_at")
        return self


class IntelligenceEventView(IntelligenceEventCreate):
    id: UUID


class IntelligenceEventEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    signal_id: UUID


class IntelligenceEventEvidenceView(IntelligenceEventEvidenceCreate):
    id: UUID


class IntelligenceEventGenerationResult(BaseModel):
    """Result of dry-run or idempotent aggregate materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[IntelligenceEventCreate, ...] = ()
    events: tuple[IntelligenceEventView, ...] = ()
    created_event_count: int = Field(ge=0)
    reused_event_count: int = Field(ge=0)
    created_evidence_count: int = Field(ge=0)
    reused_evidence_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    dry_run: bool


__all__ = [
    "IntelligenceEventCreate",
    "IntelligenceEventEvidenceCreate",
    "IntelligenceEventEvidenceView",
    "IntelligenceEventGenerationResult",
    "IntelligenceEventState",
    "IntelligenceEventType",
    "IntelligenceEventView",
]
