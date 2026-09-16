"""Read-only HTTP projection for the Intelligence Feed."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_intelligence_feed_query_service
from contracts import IntelligenceEventType, IntelligencePriorityLevel
from intelligence.feed.query import (
    FeedAssetNotFoundError,
    FeedInvestorNotFoundError,
    IntelligenceFeedQueryService,
)
from intelligence.schemas.feed import IntelligenceFeedListResponse

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-feed"])
ServiceDependency = Annotated[
    IntelligenceFeedQueryService,
    Depends(get_intelligence_feed_query_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (FeedAssetNotFoundError, FeedInvestorNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="feed entity not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid feed query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence feed query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence feed unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence feed query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence feed unavailable",
        ) from exc


@router.get(
    "/feed",
    response_model=IntelligenceFeedListResponse,
    summary="Read the Intelligence Feed",
    description=(
        "Read-only FeedItem projection sorted by observed_at descending. "
        "It does not rank, score, recommend, predict, or modify upstream evidence."
    ),
)
def get_intelligence_feed(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    asset_id: Annotated[UUID | None, Query()] = None,
    investor_id: Annotated[UUID | None, Query()] = None,
    priority_level: Annotated[IntelligencePriorityLevel | None, Query()] = None,
    event_type: Annotated[IntelligenceEventType | None, Query()] = None,
) -> IntelligenceFeedListResponse:
    return _read(
        lambda: service.list_feed(
            limit=limit,
            asset_id=asset_id,
            investor_id=investor_id,
            priority_level=priority_level,
            event_type=event_type,
        )
    )


@router.get(
    "/assets/{asset_id}/feed",
    response_model=IntelligenceFeedListResponse,
    summary="Read one Asset's Intelligence Feed items",
    description="Read-only Asset-scoped FeedItem projection with Priority and evidence context.",
)
def get_asset_feed(
    asset_id: UUID,
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    priority_level: Annotated[IntelligencePriorityLevel | None, Query()] = None,
    event_type: Annotated[IntelligenceEventType | None, Query()] = None,
) -> IntelligenceFeedListResponse:
    return _read(
        lambda: service.get_asset_feed(
            asset_id,
            limit=limit,
            priority_level=priority_level,
            event_type=event_type,
        )
    )


@router.get(
    "/investors/{investor_id}/feed",
    response_model=IntelligenceFeedListResponse,
    summary="Read one Investor's Intelligence Feed items",
    description="Read-only Investor-scoped FeedItem projection based on linked Signal evidence.",
)
def get_investor_feed(
    investor_id: UUID,
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    priority_level: Annotated[IntelligencePriorityLevel | None, Query()] = None,
    event_type: Annotated[IntelligenceEventType | None, Query()] = None,
) -> IntelligenceFeedListResponse:
    return _read(
        lambda: service.get_investor_feed(
            investor_id,
            limit=limit,
            priority_level=priority_level,
            event_type=event_type,
        )
    )


__all__ = ["router"]
