"""Read-only service for deterministic Intelligence Pattern detection."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from config import get_settings
from intelligence.context.schemas import IntelligenceContextView
from intelligence.context.service import IntelligenceContextService
from intelligence.patterns.rules import detect_data_quality, detect_patterns
from intelligence.patterns.schemas import (
    IntelligencePatternView,
    PatternAssetIdentity,
    PatternTimeline,
)
from intelligence.schemas.discovery import IntelligenceDiscoveryCandidate


class IntelligencePatternService:
    """Classify existing Context facts without persistence or semantic recomputation."""

    def __init__(
        self,
        context_service: IntelligenceContextService,
        *,
        multi_investor_threshold: int = 3,
    ) -> None:
        if multi_investor_threshold < 2:
            raise ValueError("multi_investor_threshold must be at least 2")
        self._context_service = context_service
        self._multi_investor_threshold = multi_investor_threshold

    @classmethod
    def from_production(
        cls,
        session_factory,
        *,
        multi_investor_threshold: int | None = None,
    ) -> IntelligencePatternService:
        settings = get_settings()
        return cls(
            IntelligenceContextService.from_production(session_factory),
            multi_investor_threshold=(
                multi_investor_threshold
                if multi_investor_threshold is not None
                else settings.pattern_multi_investor_threshold
            ),
        )

    def get_asset_patterns(self, asset_id: UUID) -> IntelligencePatternView:
        context = self._context_service.get_asset_context(asset_id)
        return self._from_context(context)

    def get_context_patterns(
        self,
        context: IntelligenceContextView,
    ) -> IntelligencePatternView:
        """Project one already-read Context without opening another read scope."""

        return self._from_context(context)

    def get_candidate_patterns(
        self,
        candidate: IntelligenceDiscoveryCandidate,
    ) -> IntelligencePatternView:
        context = self._context_service.get_candidate_context(candidate)
        return self._from_context(context)

    def batch_get_patterns(
        self,
        candidates: Iterable[IntelligenceDiscoveryCandidate] | None = None,
        *,
        limit: int = 100,
    ) -> tuple[IntelligencePatternView, ...]:
        contexts = self._context_service.batch_get_context(candidates, limit=limit)
        return tuple(self._from_context(context) for context in contexts)

    def _from_context(self, context: IntelligenceContextView) -> IntelligencePatternView:
        return IntelligencePatternView(
            asset=PatternAssetIdentity(
                asset_id=context.asset.asset_id,
                name=context.asset.name,
                market=context.asset.market,
                symbol=context.asset.symbol,
            ),
            patterns=detect_patterns(
                context,
                multi_investor_threshold=self._multi_investor_threshold,
            ),
            data_quality=detect_data_quality(context),
            timeline=PatternTimeline(
                first_observed_at=context.timeline_context.first_observed_at,
                latest_observed_at=context.timeline_context.latest_observed_at,
            ),
            limitations=list(context.limitations),
        )


__all__ = ["IntelligencePatternService"]
