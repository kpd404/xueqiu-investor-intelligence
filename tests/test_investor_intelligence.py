from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from contracts import (
    AttentionEvidenceType,
    CombinedAssetAttentionSummary,
    CombinedAssetDataQuality,
    CombinedAssetIntelligenceView,
    CombinedAssetInvestorView,
    CombinedAttentionOpinionRelation,
    CrossInvestorAssetAlignmentView,
    DirectionalAlignmentState,
    ObservedAttentionCompleteness,
    OpinionCoverageState,
    OpinionDirection,
)
from intelligence.services.investor_intelligence import (
    InvestorIntelligenceInvestorNotFoundError,
    InvestorIntelligenceService,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=10)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _investor(
    investor_id: int,
    name: str,
    *,
    attention: int = 0,
    opinions: int = 0,
    direction: OpinionDirection | None = None,
    changed: int = 0,
    extended: int = 0,
    reversal: int = 0,
    missing: int = 0,
) -> CombinedAssetInvestorView:
    attention_time = START + timedelta(days=1) if attention else None
    opinion_time = START + timedelta(days=2) if opinions else None
    return CombinedAssetInvestorView(
        investor_id=_uuid(investor_id),
        investor_name=name,
        first_attention_time=attention_time,
        latest_attention_time=attention_time,
        attention_occurrence_count=attention,
        attention_evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,) if attention else (),
        first_attention_raw_event_id=_uuid(investor_id + 1000) if attention else None,
        opinion_count=opinions,
        first_opinion_time=opinion_time,
        latest_opinion_time=opinion_time,
        latest_observed_direction=direction,
        latest_observed_confidence=0.8 if opinions else None,
        thesis_change_count=max(0, opinions - missing),
        latest_thesis_change_type=None,
        reversal_count=reversal,
        changed_count=changed,
        extended_count=extended,
        missing_thesis_comparison_count=missing,
        thesis_timeline=None,
        attention_opinion_relation=(
            CombinedAttentionOpinionRelation.ATTENTION_WITHOUT_OPINION
            if not opinions
            else CombinedAttentionOpinionRelation.OPINION_AFTER_ATTENTION
        ),
        attention_to_first_opinion_lag=(timedelta(days=1).total_seconds() if opinions else None),
        attention_to_first_opinion_lag_hours=(24.0 if opinions else None),
        attention_to_first_opinion_lag_days=(1.0 if opinions else None),
    )


def _asset(
    asset_id: int,
    name: str,
    market: str,
    symbol: str,
    investors: tuple[CombinedAssetInvestorView, ...],
    *,
    alignment: DirectionalAlignmentState | None = None,
) -> CombinedAssetIntelligenceView:
    attention_investors = [value for value in investors if value.attention_occurrence_count]
    attention_times = [value.latest_attention_time for value in attention_investors]
    attention_times = [value for value in attention_times if value is not None]
    earliest = min(attention_times) if attention_times else None
    evidence_times = [
        value
        for investor in investors
        for value in (investor.latest_attention_time, investor.latest_opinion_time)
        if value is not None
    ]
    latest = max(evidence_times, default=None)
    span = (latest - earliest).total_seconds() if earliest and latest else None
    alignment_view = None
    if alignment is not None:
        alignment_view = CrossInvestorAssetAlignmentView(
            id=_uuid(asset_id + 5000),
            asset_id=_uuid(asset_id),
            source_snapshot_id=_uuid(asset_id + 6000),
            opinion_coverage_state=OpinionCoverageState.COMPLETE,
            directional_alignment_state=alignment,
            alignment_policy_version="alignment-v1",
            input_identity="a" * 64,
            calculated_at=END,
            created_at=END,
        )
    missing = sum(value.missing_thesis_comparison_count for value in investors)
    cross_available = alignment_view is not None
    return CombinedAssetIntelligenceView(
        asset_id=_uuid(asset_id),
        asset_name=name,
        market=market,
        symbol=symbol,
        window_start=START,
        window_end=END,
        completeness=ObservedAttentionCompleteness.UNKNOWN,
        attention_summary=CombinedAssetAttentionSummary(
            attention_investor_count=len(attention_investors),
            attention_occurrence_count=sum(value.attention_occurrence_count for value in investors),
            earliest_observed_time=earliest,
            earliest_observed_investor_id=(
                attention_investors[0].investor_id if attention_investors else None
            ),
            earliest_observed_investor_name=(
                attention_investors[0].investor_name if attention_investors else None
            ),
            observed_span_seconds=span,
            observed_span_hours=span / 3600 if span is not None else None,
            observed_span_days=span / 86400 if span is not None else None,
        ),
        investor_views=investors,
        alignment=alignment_view,
        data_quality=CombinedAssetDataQuality(
            completeness=ObservedAttentionCompleteness.UNKNOWN,
            opinion_coverage=OpinionCoverageState.COMPLETE,
            missing_thesis_comparison_count=missing,
            cross_investor_evidence_available=cross_available,
            unresolved_semantic_limitations=("HISTORICAL_COMPLETENESS_UNKNOWN",),
        ),
    )


