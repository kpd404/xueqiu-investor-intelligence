from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from contracts import (
    AssetIntelligenceSnapshot,
    ConsensusDirection,
    InvestorStateAggregationInput,
    InvestorStateContribution,
)
from intelligence.policies.consensus import calculate_consensus, direction_side
from intelligence.policies.inclusion import is_active_state, is_valid_aggregation_state
from intelligence.policies.investor_weight import investor_weight


def aggregate_asset_intelligence(
    asset_id: UUID,
    as_of: datetime,
    states: Sequence[InvestorStateAggregationInput],
) -> AssetIntelligenceSnapshot:
    """Build a deterministic, non-persisted asset intelligence snapshot."""

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    normalized_as_of = as_of.astimezone(UTC)

    contributions: list[InvestorStateContribution] = []
    for item in sorted(states, key=lambda item: (item.state.investor_id.int, item.state_id.int)):
        if item.state.asset_id != asset_id:
            raise ValueError("all states must belong to the requested asset")
        source_event_ids = tuple(sorted(set(item.source_event_ids), key=lambda value: value.int))
        if not is_valid_aggregation_state(item.state, source_event_ids, normalized_as_of):
            continue

        effective_quality, weight = investor_weight(item.quality_score)
        contributions.append(
            InvestorStateContribution(
                state_id=item.state_id,
                investor_id=item.state.investor_id,
                asset_id=item.state.asset_id,
                quality_score=effective_quality,
                weight=weight,
                active=is_active_state(item.state),
                attention_level=item.state.attention_level,
                direction=item.state.direction,
                conviction=item.state.conviction,
                mention_count=item.state.mention_count,
                last_opinion_time=item.state.last_opinion_time,
                source_event_ids=source_event_ids,
            )
        )

    active = [contribution for contribution in contributions if contribution.active]
    counts = {
        ConsensusDirection.BULLISH: 0,
        ConsensusDirection.NEUTRAL: 0,
        ConsensusDirection.BEARISH: 0,
    }
    weights = {
        ConsensusDirection.BULLISH: 0.0,
        ConsensusDirection.NEUTRAL: 0.0,
        ConsensusDirection.BEARISH: 0.0,
    }
    for contribution in active:
        side = direction_side(contribution.direction)
        counts[side] += 1
        weights[side] += contribution.weight

    consensus_direction, consensus_strength = calculate_consensus(contributions)
    evidence = tuple(
        sorted(
            {
                event_id
                for contribution in contributions
                for event_id in contribution.source_event_ids
            },
            key=lambda value: value.int,
        )
    )
    return AssetIntelligenceSnapshot(
        asset_id=asset_id,
        as_of=normalized_as_of,
        observed_investor_count=len(contributions),
        active_investor_count=len(active),
        bullish_count=counts[ConsensusDirection.BULLISH],
        neutral_count=counts[ConsensusDirection.NEUTRAL],
        bearish_count=counts[ConsensusDirection.BEARISH],
        weighted_bullish=round(weights[ConsensusDirection.BULLISH], 6),
        weighted_neutral=round(weights[ConsensusDirection.NEUTRAL], 6),
        weighted_bearish=round(weights[ConsensusDirection.BEARISH], 6),
        consensus_direction=consensus_direction,
        consensus_strength=consensus_strength,
        investor_states=tuple(contributions),
        source_event_ids=evidence,
    )
