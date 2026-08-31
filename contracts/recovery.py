from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts.analysis import EventAnalysisStatus
from contracts.opinion import UnresolvedAsset

ASSET_RECOVERY_POLICY_VERSION = "asset-resolution-recovery-v1"


class AssetRecoveryStatus(StrEnum):
    RECOVERED = "RECOVERED"
    ALREADY_RECOVERED = "ALREADY_RECOVERED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    NO_UNRESOLVED = "NO_UNRESOLVED"


class AssetRecoveryResult(BaseModel):
    """Result of deterministic re-resolution for one persisted EventAnalysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: UUID
    event_id: UUID
    status: AssetRecoveryStatus
    opinion_ids: tuple[UUID, ...] = ()
    created_count: int = Field(default=0, ge=0)
    reused_count: int = Field(default=0, ge=0)
    resolved_asset_ids: tuple[UUID, ...] = ()
    unresolved_assets: tuple[UnresolvedAsset, ...] = ()
    calculated_at: AwareDatetime
    analysis_status_before: EventAnalysisStatus
    analysis_status_after: EventAnalysisStatus
