"""Version-neutral read-only HTTP projections for the Intelligence Query Layer."""

from collections.abc import Callable
from datetime import datetime
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_intelligence_query_service
from intelligence.schemas.intelligence import (
    AssetIntelligenceView,
    InvestorIntelligenceView,
)
from intelligence.schemas.search import IntelligenceSearchResponse
from intelligence.services.combined_asset_intelligence import CombinedAssetNotFoundError
from intelligence.services.intelligence_service import IntelligenceQueryService
from intelligence.services.investor_intelligence import (
    InvestorIntelligenceInvestorNotFoundError,
)

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-query"])
ServiceDependency = Annotated[
    IntelligenceQueryService,
    Depends(get_intelligence_query_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (CombinedAssetNotFoundError, InvestorIntelligenceInvestorNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="intelligence entity not found or has no effective observed evidence",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid intelligence query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence query unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence query unavailable",
        ) from exc


@router.get(
    "/investors/{investor_id}",
    response_model=InvestorIntelligenceView,
    summary="Read one Investor Intelligence View",
    description=(
        "Read-only projection of observed Attention, Opinion, Thesis, and shared-Asset evidence. "
        "Historical completeness is UNKNOWN; no holdings, current-belief, absence, influence, "
        "score, or ranking inference is made."
    ),
)
def get_query_investor(
    investor_id: UUID,
    service: ServiceDependency,
    window_start: Annotated[
        datetime | None,
        Query(description="Inclusive timezone-aware published-time lower bound."),
    ] = None,
    window_end: Annotated[
        datetime | None,
        Query(description="Inclusive timezone-aware published-time upper bound."),
    ] = None,
) -> InvestorIntelligenceView:
    return _read(lambda: service.get_investor_view(investor_id, window_start, window_end))


@router.get(
    "/assets/{asset_id}",
    response_model=AssetIntelligenceView,
    summary="Read one Asset Intelligence View",
    description=(
        "Read-only projection of existing Attention, Opinion, ThesisChange, Snapshot, Alignment, "
        "and Consensus evidence. Consensus is read from persisted evidence; no score or ranking "
        "is calculated. Historical completeness is UNKNOWN."
    ),
)
def get_query_asset(
    asset_id: UUID,
    service: ServiceDependency,
    window_start: Annotated[
        datetime | None,
        Query(description="Inclusive timezone-aware published-time lower bound."),
    ] = None,
    window_end: Annotated[
        datetime | None,
        Query(description="Inclusive timezone-aware published-time upper bound."),
    ] = None,
) -> AssetIntelligenceView:
    return _read(lambda: service.get_asset_view(asset_id, window_start, window_end))


@router.get(
    "/search",
    response_model=IntelligenceSearchResponse,
    summary="Search Investors and listing-level Assets",
    description=(
        "Read-only identity search by Investor name or Asset name, market, and symbol. "
        "A/H listings remain separate entities."
    ),
)
def search_intelligence(
    service: ServiceDependency,
    q: Annotated[str, Query(min_length=1, description="Search text.")],
) -> IntelligenceSearchResponse:
    normalized = q.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="search query must not be blank",
        )
    items = _read(lambda: service.search(normalized))
    return IntelligenceSearchResponse(query=normalized, items=items)


__all__ = ["router"]
