"""Pure V0 direction-to-position-change consistency policy."""

from contracts import ConsistencyType, OpinionDirection, PortfolioActionType


def classify_consistency(
    opinion_direction: OpinionDirection | None,
    action_type: PortfolioActionType | None,
) -> tuple[ConsistencyType, float]:
    """Classify alignment without inferring intent, skill, or performance."""

    if opinion_direction is None or opinion_direction is OpinionDirection.NEUTRAL:
        return ConsistencyType.NO_DIRECTION, 0.0
    if action_type not in {
        PortfolioActionType.POSITION_INCREASED,
        PortfolioActionType.POSITION_DECREASED,
    }:
        return ConsistencyType.INSUFFICIENT_EVIDENCE, 0.0

    is_bullish = opinion_direction in {
        OpinionDirection.BULLISH,
        OpinionDirection.STRONG_BULLISH,
    }
    is_increase = action_type is PortfolioActionType.POSITION_INCREASED
    if is_bullish == is_increase:
        return ConsistencyType.POSITIVE_ALIGNMENT, 1.0
    return ConsistencyType.NEGATIVE_ALIGNMENT, 1.0
