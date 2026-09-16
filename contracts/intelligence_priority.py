"""Contracts for deterministic observation-priority projections."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class IntelligencePriorityLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IntelligencePriorityReason(StrEnum):
    MULTI_INVESTOR_ATTENTION = "MULTI_INVESTOR_ATTENTION"
    THESIS_ACCELERATION = "THESIS_ACCELERATION"
    CROSS_INVESTOR_DISCOVERY = "CROSS_INVESTOR_DISCOVERY"
    CONSENSUS_STATE_CHANGE = "CONSENSUS_STATE_CHANGE"


class IntelligenceEventPriorityCreate(BaseModel):
    """One observation-priority classification for an IntelligenceEvent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    priority_level: IntelligencePriorityLevel
    reason: IntelligencePriorityReason
    evidence_count: int = Field(ge=1)
    created_at: AwareDatetime


class IntelligenceEventPriorityView(IntelligenceEventPriorityCreate):
    id: UUID


class IntelligencePriorityGenerationResult(BaseModel):
    """Result of dry-run or idempotent priority materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[IntelligenceEventPriorityCreate, ...] = ()
    priorities: tuple[IntelligenceEventPriorityView, ...] = ()
    created_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    dry_run: bool


__all__ = [
    "IntelligenceEventPriorityCreate",
    "IntelligenceEventPriorityView",
    "IntelligencePriorityGenerationResult",
    "IntelligencePriorityLevel",
    "IntelligencePriorityReason",
]
