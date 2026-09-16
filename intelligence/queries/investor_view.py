"""Map the existing Investor View to the Query Layer contract."""

from __future__ import annotations

from contracts import (
    InvestorIntelligenceView as ExistingInvestorIntelligenceView,
)
from contracts import (
    OpinionDirection,
)
from intelligence.schemas.intelligence import (
    InvestorAttentionAssetView,
    InvestorAttentionSummary,
    InvestorIntelligenceView,
    InvestorOpinionAssetView,
    InvestorOpinionSummary,
    InvestorSharedSummary,
    InvestorThesisChangeView,
    InvestorThesisSummary,
    InvestorTimelineEvent,
)

_BULLISH = {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH}
_BEARISH = {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH}


def build_investor_intelligence_view(
    view: ExistingInvestorIntelligenceView,
    *,
    recent_limit: int = 5,
) -> InvestorIntelligenceView:
    """Return a deterministic Investor projection without adding semantics."""

    if recent_limit < 1:
        raise ValueError("recent_limit must be at least 1")

    attention_assets = tuple(
        InvestorAttentionAssetView(
            asset_id=item.asset_id,
            asset_name=item.asset_name,
            market=item.market,
            symbol=item.symbol,
            attention_count=item.attention_occurrence_count,
            first_observed_time=item.first_attention_time,
            latest_observed_time=item.latest_attention_time,
            evidence_types=item.attention_evidence_types,
        )
        for item in view.asset_views
        if item.attention_occurrence_count > 0
    )
    opinion_assets = tuple(
        InvestorOpinionAssetView(
            asset_id=item.asset_id,
            asset_name=item.asset_name,
            market=item.market,
            symbol=item.symbol,
            opinion_count=item.opinion_count,
            direction=item.latest_observed_direction,
            published_time=item.latest_opinion_time,
            opinion_summary=getattr(item, "latest_thesis", ()),
        )
        for item in view.asset_views
        if item.opinion_count > 0
    )

    recent = tuple(
        sorted(
            attention_assets,
            key=lambda item: (
                item.latest_observed_time is None,
                -(item.latest_observed_time.timestamp() if item.latest_observed_time else 0),
                item.asset_name,
                item.market,
                item.symbol,
                item.asset_id.int,
            ),
        )[:recent_limit]
    )
    strongest = tuple(
        sorted(
            attention_assets,
            key=lambda item: (
                -item.attention_count,
                item.asset_name,
                item.market,
                item.symbol,
                item.asset_id.int,
            ),
        )[:recent_limit]
    )

    thesis_changes = []
    for item in view.asset_views:
        change_type = getattr(item, "latest_thesis_change_type", None)
        if item.thesis_change_count <= 0 or change_type is None:
            continue
        thesis_changes.append(
            InvestorThesisChangeView(
                asset_id=item.asset_id,
                asset_name=item.asset_name,
                market=item.market,
                symbol=item.symbol,
                effective_time=(
                    getattr(item, "latest_thesis_change_time", None)
                    or item.latest_opinion_time
                    or item.latest_attention_time
                ),
                change_type=change_type,
                previous_direction=None,
                current_direction=item.latest_observed_direction or OpinionDirection.NEUTRAL,
                opinion_id=getattr(item, "latest_opinion_id", None),
                thesis_change_id=getattr(item, "latest_thesis_change_id", None),
            )
        )
    thesis_changes = [item for item in thesis_changes if item.effective_time is not None]
    thesis_changes.sort(
        key=lambda item: (item.effective_time, item.asset_name, item.market, item.symbol)
    )

    shared_attention = tuple(
        item
        for item in attention_assets
        if next(
            summary.shared_attention_investor_count
            for summary in view.asset_views
            if summary.asset_id == item.asset_id
        )
        > 0
    )
    shared_opinion = tuple(
        item
        for item in opinion_assets
        if next(
            summary.shared_opinion_investor_count
            for summary in view.asset_views
            if summary.asset_id == item.asset_id
        )
        > 0
    )

    timeline: list[InvestorTimelineEvent] = []
    for item in view.asset_views:
        if item.latest_attention_time is not None:
            timeline.append(
                InvestorTimelineEvent(
                    timestamp=item.latest_attention_time,
                    asset_id=item.asset_id,
                    asset_name=item.asset_name,
                    market=item.market,
                    symbol=item.symbol,
                    event_type="ATTENTION_OBSERVED",
                )
            )
        if item.latest_opinion_time is not None and item.latest_observed_direction is not None:
            timeline.append(
                InvestorTimelineEvent(
                    timestamp=item.latest_opinion_time,
                    asset_id=item.asset_id,
                    asset_name=item.asset_name,
                    market=item.market,
                    symbol=item.symbol,
                    event_type="OPINION_OBSERVED",
                    opinion=True,
                    direction=item.latest_observed_direction,
                    opinion_id=getattr(item, "latest_opinion_id", None),
                )
            )
        change_type = getattr(item, "latest_thesis_change_type", None)
        change_time = getattr(item, "latest_thesis_change_time", None)
        if change_type is not None and change_time is not None:
            timeline.append(
                InvestorTimelineEvent(
                    timestamp=change_time,
                    asset_id=item.asset_id,
                    asset_name=item.asset_name,
                    market=item.market,
                    symbol=item.symbol,
                    event_type="THESIS_CHANGE_OBSERVED",
                    direction=item.latest_observed_direction,
                    thesis_change=change_type,
                    opinion_id=getattr(item, "latest_opinion_id", None),
                    thesis_change_id=getattr(item, "latest_thesis_change_id", None),
                )
            )
    timeline.sort(
        key=lambda item: (
            item.timestamp,
            item.asset_name,
            item.market,
            item.symbol,
            item.event_type.value,
        )
    )

    return InvestorIntelligenceView(
        investor_id=view.investor_id,
        investor_name=view.investor_name,
        window_start=view.window_start,
        window_end=view.window_end,
        completeness=view.completeness,
        attention_summary=InvestorAttentionSummary(
            total_attention_assets=view.attention_asset_count,
            recent_attention_assets=recent,
            # This is an observed-count ordering only; it is not an attention
            # strength, score, rank, or recommendation.
            strongest_attention_assets=strongest,
        ),
        opinion_summary=InvestorOpinionSummary(
            total_opinion_assets=view.opinion_asset_count,
            bullish_count=sum(item.direction in _BULLISH for item in opinion_assets),
            bearish_count=sum(item.direction in _BEARISH for item in opinion_assets),
            neutral_count=sum(
                item.direction == OpinionDirection.NEUTRAL for item in opinion_assets
            ),
        ),
        thesis_summary=InvestorThesisSummary(
            thesis_change_count=sum(item.thesis_change_count for item in view.asset_views),
            latest_thesis_changes=tuple(thesis_changes[-recent_limit:]),
        ),
        shared_summary=InvestorSharedSummary(
            shared_attention_assets=shared_attention,
            shared_opinion_assets=shared_opinion,
        ),
        timeline=tuple(timeline[-recent_limit:]),
        data_quality=view.data_quality,
    )


__all__ = ["build_investor_intelligence_view"]
