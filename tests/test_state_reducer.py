from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from contracts import (
    AttentionLevel,
    OpinionDirection,
    OpinionTimelineEntry,
    StateTransitionType,
)
from intelligence.policies import reduce_investor_asset_state


def timeline_entry(
    *,
    investor_id: UUID,
    asset_id: UUID,
    published_time: datetime,
    direction: OpinionDirection,
    strength: float = 80,
    confidence: float = 0.9,
    event_id: UUID | None = None,
    generated_time: datetime | None = None,
) -> OpinionTimelineEntry:
    return OpinionTimelineEntry(
        opinion_id=uuid4(),
        event_id=event_id or uuid4(),
        investor_id=investor_id,
        asset_id=asset_id,
        direction=direction,
        strength=strength,
        confidence=confidence,
        published_time=published_time,
        generated_time=generated_time or published_time + timedelta(minutes=1),
    )


def test_reducer_is_independent_of_input_order() -> None:
    investor_id = uuid4()
    asset_id = uuid4()
    first = timeline_entry(
        investor_id=investor_id,
        asset_id=asset_id,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
        direction=OpinionDirection.NEUTRAL,
    )
    second = timeline_entry(
        investor_id=investor_id,
        asset_id=asset_id,
        published_time=datetime(2026, 8, 21, tzinfo=UTC),
        direction=OpinionDirection.BULLISH,
    )

    chronological = reduce_investor_asset_state([first, second])
    reversed_input = reduce_investor_asset_state([second, first])

    assert chronological == reversed_input
    assert chronological.after.direction == OpinionDirection.BULLISH
    assert chronological.after.conviction == 72
    assert chronological.after.mention_count == 2
    assert chronological.after.attention_level == AttentionLevel.TRACKING


def test_reducer_counts_one_effective_opinion_per_source_event() -> None:
    investor_id = uuid4()
    asset_id = uuid4()
    event_id = uuid4()
    published_time = datetime(2026, 8, 20, tzinfo=UTC)
    old_model = timeline_entry(
        investor_id=investor_id,
        asset_id=asset_id,
        event_id=event_id,
        published_time=published_time,
        generated_time=published_time + timedelta(minutes=1),
        direction=OpinionDirection.NEUTRAL,
    )
    new_model = timeline_entry(
        investor_id=investor_id,
        asset_id=asset_id,
        event_id=event_id,
        published_time=published_time,
        generated_time=published_time + timedelta(minutes=2),
        direction=OpinionDirection.BULLISH,
    )

    reduction = reduce_investor_asset_state([old_model, new_model])

    assert reduction.after.mention_count == 1
    assert reduction.after.direction == OpinionDirection.BULLISH
    assert reduction.applied_opinion_ids == (new_model.opinion_id,)
    assert reduction.source_event_ids == (event_id,)


def test_focus_requires_repeated_history_and_high_conviction() -> None:
    investor_id = uuid4()
    asset_id = uuid4()
    base_time = datetime(2026, 8, 20, tzinfo=UTC)
    history = [
        timeline_entry(
            investor_id=investor_id,
            asset_id=asset_id,
            published_time=base_time + timedelta(days=index),
            direction=OpinionDirection.BULLISH,
            strength=90,
            confidence=0.9,
        )
        for index in range(4)
    ]

    reduction = reduce_investor_asset_state(history)

    assert reduction.after.attention_level == AttentionLevel.FOCUS
    assert reduction.transition == StateTransitionType.NEW_ATTENTION


def test_bullish_to_neutral_is_opinion_downgrade() -> None:
    investor_id = uuid4()
    asset_id = uuid4()
    base_time = datetime(2026, 8, 20, tzinfo=UTC)
    bullish = timeline_entry(
        investor_id=investor_id,
        asset_id=asset_id,
        published_time=base_time,
        direction=OpinionDirection.BULLISH,
    )
    before = reduce_investor_asset_state([bullish]).after
    neutral = timeline_entry(
        investor_id=investor_id,
        asset_id=asset_id,
        published_time=base_time + timedelta(days=1),
        direction=OpinionDirection.NEUTRAL,
    )

    reduction = reduce_investor_asset_state([bullish, neutral], before)

    assert reduction.transition == StateTransitionType.OPINION_DOWNGRADE
