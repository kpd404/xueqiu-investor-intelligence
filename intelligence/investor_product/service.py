"""Compose the Investor Product View from one shared read scope."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from uuid import UUID

from intelligence.investor_product.schemas import (
    InvestorAssetIntelligenceView,
    InvestorIntelligenceView,
    InvestorProductActivityEvent,
    InvestorProductAttention,
    InvestorProductCoverage,
    InvestorProductDataQuality,
    InvestorProductIdentity,
    InvestorProductOpinion,
    InvestorProductRelationship,
    InvestorProductSummary,
    InvestorProductThesis,
    InvestorProductTraceability,
    InvestorProductTraceabilitySummary,
)
from intelligence.investor_read_scope import (
    InvestorIntelligenceReadScope,
    InvestorIntelligenceReadScopeLoader,
)


class InvestorIntelligenceProductService:
    """Product composition only; persisted Attention/Opinion/Thesis semantics stay intact."""

    def __init__(self, scope_loader: InvestorIntelligenceReadScopeLoader) -> None:
        self._scope_loader = scope_loader

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
    ) -> InvestorIntelligenceProductService:
        return cls(InvestorIntelligenceReadScopeLoader.from_production(session_factory))

    def get_investor_view(self, investor_id: UUID) -> InvestorIntelligenceView:
        scope = self._scope_loader.load(investor_id)
        return self._project(scope)

    def _project(self, scope: InvestorIntelligenceReadScope) -> InvestorIntelligenceView:
        assets_by_id = scope.assets_by_id
        attention_by_asset = self._group_by_asset(scope.attention_occurrences)
        opinion_by_asset = self._group_by_asset(scope.opinions)
        thesis_by_asset = self._group_by_asset(scope.thesis_changes)

        asset_ids = sorted(
            set(attention_by_asset) | set(opinion_by_asset) | set(thesis_by_asset),
            key=lambda value: (
                assets_by_id[value].name if value in assets_by_id else "",
                assets_by_id[value].market if value in assets_by_id else "",
                assets_by_id[value].symbol if value in assets_by_id else "",
                value.int,
            ),
        )
        asset_views = tuple(
            self._asset_view(
                assets_by_id[asset_id],
                attention_by_asset.get(asset_id, ()),
                opinion_by_asset.get(asset_id, ()),
                thesis_by_asset.get(asset_id, ()),
            )
            for asset_id in asset_ids
            if asset_id in assets_by_id
        )
        recent_activity = self._recent_activity(
            assets_by_id,
            attention_by_asset,
            opinion_by_asset,
            thesis_by_asset,
        )

        observed_assets = tuple(item.asset for item in asset_views)
        opinion_assets = tuple(item.asset for item in asset_views if item.relationship.has_opinion)
        attention_only_assets = tuple(
            item.asset for item in asset_views if item.relationship.attention_only
        )
        all_times = [
            item.latest_observed_at for item in asset_views if item.latest_observed_at is not None
        ]
        limitations = (
            "Historical completeness is UNKNOWN.",
            "Available collection provenance does not establish historical completeness.",
            "Historical comparison is unsupported.",
            "Absence inference is unsupported.",
            "Latest Opinion direction is the latest observed persisted Opinion only.",
        )
        return InvestorIntelligenceView(
            investor=InvestorProductIdentity(
                investor_id=scope.investor.investor_id,
                name=scope.investor.name,
                source_platform=scope.investor.platform,
                source_user_id=scope.investor.platform_user_id,
            ),
            window_start=scope.window_start,
            window_end=scope.window_end,
            summary=InvestorProductSummary(
                observed_asset_count=len(observed_assets),
                opinion_asset_count=len(opinion_assets),
                thesis_change_count=len(scope.thesis_changes),
                attention_occurrence_count=len(scope.attention_occurrences),
                opinion_count=len(scope.opinions),
                latest_observed_at=max(all_times) if all_times else None,
            ),
            coverage=InvestorProductCoverage(
                observed_assets=observed_assets,
                opinion_assets=opinion_assets,
                attention_only_assets=attention_only_assets,
            ),
            asset_views=asset_views,
            recent_activity=recent_activity,
            data_quality=InvestorProductDataQuality(limitations=limitations),
            traceability_summary=InvestorProductTraceabilitySummary(
                attention_occurrence_ref_count=len(
                    {item.id for item in scope.attention_occurrences}
                ),
                raw_event_ref_count=len(
                    {
                        *(item.event_id for item in scope.attention_occurrences),
                        *(item.event_id for item in scope.opinions),
                        *(item.current_event_id for item in scope.thesis_changes),
                    }
                ),
                opinion_ref_count=len({item.opinion_id for item in scope.opinions}),
                thesis_change_ref_count=len({item.id for item in scope.thesis_changes}),
                activity_source_ref_count=sum(len(item.source_refs) for item in recent_activity),
            ),
        )

    @staticmethod
    def _group_by_asset(values):
        grouped = defaultdict(list)
        for value in values:
            grouped[value.asset_id].append(value)
        return {
            asset_id: tuple(sorted(items, key=InvestorIntelligenceProductService._fact_key))
            for asset_id, items in grouped.items()
        }

    @staticmethod
    def _fact_key(value):
        fact_time = getattr(value, "published_time", None) or getattr(value, "effective_time", None)
        identity = getattr(value, "id", None) or getattr(value, "opinion_id", None)
        if identity is None:
            identity = getattr(value, "current_event_id", None)
        return fact_time, identity.int

    @classmethod
    def _asset_view(cls, asset, attention, opinions, thesis_changes):
        latest_opinion = opinions[-1] if opinions else None
        latest_thesis = thesis_changes[-1] if thesis_changes else None
        evidence_times = [
            *(item.published_time for item in attention),
            *(item.published_time for item in opinions),
            *(item.effective_time for item in thesis_changes),
        ]
        source_raw_events = {
            *(item.event_id for item in attention),
            *(item.event_id for item in opinions),
            *(item.current_event_id for item in thesis_changes),
        }
        opinion_ids = {item.opinion_id for item in opinions}
        thesis_ids = {item.id for item in thesis_changes}
        attention_ids = {item.id for item in attention}
        return InvestorAssetIntelligenceView(
            asset={
                "asset_id": asset.asset_id,
                "name": asset.name,
                "market": asset.market,
                "symbol": asset.symbol,
            },
            attention=InvestorProductAttention(
                occurrence_count=len(attention),
                first_observed_at=attention[0].published_time if attention else None,
                latest_observed_at=attention[-1].published_time if attention else None,
                evidence_types=tuple(
                    sorted(
                        {evidence for item in attention for evidence in item.evidence_types},
                        key=lambda value: value.value,
                    )
                ),
            ),
            opinion=InvestorProductOpinion(
                opinion_count=len(opinions),
                latest_direction=latest_opinion.direction if latest_opinion else None,
                latest_opinion_at=latest_opinion.published_time if latest_opinion else None,
                latest_opinion_id=latest_opinion.opinion_id if latest_opinion else None,
            ),
            thesis=InvestorProductThesis(
                thesis_change_count=len(thesis_changes),
                latest_change_type=(latest_thesis.change_type.value if latest_thesis else None),
                latest_change_at=latest_thesis.effective_time if latest_thesis else None,
                latest_thesis_change_id=latest_thesis.id if latest_thesis else None,
            ),
            relationship=InvestorProductRelationship(
                has_attention=bool(attention),
                has_opinion=bool(opinions),
                attention_only=bool(attention) and not opinions,
            ),
            latest_observed_at=max(evidence_times) if evidence_times else None,
            traceability=InvestorProductTraceability(
                attention_occurrence_ids=tuple(sorted(attention_ids, key=lambda value: value.int)),
                raw_event_ids=tuple(sorted(source_raw_events, key=lambda value: value.int)),
                opinion_ids=tuple(sorted(opinion_ids, key=lambda value: value.int)),
                thesis_change_ids=tuple(sorted(thesis_ids, key=lambda value: value.int)),
            ),
        )

    @classmethod
    def _recent_activity(
        cls,
        assets_by_id,
        attention_by_asset,
        opinion_by_asset,
        thesis_by_asset,
    ) -> tuple[InvestorProductActivityEvent, ...]:
        events: dict[tuple[str, UUID], InvestorProductActivityEvent] = {}
        for asset_id, items in attention_by_asset.items():
            asset = assets_by_id[asset_id]
            for item in items:
                events.setdefault(
                    ("ATTENTION_OBSERVED", item.id),
                    InvestorProductActivityEvent(
                        observed_at=item.published_time,
                        event_type="ATTENTION_OBSERVED",
                        asset={
                            "asset_id": asset.asset_id,
                            "name": asset.name,
                            "market": asset.market,
                            "symbol": asset.symbol,
                        },
                        source_refs=(
                            ("AttentionOccurrence", item.id),
                            ("RawEvent", item.event_id),
                        ),
                    ),
                )
        for asset_id, items in opinion_by_asset.items():
            asset = assets_by_id[asset_id]
            for item in items:
                events.setdefault(
                    ("OPINION_RECORDED", item.opinion_id),
                    InvestorProductActivityEvent(
                        observed_at=item.published_time,
                        event_type="OPINION_RECORDED",
                        asset={
                            "asset_id": asset.asset_id,
                            "name": asset.name,
                            "market": asset.market,
                            "symbol": asset.symbol,
                        },
                        source_refs=(("Opinion", item.opinion_id), ("RawEvent", item.event_id)),
                    ),
                )
        for asset_id, items in thesis_by_asset.items():
            asset = assets_by_id[asset_id]
            for item in items:
                events.setdefault(
                    ("THESIS_CHANGE_OBSERVED", item.id),
                    InvestorProductActivityEvent(
                        observed_at=item.effective_time,
                        event_type="THESIS_CHANGE_OBSERVED",
                        asset={
                            "asset_id": asset.asset_id,
                            "name": asset.name,
                            "market": asset.market,
                            "symbol": asset.symbol,
                        },
                        source_refs=(
                            ("ThesisChange", item.id),
                            ("RawEvent", item.current_event_id),
                        ),
                    ),
                )
        ordered = sorted(
            events.values(),
            key=lambda item: (
                item.observed_at,
                item.event_type,
                item.asset.asset_id.int,
                item.source_refs[0][1].int,
            ),
        )
        return tuple(ordered[-100:])


__all__ = [
    "InvestorIntelligenceProductService",
]
