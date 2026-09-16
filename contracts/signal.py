"""Provider-neutral contracts for deterministic Signal evidence."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class SignalType(StrEnum):
    NEW_ATTENTION = "NEW_ATTENTION"
    THESIS_CHANGE = "THESIS_CHANGE"
    CROSS_INVESTOR_ALIGNMENT = "CROSS_INVESTOR_ALIGNMENT"
    CONSENSUS_CHANGE = "CONSENSUS_CHANGE"


class SignalState(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    SUPERSEDED = "SUPERSEDED"


class SignalSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SignalCreate(BaseModel):
    """One deterministic Signal derived from an existing source artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    investor_id: UUID | None = None
    signal_type: SignalType
    state: SignalState = SignalState.ACTIVE
    severity: SignalSeverity = SignalSeverity.LOW
    source_type: str = Field(min_length=1, max_length=128)
    source_id: UUID
    created_at: AwareDatetime
    observed_at: AwareDatetime
    metadata: dict[str, object] = Field(default_factory=dict)


class SignalView(SignalCreate):
    id: UUID


class SignalGenerationResult(BaseModel):
    """Bounded result for dry-run or persisted deterministic generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[SignalCreate, ...] = ()
    signals: tuple[SignalView, ...] = ()
    created_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    dry_run: bool


__all__ = [
    "SignalCreate",
    "SignalGenerationResult",
    "SignalSeverity",
    "SignalState",
    "SignalType",
    "SignalView",
]
