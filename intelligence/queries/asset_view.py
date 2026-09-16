"""Map the existing Combined Asset View to the Query Layer contract."""

from __future__ import annotations

from contracts import (
    CombinedAssetIntelligenceView,
    CombinedAssetTimelineEventType,
)
from intelligence.schemas.intelligence import (
    AssetAttentionInvestorView,
    AssetCrossInvestorView,
    AssetIntelligenceView,
    AssetOpinionView,
    AssetThesisView,
)


def _thesis_entries(view: CombinedAssetIntelligenceView):
    for investor_view in view.investor_views:
        timeline = investor_view.thesis_timeline
        if timeline is None:
            continue
        entries_by_id = {entry.opinion_id: entry for entry in timeline.entries}
        for entry in timeline.entries:
            yield investor_view.investor_id, investor_view.investor_name, entry, entries_by_id


def _build_opinions(view: CombinedAssetIntelligenceView) -> tuple[AssetOpinionView, ...]:
    thesis_by_opinion = {}
    for investor_id, investor_name, entry, _ in _thesis_entries(view):
        thesis_by_opinion[entry.opinion_id] = (investor_id, investor_name, entry)

    opinions: list[AssetOpinionView] = []
    seen: set[object] = set()
    for event in view.event_timeline:
        if event.event_type is not CombinedAssetTimelineEventType.OPINION_OBSERVED:
            continue
        if event.opinion_id is None or event.opinion_id in seen or event.direction is None:
            continue
        seen.add(event.opinion_id)
        entry = thesis_by_opinion.get(event.opinion_id)
        opinions.append(
            AssetOpinionView(
                investor_id=event.investor_id,
                investor_name=event.investor_name,
                opinion_id=event.opinion_id,
                published_time=event.published_time,
                direction=event.direction,
                opinion_summary=entry[2].thesis if entry is not None else (),
            )
        )

    # A valid Opinion timeline is normally also represented in the Combined
    # event timeline.  This fallback keeps the projection lossless for a
    # compatible read-model fixture without inventing any event.
    for investor_id, investor_name, entry, _ in _thesis_entries(view):
        if entry.opinion_id in seen:
            continue
        seen.add(entry.opinion_id)
        opinions.append(
            AssetOpinionView(
                investor_id=investor_id,
                investor_name=investor_name,
                opinion_id=entry.opinion_id,
                published_time=entry.published_time,
                direction=entry.direction,
                opinion_summary=entry.thesis,
            )
        )
    return tuple(sorted(opinions, key=lambda item: (item.published_time, item.opinion_id.int)))


def _build_thesis(view: CombinedAssetIntelligenceView) -> tuple[AssetThesisView, ...]:
    changes: list[AssetThesisView] = []
    seen: set[object] = set()
    for investor_id, investor_name, entry, entries_by_id in _thesis_entries(view):
        if entry.thesis_change_type is None:
            continue
        identity = entry.thesis_change_id or entry.opinion_id
        if identity in seen:
            continue
        seen.add(identity)
        predecessor = entries_by_id.get(entry.predecessor_opinion_id)
        changes.append(
            AssetThesisView(
                investor_id=investor_id,
                investor_name=investor_name,
                effective_time=entry.thesis_change_time or entry.published_time,
                previous_direction=predecessor.direction if predecessor else None,
                current_direction=entry.direction,
                change_type=entry.thesis_change_type,
                opinion_id=entry.opinion_id,
                thesis_change_id=entry.thesis_change_id,
            )
        )
    return tuple(
        sorted(
            changes,
            key=lambda item: (
                item.effective_time,
                item.investor_name,
                item.opinion_id.int,
            ),
        )
    )


def build_asset_intelligence_view(view: CombinedAssetIntelligenceView) -> AssetIntelligenceView:
    """Return a lossless, read-only Asset projection from existing evidence."""

    attention = tuple(
        sorted(
            (
                AssetAttentionInvestorView(
                    investor_id=item.investor_id,
                    investor_name=item.investor_name,
                    attention_count=item.attention_occurrence_count,
                    first_observed_time=item.first_attention_time,
                    latest_observed_time=item.latest_attention_time,
                    evidence_types=item.attention_evidence_types,
                )
                for item in view.investor_views
                if item.attention_occurrence_count > 0
            ),
            key=lambda item: (item.investor_name, item.investor_id.int),
        )
    )
    snapshot = view.snapshot
    opinions = _build_opinions(view)
    cross = AssetCrossInvestorView(
        snapshot_id=snapshot.id if snapshot is not None else None,
        attention_investors=(
            snapshot.attention_investor_count
            if snapshot is not None
            else view.attention_summary.attention_investor_count
        ),
        opinion_investors=(
            snapshot.opinion_investor_count
            if snapshot is not None
            else len({item.investor_id for item in opinions})
        ),
        alignment=(view.alignment.directional_alignment_state if view.alignment else None),
        consensus=(view.consensus.consensus_state if view.consensus else None),
        consensus_evidence_id=view.consensus.id if view.consensus else None,
        evidence_count=(view.consensus.opinion_investor_count if view.consensus else 0),
    )
    return AssetIntelligenceView(
        asset_id=view.asset_id,
        asset_name=view.asset_name,
        market=view.market,
        symbol=view.symbol,
        window_start=view.window_start,
        window_end=view.window_end,
        completeness=view.completeness,
        investor_attention=attention,
        opinions=opinions,
        thesis=_build_thesis(view),
        cross_investor=cross,
        data_quality=view.data_quality,
    )


__all__ = ["build_asset_intelligence_view"]
