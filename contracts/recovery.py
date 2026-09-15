from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts.analysis import EventAnalysisStatus
from contracts.opinion import UnresolvedAsset
from contracts.resolution_materialization import CurrentAnalysisResolution

ASSET_RECOVERY_POLICY_VERSION = "asset-resolution-recovery-v1"


class AssetRecoveryStatus(StrEnum):
    RECOVERED = "RECOVERED"
    ALREADY_RECOVERED = "ALREADY_RECOVERED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    NO_UNRESOLVED = "NO_UNRESOLVED"


class AssetRecoveryResult(BaseModel):
    """Compatibility result for immutable resolution projection and Opinion materialization.

    The result reports the persisted Analysis status before and after the operation;
    both values are intentionally identical because Asset recovery never rewrites
    EventAnalysis. The query-time ``projection`` carries current resolution state.
    """

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
    projection: CurrentAnalysisResolution
    dry_run: bool = False
