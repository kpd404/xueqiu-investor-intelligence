from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts.intelligence import AssetIntelligenceSnapshot
from contracts.opinion import OpinionProcessingStatus, UnresolvedAsset
from contracts.state import StateUpdateResult


class ProcessRawEventCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    model_version: str = Field(min_length=1, max_length=255)
    as_of: AwareDatetime


class CoreProcessingFailureCode(StrEnum):
    RAW_EVENT_NOT_FOUND = "RAW_EVENT_NOT_FOUND"
    STATE_UPDATE_FAILED = "STATE_UPDATE_FAILED"
    INTELLIGENCE_CALCULATION_FAILED = "INTELLIGENCE_CALCULATION_FAILED"


class CoreProcessingWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: CoreProcessingFailureCode
    message: str = Field(min_length=1)
    opinion_id: UUID | None = None
    asset_id: UUID | None = None


class CoreProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    model_version: str
    as_of: AwareDatetime
    opinion_processing_status: OpinionProcessingStatus
    opinion_ids: tuple[UUID, ...]
    state_updates: tuple[StateUpdateResult, ...]
    affected_asset_ids: tuple[UUID, ...]
    asset_intelligence_snapshots: tuple[AssetIntelligenceSnapshot, ...]
    unresolved_assets: tuple[UnresolvedAsset, ...]
    warnings: tuple[CoreProcessingWarning, ...]
