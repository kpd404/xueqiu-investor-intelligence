from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from contracts.attention import AttentionOccurrenceRebuildResult
from contracts.recovery import AssetRecoveryResult
from contracts.state import StateUpdateResult


class BehaviorReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recovery: AssetRecoveryResult
    state_updates: tuple[StateUpdateResult, ...]
    attention: AttentionOccurrenceRebuildResult
    affected_asset_ids: tuple[UUID, ...]
    skipped_inactive_opinion_ids: tuple[UUID, ...]
    calculated_at: AwareDatetime
