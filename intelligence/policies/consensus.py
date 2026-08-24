from collections.abc import Sequence

from contracts import ConsensusDirection, InvestorStateContribution, OpinionDirection

MINIMUM_POSITIVE_WEIGHT_INVESTORS = 2
MINIMUM_TOP_SHARE = 0.60
MINIMUM_LEAD_SHARE = 0.15


def direction_side(direction: OpinionDirection) -> ConsensusDirection:
    if direction in {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH}:
        return ConsensusDirection.BULLISH
    if direction in {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH}:
        return ConsensusDirection.BEARISH
    return ConsensusDirection.NEUTRAL


def calculate_consensus(
    contributions: Sequence[InvestorStateContribution],
) -> tuple[ConsensusDirection, float]:
    active = [contribution for contribution in contributions if contribution.active]
    positive_weight_count = sum(contribution.weight > 0 for contribution in active)
    if positive_weight_count < MINIMUM_POSITIVE_WEIGHT_INVESTORS:
        return ConsensusDirection.INSUFFICIENT_DATA, 0.0

    weights = {
        ConsensusDirection.BULLISH: 0.0,
        ConsensusDirection.NEUTRAL: 0.0,
        ConsensusDirection.BEARISH: 0.0,
    }
    for contribution in active:
        weights[direction_side(contribution.direction)] += contribution.weight

    total_weight = sum(weights.values())
    if total_weight <= 0:
        return ConsensusDirection.INSUFFICIENT_DATA, 0.0

    ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0].value))
    top_direction, top_weight = ranked[0]
    second_weight = ranked[1][1]
    top_share = top_weight / total_weight
    lead_share = (top_weight - second_weight) / total_weight
    strength = round(max(0.0, lead_share) * 100, 4)

    if top_share < MINIMUM_TOP_SHARE or lead_share < MINIMUM_LEAD_SHARE:
        return ConsensusDirection.MIXED, strength
    return top_direction, strength
