"""Application service for the read-only Intelligence Query Layer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from contracts import CombinedAssetIntelligenceView
from intelligence.queries.asset_view import build_asset_intelligence_view
from intelligence.queries.investor_view import build_investor_intelligence_view
from intelligence.queries.search import (
    IntelligenceSearchReader,
    SqlAlchemyIntelligenceSearchReader,
)
from intelligence.queries.signal_view import build_signal_candidate_views
from intelligence.schemas.intelligence import (
    AssetIntelligenceView,
    IntelligenceSearchEntity,
    InvestorIntelligenceView,
    SignalCandidateView,
)
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetIntelligenceService,
    CombinedAssetNotFoundError,
)
from intelligence.services.investor_intelligence import (
    InvestorIntelligenceInvestorNotFoundError,
    InvestorIntelligenceService,
)


class IntelligenceQueryAssetService(Protocol):
    def get_asset_view(
        self,
        asset_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> CombinedAssetIntelligenceView | None: ...


class IntelligenceQueryInvestorService(Protocol):
    def get_investor_view(
        self,
        investor_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> object: ...


class IntelligenceQueryService:
    """Compose existing effective read services and identity search."""

    def __init__(
        self,
        asset_service: IntelligenceQueryAssetService,
        investor_service: IntelligenceQueryInvestorService,
        search_reader: IntelligenceSearchReader,
    ) -> None:
        self._asset_service = asset_service
        self._investor_service = investor_service
        self._search_reader = search_reader

    @classmethod
    def from_production(
        cls,
        unit_of_work_factory: Callable[[], object],
        search_session_factory: Callable[[], object],
    ) -> IntelligenceQueryService:
        return cls(
            CombinedAssetIntelligenceService.from_production(unit_of_work_factory),
            InvestorIntelligenceService.from_production(unit_of_work_factory),
            SqlAlchemyIntelligenceSearchReader(search_session_factory),
        )

    def get_investor_view(
        self,
        investor_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> InvestorIntelligenceView:
        try:
            view = self._investor_service.get_investor_view(
                investor_id,
                window_start,
                window_end,
            )
        except InvestorIntelligenceInvestorNotFoundError:
            raise
        return build_investor_intelligence_view(view)

    def get_asset_view(
        self,
        asset_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> AssetIntelligenceView:
        view = self._asset_service.get_asset_view(asset_id, window_start, window_end)
        if view is None:
            raise CombinedAssetNotFoundError(
                f"asset has no effective observed intelligence: {asset_id}"
            )
        return build_asset_intelligence_view(view)

    def get_signal_candidates(
        self,
        asset_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> tuple[SignalCandidateView, ...]:
        view = self._asset_service.get_asset_view(asset_id, window_start, window_end)
        if view is None:
            raise CombinedAssetNotFoundError(
                f"asset has no effective observed intelligence: {asset_id}"
            )
        return build_signal_candidate_views(view)

    def search(self, query: str) -> tuple[IntelligenceSearchEntity, ...]:
        return self._search_reader.search(query)


__all__ = [
    "IntelligenceQueryAssetService",
    "IntelligenceQueryInvestorService",
    "IntelligenceQueryService",
]
