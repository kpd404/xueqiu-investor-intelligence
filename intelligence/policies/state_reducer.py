from collections.abc import Sequence
from uuid import UUID

from contracts import (
    InvestorAssetStateSnapshot,
    OpinionTimelineEntry,
    PositionStatus,
    StateReduction,
)
from intelligence.policies.attention import classify_attention
from intelligence.policies.transition import classify_transition


def reduce_investor_asset_state(
    opinions: Sequence[OpinionTimelineEntry],
    before: InvestorAssetStateSnapshot | None = None,
) -> StateReduction:
    """Rebuild one Investor × Asset state from its complete effective opinion history."""

    if not opinions:
        raise ValueError("at least one opinion is required to build state")

    effective = select_effective_opinions(opinions)
    investor_id = effective[0].investor_id
    asset_id = effective[0].asset_id
    if any(
        opinion.investor_id != investor_id or opinion.asset_id != asset_id for opinion in effective
    ):
        raise ValueError("all opinions must belong to the same investor and asset")
    if before is not None and (before.investor_id != investor_id or before.asset_id != asset_id):
        raise ValueError("before state must belong to the same investor and asset")

    latest = effective[-1]
    mention_count = len(effective)
    conviction = round(latest.strength * latest.confidence, 4)
    attention_level = classify_attention(mention_count, conviction)
    position_status = before.position_status if before else PositionStatus.NO_POSITION

    candidate = InvestorAssetStateSnapshot(
        investor_id=investor_id,
        asset_id=asset_id,
        attention_level=attention_level,
        direction=latest.direction,
        conviction=conviction,
        mention_count=mention_count,
        position_status=position_status,
        last_activity_time=latest.published_time,
        last_material_change_time=before.last_material_change_time if before else None,
    )
    projection_changed = before is None or _projection_fingerprint(
        before
    ) != _projection_fingerprint(candidate)
    transition = classify_transition(before, candidate)
    material_change = transition.value != "NO_MATERIAL_CHANGE"
    last_material_change_time = (
        latest.published_time
        if material_change
        else before.last_material_change_time
        if before is not None
        else latest.published_time
    )
    after = candidate.model_copy(update={"last_material_change_time": last_material_change_time})

    return StateReduction(
        projection_changed=projection_changed,
        material_change=material_change,
        before=before,
        after=after,
        transition=transition,
        applied_opinion_ids=tuple(opinion.opinion_id for opinion in effective),
        source_event_ids=tuple(opinion.event_id for opinion in effective),
    )


def select_effective_opinions(
    opinions: Sequence[OpinionTimelineEntry],
) -> list[OpinionTimelineEntry]:
    """Choose the latest interpretation per source event, then order the timeline."""

    latest_by_event: dict[UUID, OpinionTimelineEntry] = {}
    for opinion in opinions:
        current = latest_by_event.get(opinion.event_id)
        if current is None or (opinion.generated_time, opinion.opinion_id.int) > (
            current.generated_time,
            current.opinion_id.int,
        ):
            latest_by_event[opinion.event_id] = opinion

    return sorted(
        latest_by_event.values(),
        key=lambda opinion: (
            opinion.published_time,
            opinion.event_id.int,
            opinion.opinion_id.int,
        ),
    )


def _projection_fingerprint(state: InvestorAssetStateSnapshot) -> tuple[object, ...]:
    return (
        state.attention_level,
        state.direction,
        state.conviction,
        state.mention_count,
        state.position_status,
        state.last_activity_time,
    )
