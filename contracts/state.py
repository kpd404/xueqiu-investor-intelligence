from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts.enums import AttentionLevel, OpinionDirection, PositionStatus


class OpinionTimelineEntry(BaseModel):
    """One traceable interpretation paired with its source event time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opinion_id: UUID
    event_id: UUID
    investor_id: UUID
    asset_id: UUID
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    published_time: AwareDatetime
    generated_time: AwareDatetime


class InvestorAssetStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID
    attention_level: AttentionLevel
    direction: OpinionDirection
    conviction: float = Field(ge=0, le=100)
    mention_count: int = Field(ge=0)
    position_status: PositionStatus
    last_opinion_time: AwareDatetime | None
    last_change_time: AwareDatetime | None


class StateTransitionType(StrEnum):
    NEW_ATTENTION = "NEW_ATTENTION"
    OPINION_UPGRADE = "OPINION_UPGRADE"
    OPINION_DOWNGRADE = "OPINION_DOWNGRADE"
    OPINION_REVERSAL = "OPINION_REVERSAL"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"


class StateReduction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    changed: bool
    before: InvestorAssetStateSnapshot | None
    after: InvestorAssetStateSnapshot
    transition: StateTransitionType
    applied_opinion_ids: tuple[UUID, ...]
    source_event_ids: tuple[UUID, ...]


class StateUpdateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state_id: UUID
    changed: bool
    before: InvestorAssetStateSnapshot | None
    after: InvestorAssetStateSnapshot
    transition: StateTransitionType
    applied_opinion_ids: tuple[UUID, ...]
    source_event_ids: tuple[UUID, ...]
