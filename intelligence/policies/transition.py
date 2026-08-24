from contracts import (
    InvestorAssetStateSnapshot,
    OpinionDirection,
    StateTransitionType,
)

DIRECTION_RANK = {
    OpinionDirection.STRONG_BEARISH: -2,
    OpinionDirection.BEARISH: -1,
    OpinionDirection.NEUTRAL: 0,
    OpinionDirection.BULLISH: 1,
    OpinionDirection.STRONG_BULLISH: 2,
}


def classify_transition(
    before: InvestorAssetStateSnapshot | None,
    after: InvestorAssetStateSnapshot,
) -> StateTransitionType:
    if before is None or (before.mention_count == 0 and after.mention_count > 0):
        return StateTransitionType.NEW_ATTENTION

    before_rank = DIRECTION_RANK[before.direction]
    after_rank = DIRECTION_RANK[after.direction]
    if before_rank != 0 and after_rank != 0 and (before_rank < 0) != (after_rank < 0):
        return StateTransitionType.OPINION_REVERSAL
    if after_rank > before_rank:
        return StateTransitionType.OPINION_UPGRADE
    if after_rank < before_rank:
        return StateTransitionType.OPINION_DOWNGRADE
    return StateTransitionType.NO_MATERIAL_CHANGE
