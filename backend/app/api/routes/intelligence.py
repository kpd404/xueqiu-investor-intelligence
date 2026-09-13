"""Thin HTTP projections over the Combined Asset Intelligence read model."""

from collections.abc import Callable
from datetime import datetime
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_combined_asset_intelligence_service
from backend.app.api.intelligence_schemas import (
    AssetIntelligenceListResponse,
    AssetIntelligenceSummaryResponse,
    AssetIntelligenceTimelineResponse,
)
from contracts import CombinedAssetIntelligenceView
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetIntelligenceService,
    CombinedAssetNotFoundError,
)

logger = getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/intelligence",
    tags=["intelligence"],
)

ServiceDependency = Annotated[
    CombinedAssetIntelligenceService,
    Depends(get_combined_asset_intelligence_service),
]
MAX_LIMIT = 100
DEFAULT_LIMIT = 50


def _read[T](operation: Callable[[], T]) -> T:
    """Translate service/read-boundary failures without exposing internals."""

    try:
        return operation()
    except CombinedAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid intelligence query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence read failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence read unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence read failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence read unavailable",
        ) from exc


def _normalize_market(market: str | None) -> str | None:
    if market is None:
        return None
    normalized = market.strip().upper()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="market must not be blank",
        )
    return normalized


@router.get(
    "/assets",
    response_model=AssetIntelligenceListResponse,
    summary="List Asset intelligence summaries",
    description=(
        "Returns bounded summaries of existing effective Asset intelligence. "
        "Evidence is observed in the monitored sample only; historical completeness "
        "is UNKNOWN. The API makes no causality or absence inference and does not rank Assets."
    ),
    responses={
        422: {"description": "Invalid window, filter, limit, or offset."},
        500: {"description": "Unexpected read failure."},
    },
)
def list_intelligence_assets(
    service: ServiceDependency,
    market: Annotated[
        str | None,
        Query(description="Optional market filter, for example SH, SZ, or HK."),
    ] = None,
    min_attention_investors: Annotated[
        int | None,
        Query(ge=0, description="Query-only minimum observed Attention breadth."),
    ] = None,
    min_opinion_investors: Annotated[
        int | None,
        Query(ge=0, description="Query-only minimum observed Opinion breadth."),
    ] = None,
    window_start: Annotated[
        datetime | None,
        Query(description="Inclusive timezone-aware published-time lower bound."),
    ] = None,
    window_end: Annotated[
        datetime | None,
        Query(description="Inclusive timezone-aware published-time upper bound."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_LIMIT,
            description=f"Page size, bounded to {MAX_LIMIT}.",
        ),
    ] = DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of stable-order results to skip."),
    ] = 0,
) -> AssetIntelligenceListResponse:
    normalized_market = _normalize_market(market)
    views = list(
        _read(
            lambda: service.list_asset_views(
                window_start,
                window_end,
                min_attention_investors=min_attention_investors,
                min_opinion_investors=min_opinion_investors,
            )
        )
    )
    if normalized_market is not None:
        views = [view for view in views if view.market.strip().upper() == normalized_market]
    views.sort(key=lambda view: (view.asset_name, view.market, view.symbol, view.asset_id.int))
    total = len(views)
    page = views[offset : offset + limit]
    return AssetIntelligenceListResponse(
        items=tuple(AssetIntelligenceSummaryResponse.from_view(view) for view in page),
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(page) < total,
    )


@router.get(
    "/assets/{asset_id}/timeline",
    response_model=AssetIntelligenceTimelineResponse,
    summary="Get an Asset's unified intelligence timeline",
    description=(
        "Returns Attention, Opinion, and ThesisChange events from existing effective evidence. "
        "Historical completeness is UNKNOWN. Equal-timestamp serialization order is not causal "
        "order; "
        "the API makes no causality or absence inference."
    ),
    responses={
        404: {
            "description": "Asset not found or no intelligence evidence in the requested window."
        },
        422: {"description": "Invalid window."},
        500: {"description": "Unexpected read failure."},
    },
)
def get_intelligence_asset_timeline(
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
) -> AssetIntelligenceTimelineResponse:
    view = _read(lambda: service.get_asset_view(asset_id, window_start, window_end))
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no intelligence evidence in the requested window",
        )
    return AssetIntelligenceTimelineResponse.from_view(view)


@router.get(
    "/assets/{asset_id}",
    response_model=CombinedAssetIntelligenceView,
    summary="Get a complete Combined Asset Intelligence View",
    description=(
        "Returns the existing Combined Asset Intelligence read model without recomputing its "
        "semantics. "
        "Evidence is observed in the monitored sample only; historical completeness is UNKNOWN. "
        "No causality or absence inference is made."
    ),
    responses={
        404: {
            "description": "Asset not found or no intelligence evidence in the requested window."
        },
        422: {"description": "Invalid window."},
        500: {"description": "Unexpected read failure."},
    },
)
def get_intelligence_asset(
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
) -> CombinedAssetIntelligenceView:
    view = _read(lambda: service.get_asset_view(asset_id, window_start, window_end))
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no intelligence evidence in the requested window",
        )
    return view
