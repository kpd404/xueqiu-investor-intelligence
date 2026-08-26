from datetime import datetime
from uuid import UUID

from contracts import AttentionLevel, InvestorAssetStateSnapshot

ACTIVE_ATTENTION_LEVELS = {
    AttentionLevel.DISCOVERED,
    AttentionLevel.TRACKING,
    AttentionLevel.FOCUS,
    AttentionLevel.CORE_FOCUS,
}


def is_valid_aggregation_state(
    state: InvestorAssetStateSnapshot,
    source_event_ids: tuple[UUID, ...],
    as_of: datetime,
) -> bool:
    return (
        state.attention_level != AttentionLevel.UNKNOWN
        and state.mention_count > 0
        and state.last_activity_time is not None
        and state.last_activity_time <= as_of
        and bool(source_event_ids)
    )


def is_active_state(state: InvestorAssetStateSnapshot) -> bool:
    return state.attention_level in ACTIVE_ATTENTION_LEVELS
