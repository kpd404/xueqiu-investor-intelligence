"""Pure Signal-ready projections from existing Asset evidence."""

from __future__ import annotations

from contracts import CombinedAssetIntelligenceView, CombinedAssetTimelineEventType
from intelligence.schemas.intelligence import SignalCandidateType, SignalCandidateView


def build_signal_candidate_views(
    view: CombinedAssetIntelligenceView,
) -> tuple[SignalCandidateView, ...]:
    """Project candidate facts without persisting or scoring a Signal."""

    candidates: list[SignalCandidateView] = []
    attention_events = [
        event
        for event in view.event_timeline
        if event.event_type is CombinedAssetTimelineEventType.ATTENTION_FIRST_OBSERVED
    ]
    if attention_events:
        attention_values = [
            (
                event.investor_id,
                event.investor_name,
                event.published_time,
                event.attention_occurrence_id,
            )
            for event in attention_events
        ]
    elif view.observed_attention_sequence is not None:
        observations = (
            view.observed_attention_sequence.first_observed,
            *view.observed_attention_sequence.later_observations,
        )
        attention_values = [
            (
                observation.investor_id,
                observation.investor_name,
                observation.published_time,
                observation.attention_occurrence_id,
            )
            for observation in observations
        ]
    else:
        attention_values = []

    for investor_id, investor_name, observed_time, occurrence_id in attention_values:
        candidates.append(
            SignalCandidateView(
                candidate_type=SignalCandidateType.NEW_ATTENTION,
                asset_id=view.asset_id,
                asset_name=view.asset_name,
                market=view.market,
                symbol=view.symbol,
                investor_id=investor_id,
                investor_name=investor_name,
                observed_time=observed_time,
                source_ids=(occurrence_id,) if occurrence_id is not None else (),
            )
        )

    for event in view.event_timeline:
        if event.event_type is not CombinedAssetTimelineEventType.THESIS_CHANGE_OBSERVED:
            continue
        candidates.append(
            SignalCandidateView(
                candidate_type=SignalCandidateType.THESIS_CHANGE,
                asset_id=view.asset_id,
                asset_name=view.asset_name,
                market=view.market,
                symbol=view.symbol,
                investor_id=event.investor_id,
                investor_name=event.investor_name,
                observed_time=event.published_time,
                direction=event.direction,
                source_ids=(event.thesis_change_id,) if event.thesis_change_id is not None else (),
            )
        )

    if view.snapshot is not None and view.snapshot.attention_investor_count >= 2:
        candidates.append(
            SignalCandidateView(
                candidate_type=SignalCandidateType.CROSS_INVESTOR,
                asset_id=view.asset_id,
                asset_name=view.asset_name,
                market=view.market,
                symbol=view.symbol,
                source_ids=(view.snapshot.id,),
            )
        )

    if view.consensus is not None:
        candidates.append(
            SignalCandidateView(
                candidate_type=SignalCandidateType.CONSENSUS_CHANGE,
                asset_id=view.asset_id,
                asset_name=view.asset_name,
                market=view.market,
                symbol=view.symbol,
                source_ids=(view.consensus.id,),
            )
        )

    return tuple(candidates)


__all__ = ["build_signal_candidate_views"]
