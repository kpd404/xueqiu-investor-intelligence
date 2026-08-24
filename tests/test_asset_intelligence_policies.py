from datetime import UTC, datetime
from uuid import uuid4

from contracts import (
    AttentionLevel,
    ConsensusDirection,
    InvestorAssetStateSnapshot,
    InvestorStateAggregationInput,
    InvestorStateContribution,
    OpinionDirection,
    PositionStatus,
)
from intelligence.policies import (
    aggregate_asset_intelligence,
    calculate_consensus,
    investor_weight,
)


def contribution(
    *,
    direction: OpinionDirection,
    weight: float,
    active: bool = True,
) -> InvestorStateContribution:
    return InvestorStateContribution(
        state_id=uuid4(),
        investor_id=uuid4(),
        asset_id=uuid4(),
        quality_score=weight * 100,
        weight=weight,
        active=active,
        attention_level=AttentionLevel.DISCOVERED,
        direction=direction,
        conviction=72,
        mention_count=1,
        last_opinion_time=datetime(2026, 8, 24, tzinfo=UTC),
        source_event_ids=(uuid4(),),
    )


def test_missing_quality_uses_deterministic_default_weight() -> None:
    assert investor_weight(None) == (50.0, 0.5)
    assert investor_weight(120) == (100.0, 1.0)
    assert investor_weight(-10) == (0.0, 0.0)


def test_one_positive_weight_investor_cannot_create_consensus() -> None:
    result = calculate_consensus(
        [
            contribution(direction=OpinionDirection.BULLISH, weight=1.0),
            contribution(direction=OpinionDirection.BULLISH, weight=0.0),
        ]
    )

    assert result == (ConsensusDirection.INSUFFICIENT_DATA, 0.0)


def test_strong_directions_are_grouped_with_their_side() -> None:
    direction, strength = calculate_consensus(
        [
            contribution(direction=OpinionDirection.STRONG_BULLISH, weight=0.8),
            contribution(direction=OpinionDirection.BULLISH, weight=0.6),
            contribution(direction=OpinionDirection.NEUTRAL, weight=0.2),
        ]
    )

    assert direction == ConsensusDirection.BULLISH
    assert strength == 75.0


def test_abandoned_state_counts_as_historical_breadth_but_is_not_active() -> None:
    asset_id = uuid4()
    event_id = uuid4()
    state = InvestorAssetStateSnapshot(
        investor_id=uuid4(),
        asset_id=asset_id,
        attention_level=AttentionLevel.ABANDONED,
        direction=OpinionDirection.BEARISH,
        conviction=80,
        mention_count=2,
        position_status=PositionStatus.NO_POSITION,
        last_opinion_time=datetime(2026, 8, 24, tzinfo=UTC),
        last_change_time=datetime(2026, 8, 24, tzinfo=UTC),
    )

    snapshot = aggregate_asset_intelligence(
        asset_id,
        datetime(2026, 8, 25, tzinfo=UTC),
        [
            InvestorStateAggregationInput(
                state_id=uuid4(),
                state=state,
                quality_score=100,
                source_event_ids=(event_id,),
            )
        ],
    )

    assert snapshot.observed_investor_count == 1
    assert snapshot.active_investor_count == 0
    assert snapshot.bearish_count == 0
    assert snapshot.consensus_direction == ConsensusDirection.INSUFFICIENT_DATA
    assert snapshot.source_event_ids == (event_id,)
