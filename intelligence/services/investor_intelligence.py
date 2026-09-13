"""Read-only Investor-centric composition of existing Asset intelligence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from contracts import (
    INVESTOR_INTELLIGENCE_LIMITATION_ABSENCE_INFERENCE,
    INVESTOR_INTELLIGENCE_LIMITATION_COLLECTION_PROVENANCE,
    INVESTOR_INTELLIGENCE_LIMITATION_CROSS_INVESTOR,
    INVESTOR_INTELLIGENCE_LIMITATION_HISTORICAL_COMPLETENESS,
    INVESTOR_INTELLIGENCE_LIMITATION_LATEST_DIRECTION,
    INVESTOR_INTELLIGENCE_LIMITATION_MISSING_THESIS,
    CombinedAssetIntelligenceView,
    CombinedAssetInvestorView,
    InvestorAssetIntelligenceSummary,
    InvestorIntelligenceDataQuality,
    InvestorIntelligenceView,
    InvestorOverlapSummary,
    OpinionCoverageState,
)
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetIntelligenceService,
)


class InvestorIntelligenceInvestorNotFoundError(LookupError):
    """Raised when an Investor has no effective observed intelligence."""


class InvestorIntelligenceService:
    """Invert the existing Asset-centric Combined View by Investor."""

    def __init__(self, asset_intelligence_service: CombinedAssetIntelligenceService) -> None:
        self._asset_intelligence_service = asset_intelligence_service

    @classmethod
    def from_production(
        cls,
        unit_of_work_factory: Callable[[], object],
    ) -> InvestorIntelligenceService:
        """Compose Investor views from the current production Asset View."""

        return cls(CombinedAssetIntelligenceService.from_production(unit_of_work_factory))

    def get_investor_view(
        self,
        investor_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> InvestorIntelligenceView:
        """Return one Investor's observed evidence view."""

        views = self.list_investor_views(window_start, window_end)
        for view in views:
            if view.investor_id == investor_id:
                return view
        raise InvestorIntelligenceInvestorNotFoundError(
            f"Investor has no effective observed intelligence: {investor_id}"
        )

    def list_investor_views(
        self,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        *,
        min_attention_assets: int | None = None,
        min_opinion_assets: int | None = None,
    ) -> tuple[InvestorIntelligenceView, ...]:
        """Return query-time Investor views in deterministic name order."""

        if min_attention_assets is not None and min_attention_assets < 0:
            raise ValueError("min_attention_assets must be non-negative")
        if min_opinion_assets is not None and min_opinion_assets < 0:
            raise ValueError("min_opinion_assets must be non-negative")

        asset_views = self._asset_intelligence_service.list_asset_views(
            window_start,
            window_end,
        )
        views = self._build_investor_views(asset_views)
        return tuple(
            view
            for view in views
            if (min_attention_assets is None or view.attention_asset_count >= min_attention_assets)
            and (min_opinion_assets is None or view.opinion_asset_count >= min_opinion_assets)
        )

    def _build_investor_views(
        self,
        asset_views: tuple[CombinedAssetIntelligenceView, ...],
    ) -> tuple[InvestorIntelligenceView, ...]:
        if not asset_views:
            return ()

        summaries_by_investor: dict[UUID, list[InvestorAssetIntelligenceSummary]] = defaultdict(
            list
        )
        investor_names: dict[UUID, str] = {}
        for asset_view in asset_views:
            opinion_investor_count = sum(
                item.opinion_count > 0 for item in asset_view.investor_views
            )
            for investor_view in asset_view.investor_views:
                if not self._has_evidence(investor_view):
                    continue
                investor_names[investor_view.investor_id] = investor_view.investor_name
                summaries_by_investor[investor_view.investor_id].append(
                    self._build_asset_summary(
                        asset_view,
                        investor_view,
                        opinion_investor_count,
                    )
                )

        attention_assets = {
            investor_id: {
                summary.asset_id for summary in summaries if summary.attention_occurrence_count > 0
            }
            for investor_id, summaries in summaries_by_investor.items()
        }
        opinion_assets = {
            investor_id: {summary.asset_id for summary in summaries if summary.opinion_count > 0}
            for investor_id, summaries in summaries_by_investor.items()
        }
        built: list[InvestorIntelligenceView] = []
        for investor_id in sorted(summaries_by_investor, key=lambda value: value.int):
            summaries = sorted(
                summaries_by_investor[investor_id],
                key=lambda value: (
                    value.asset_name,
                    value.market,
                    value.symbol,
                    value.asset_id.int,
                ),
            )
            built.append(
                self._build_investor_view(
                    investor_id,
                    investor_names[investor_id],
                    asset_views[0].window_start,
                    asset_views[0].window_end,
                    asset_views[0].completeness,
                    tuple(summaries),
                    attention_assets,
                    opinion_assets,
                    investor_names,
                )
            )
        return tuple(sorted(built, key=lambda value: (value.investor_name, value.investor_id.int)))

    @staticmethod
    def _has_evidence(investor_view: CombinedAssetInvestorView) -> bool:
        return investor_view.attention_occurrence_count > 0 or investor_view.opinion_count > 0

    @staticmethod
    def _build_asset_summary(
        asset_view: CombinedAssetIntelligenceView,
        investor_view: CombinedAssetInvestorView,
        opinion_investor_count: int,
    ) -> InvestorAssetIntelligenceSummary:
        evidence_times = [
            value
            for value in (investor_view.latest_attention_time, investor_view.latest_opinion_time)
            if value is not None
        ]
        return InvestorAssetIntelligenceSummary(
            asset_id=asset_view.asset_id,
            asset_name=asset_view.asset_name,
            market=asset_view.market,
            symbol=asset_view.symbol,
            attention_occurrence_count=investor_view.attention_occurrence_count,
            first_attention_time=investor_view.first_attention_time,
            latest_attention_time=investor_view.latest_attention_time,
            attention_evidence_types=investor_view.attention_evidence_types,
            opinion_count=investor_view.opinion_count,
            first_opinion_time=investor_view.first_opinion_time,
            latest_opinion_time=investor_view.latest_opinion_time,
            latest_observed_direction=investor_view.latest_observed_direction,
            thesis_change_count=investor_view.thesis_change_count,
            changed_count=investor_view.changed_count,
            extended_count=investor_view.extended_count,
            reversal_count=investor_view.reversal_count,
            missing_thesis_comparison_count=investor_view.missing_thesis_comparison_count,
            attention_investor_count=asset_view.attention_summary.attention_investor_count,
            opinion_investor_count=opinion_investor_count,
            shared_attention_investor_count=max(
                0,
                asset_view.attention_summary.attention_investor_count
                - (1 if investor_view.attention_occurrence_count > 0 else 0),
            ),
            shared_opinion_investor_count=max(
                0,
                opinion_investor_count - (1 if investor_view.opinion_count > 0 else 0),
            ),
            latest_evidence_time=max(evidence_times) if evidence_times else None,
            alignment=(
                asset_view.alignment.directional_alignment_state if asset_view.alignment else None
            ),
            consensus=asset_view.consensus.consensus_state if asset_view.consensus else None,
        )

    @classmethod
    def _build_investor_view(
        cls,
        investor_id: UUID,
        investor_name: str,
        window_start: datetime,
        window_end: datetime,
        completeness,
        summaries: tuple[InvestorAssetIntelligenceSummary, ...],
        attention_assets: dict[UUID, set[UUID]],
        opinion_assets: dict[UUID, set[UUID]],
        investor_names: dict[UUID, str],
    ) -> InvestorIntelligenceView:
        attention_set = attention_assets[investor_id]
        opinion_set = opinion_assets[investor_id]
        missing_thesis = sum(item.missing_thesis_comparison_count for item in summaries)
        lineage_available = any(
            item.alignment is not None or item.consensus is not None for item in summaries
        )
        limitations = [
            INVESTOR_INTELLIGENCE_LIMITATION_HISTORICAL_COMPLETENESS,
            INVESTOR_INTELLIGENCE_LIMITATION_ABSENCE_INFERENCE,
            INVESTOR_INTELLIGENCE_LIMITATION_COLLECTION_PROVENANCE,
            INVESTOR_INTELLIGENCE_LIMITATION_LATEST_DIRECTION,
        ]
        if missing_thesis:
            limitations.append(INVESTOR_INTELLIGENCE_LIMITATION_MISSING_THESIS)
        if not lineage_available:
            limitations.append(INVESTOR_INTELLIGENCE_LIMITATION_CROSS_INVESTOR)
        opinion_coverage = (
            OpinionCoverageState.NONE
            if not opinion_set
            else OpinionCoverageState.PARTIAL
            if len(opinion_set) < len(attention_set)
            else OpinionCoverageState.COMPLETE
        )
        overlaps = []
        for other_id in sorted(
            (set(attention_assets) | set(opinion_assets)) - {investor_id},
            key=lambda value: (investor_names.get(value, ""), value.int),
        ):
            shared_attention = len(attention_set & attention_assets.get(other_id, set()))
            shared_opinion = len(opinion_set & opinion_assets.get(other_id, set()))
            if shared_attention or shared_opinion:
                overlaps.append(
                    InvestorOverlapSummary(
                        other_investor_id=other_id,
                        other_investor_name=investor_names[other_id],
                        shared_attention_asset_count=shared_attention,
                        shared_opinion_asset_count=shared_opinion,
                    )
                )
        observed_times = [
            item.latest_evidence_time for item in summaries if item.latest_evidence_time
        ]
        first_times = [
            value
            for item in summaries
            for value in (item.first_attention_time, item.first_opinion_time)
            if value is not None
        ]
        data_quality = InvestorIntelligenceDataQuality(
            completeness=completeness,
            opinion_coverage=opinion_coverage,
            missing_thesis_comparison_count=missing_thesis,
            cross_investor_lineage_available=lineage_available,
            limitations=tuple(limitations),
        )
        return InvestorIntelligenceView(
            investor_id=investor_id,
            investor_name=investor_name,
            window_start=window_start,
            window_end=window_end,
            completeness=completeness,
            first_observed_evidence_time=min(first_times) if first_times else None,
            latest_observed_evidence_time=max(observed_times) if observed_times else None,
            attention_asset_count=len(attention_set),
            opinion_asset_count=len(opinion_set),
            repeated_opinion_asset_count=sum(item.has_repeated_opinion for item in summaries),
            thesis_changed_asset_count=sum(item.changed_count > 0 for item in summaries),
            direction_reversal_asset_count=sum(item.reversal_count > 0 for item in summaries),
            shared_attention_asset_count=sum(
                item.attention_occurrence_count > 0 and item.shared_attention_investor_count > 0
                for item in summaries
            ),
            shared_opinion_asset_count=sum(
                item.opinion_count > 0 and item.shared_opinion_investor_count > 0
                for item in summaries
            ),
            asset_views=summaries,
            overlap_summaries=tuple(overlaps),
            data_quality=data_quality,
        )


__all__ = [
    "InvestorIntelligenceInvestorNotFoundError",
    "InvestorIntelligenceService",
]
