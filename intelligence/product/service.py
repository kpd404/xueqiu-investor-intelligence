"""Compose the Product V0 Asset view from one shared read scope."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from contracts import FeedState, IntelligenceEventState
from intelligence.attention_classification.service import (
    IntelligenceAttentionClassificationService,
)
from intelligence.context.service import IntelligenceContextService
from intelligence.discovery.service import IntelligenceDiscoveryService
from intelligence.evolution.service import IntelligenceEvolutionService
from intelligence.narrative.service import IntelligenceNarrativeService
from intelligence.patterns.service import IntelligencePatternService
from intelligence.product.schemas import (
    AssetIntelligenceView,
    ProductAssetIdentity,
    ProductContextView,
    ProductCurrentStateView,
    ProductDataQualityView,
    ProductDiscoveryView,
    ProductEvolutionView,
    ProductLifecycleSummary,
    ProductNarrativeView,
    ProductReviewView,
    ProductTraceabilitySummary,
)
from intelligence.read_scope import AssetIntelligenceReadScopeLoader

RECENT_EVOLUTION_STEP_LIMIT = 20
_INTERMEDIATE_SOURCE_TYPES = {
    "IntelligenceEvent",
    "IntelligenceEventPriority",
    "IntelligenceFeedItem",
    "Priority",
    "Signal",
}


class AssetIntelligenceProductService:
    """Product composition only; all semantics remain owned by existing layers."""

    def __init__(
        self,
        scope_loader: AssetIntelligenceReadScopeLoader,
        discovery_service: IntelligenceDiscoveryService,
        narrative_service: IntelligenceNarrativeService,
        context_service: IntelligenceContextService,
        pattern_service: IntelligencePatternService,
        evolution_service: IntelligenceEvolutionService,
        attention_service: IntelligenceAttentionClassificationService,
    ) -> None:
        self._scope_loader = scope_loader
        self._discovery_service = discovery_service
        self._narrative_service = narrative_service
        self._context_service = context_service
        self._pattern_service = pattern_service
        self._evolution_service = evolution_service
        self._attention_service = attention_service

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
    ) -> AssetIntelligenceProductService:
        discovery = IntelligenceDiscoveryService.from_production(session_factory)
        context = IntelligenceContextService.from_production(session_factory)
        pattern = IntelligencePatternService.from_production(session_factory)
        evolution = IntelligenceEvolutionService.from_production(session_factory)
        attention = IntelligenceAttentionClassificationService.from_production(session_factory)
        return cls(
            AssetIntelligenceReadScopeLoader.from_production(session_factory),
            discovery,
            IntelligenceNarrativeService(discovery),
            context,
            pattern,
            evolution,
            attention,
        )

    def get_asset_view(
        self,
        asset_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> AssetIntelligenceView:
        scope = self._scope_loader.load(asset_id, as_of=as_of)
        candidate = self._discovery_service.get_scope_candidate(scope)
        context = self._context_service.get_scope_context(
            scope,
            candidate,
            as_of=scope.as_of,
        )
        pattern = self._pattern_service.get_context_patterns(context)
        narrative = self._narrative_service.get_scope_narrative(scope, candidate)
        evolution = self._evolution_service.get_scope_evolution(scope, context, pattern)
        attention = self._attention_service.get_scope_attention_classification(
            scope,
            candidate,
            evolution,
        )

        feed_states = self._state_counts(scope.feed_items)
        event_states = self._state_counts(scope.events)
        limitations = self._data_quality_limitations(
            context.limitations,
            pattern.limitations,
            evolution.limitations,
            attention.limitations,
            narrative.limitations,
        )
        source_types = tuple(sorted({item.source_type for item in attention.evidence_refs}))
        canonical_sources = {
            (item.source_type, item.source_id)
            for item in attention.evidence_refs
            if item.source_type not in _INTERMEDIATE_SOURCE_TYPES
        }

        return AssetIntelligenceView(
            asset=ProductAssetIdentity(
                asset_id=scope.asset.asset_id,
                name=scope.asset.name,
                market=scope.asset.market,
                symbol=scope.asset.symbol,
            ),
            review=ProductReviewView(
                attention_class=attention.attention_class,
                reasons=attention.reasons,
                latest_observed_at=attention.latest_observed_at,
            ),
            discovery=ProductDiscoveryView(
                is_discoverable=candidate is not None,
                discovery_reasons=(
                    tuple(candidate.discovery_reasons) if candidate is not None else ()
                ),
                activity_summary=(candidate.activity_summary if candidate is not None else None),
            ),
            current_state=ProductCurrentStateView(
                alignment=evolution.current_state.alignment_state,
                consensus=evolution.current_state.consensus_state,
                patterns=tuple(evolution.current_state.patterns),
            ),
            context=ProductContextView(
                activity_context=context.activity_context,
                investor_context=context.investor_context,
                attention_context=context.attention_context,
                thesis_context=context.thesis_context,
                timeline_context=context.timeline_context,
            ),
            narrative=ProductNarrativeView(
                headline=narrative.headline,
                summary=narrative.summary,
                attention_summary=narrative.attention_summary,
                thesis_summary=narrative.thesis_summary,
                cross_investor_summary=narrative.cross_investor_summary,
                consensus_summary=narrative.consensus_summary,
            ),
            evolution=ProductEvolutionView(
                timeline_range=evolution.timeline_range,
                step_count=len(evolution.timeline),
                recent_steps=tuple(evolution.timeline[-RECENT_EVOLUTION_STEP_LIMIT:]),
            ),
            feed=ProductLifecycleSummary(
                active_count=feed_states.get(FeedState.ACTIVE.value, 0),
                states=feed_states,
            ),
            events=ProductLifecycleSummary(
                active_count=event_states.get(IntelligenceEventState.ACTIVE.value, 0),
                states=event_states,
            ),
            data_quality=ProductDataQualityView(limitations=limitations),
            traceability_summary=ProductTraceabilitySummary(
                source_ref_count=len(attention.evidence_refs),
                canonical_source_count=len(canonical_sources),
                source_types=source_types,
                signal_count=len(scope.signals),
                evidence_refs=attention.evidence_refs,
            ),
        )

    @staticmethod
    def _state_counts(items) -> dict[str, int]:
        counts = Counter(item.state.value for item in items)
        return dict(sorted(counts.items()))

    @staticmethod
    def _data_quality_limitations(*groups) -> tuple[str, ...]:
        values: list[str] = [
            "Historical completeness is UNKNOWN.",
            "Available collection provenance does not establish historical completeness.",
            "Absence inference is unsupported.",
        ]
        for group in groups:
            values.extend(group)
        normalized = [
            (
                "Available collection provenance does not establish historical completeness."
                if "Collection provenance is unavailable" in value
                or "collection provenance remain UNKNOWN/unavailable" in value
                else value
            )
            for value in values
        ]
        return tuple(dict.fromkeys(normalized))


__all__ = ["AssetIntelligenceProductService", "RECENT_EVOLUTION_STEP_LIMIT"]