class _StubAssetIntelligenceService:
    def __init__(self, views: tuple[CombinedAssetIntelligenceView, ...]):
        self.views = views
        self.calls: list[tuple[datetime | None, datetime | None]] = []

    def list_asset_views(self, window_start=None, window_end=None):
        self.calls.append((window_start, window_end))
        return self.views


@pytest.fixture
def service() -> InvestorIntelligenceService:
    alpha = _investor(11, "alpha", attention=2, opinions=1, direction=OpinionDirection.BULLISH)
    beta = _investor(12, "beta", attention=1, opinions=1, direction=OpinionDirection.BEARISH)
    beta_without_opinion = _investor(12, "beta", attention=1)
    asset_sh = _asset(
        1,
        "山东黄金",
        "SH",
        "600547",
        (alpha, beta),
        alignment=DirectionalAlignmentState.MIXED_DIRECTION,
    )
    asset_hk = _asset(
        2,
        "山东黄金",
        "HK",
        "01787",
        (
            _investor(
                11,
                "alpha",
                attention=1,
                opinions=2,
                direction=OpinionDirection.BEARISH,
                changed=1,
                extended=1,
                reversal=1,
            ),
            beta_without_opinion,
        ),
    )
    asset_datang = _asset(
        3,
        "大唐发电",
        "HK",
        "00991",
        (
            _investor(
                13,
                "爱投资的小人书",
                attention=1,
                opinions=14,
                direction=OpinionDirection.BULLISH,
                missing=1,
            ),
        ),
    )
    return InvestorIntelligenceService(
        _StubAssetIntelligenceService((asset_sh, asset_hk, asset_datang))
    )


def test_investor_view_inverts_existing_asset_evidence_and_preserves_listing_identity(service):
    alpha = service.get_investor_view(_uuid(11), START, END)

    assert alpha.investor_name == "alpha"
    assert alpha.completeness is ObservedAttentionCompleteness.UNKNOWN
    assert alpha.attention_asset_count == 2
    assert alpha.opinion_asset_count == 2
    assert alpha.repeated_opinion_asset_count == 1
    assert alpha.thesis_changed_asset_count == 1
    assert alpha.direction_reversal_asset_count == 1
    assert alpha.shared_attention_asset_count == 2
    assert alpha.shared_opinion_asset_count == 1
    assert alpha.asset_views[0].shared_attention_investor_count == 1
    assert alpha.asset_views[0].shared_opinion_investor_count == 0
    assert alpha.asset_views[1].shared_attention_investor_count == 1
    assert alpha.asset_views[1].shared_opinion_investor_count == 1
    assert [(item.market, item.symbol) for item in alpha.asset_views] == [
        ("HK", "01787"),
        ("SH", "600547"),
    ]
    assert alpha.asset_views[0].latest_observed_direction is OpinionDirection.BEARISH
    assert alpha.overlap_summaries[0].other_investor_name == "beta"
    assert alpha.overlap_summaries[0].shared_attention_asset_count == 2
    assert alpha.overlap_summaries[0].shared_opinion_asset_count == 1
    assert all(item.other_investor_id != alpha.investor_id for item in alpha.overlap_summaries)
    assert alpha.data_quality.opinion_coverage is OpinionCoverageState.COMPLETE
    assert all(
        field not in alpha.model_dump()
        for field in ("score", "ranking", "influence", "current_belief", "holdings")
    )


def test_missing_thesis_comparison_is_retained_and_attention_only_is_not_inferred(service):
    investor = service.get_investor_view(_uuid(13), START, END)

    assert investor.asset_views[0].opinion_count == 14
    assert investor.asset_views[0].missing_thesis_comparison_count == 1
    assert investor.data_quality.missing_thesis_comparison_count == 1
    assert "MISSING_THESIS_COMPARISON" in investor.data_quality.limitations

    beta = next(
        view for view in service.list_investor_views(START, END) if view.investor_name == "beta"
    )
    assert beta.attention_asset_count == 2
    assert beta.opinion_asset_count == 1
    assert beta.data_quality.opinion_coverage is OpinionCoverageState.PARTIAL


def test_investor_list_is_deterministic_and_supports_query_filters(service):
    first = service.list_investor_views(START, END)
    second = service.list_investor_views(START, END)

    assert first == second
    assert [view.investor_name for view in first] == ["alpha", "beta", "爱投资的小人书"]
    assert [
        view.investor_name
        for view in service.list_investor_views(START, END, min_attention_assets=2)
    ] == ["alpha", "beta"]
    assert [
        view.investor_name for view in service.list_investor_views(START, END, min_opinion_assets=2)
    ] == ["alpha"]


def test_unknown_investor_and_negative_filters_are_rejected(service):
    with pytest.raises(InvestorIntelligenceInvestorNotFoundError):
        service.get_investor_view(_uuid(999), START, END)
    with pytest.raises(ValueError):
        service.list_investor_views(START, END, min_attention_assets=-1)
    with pytest.raises(ValueError):
        service.list_investor_views(START, END, min_opinion_assets=-1)
