"""Read-only HTTP projection for Asset-grouped Intelligence Discovery."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_intelligence_discovery_service
from contracts import IntelligenceEventType
from intelligence.discovery.service import (
    DiscoveryAssetNotFoundError,
    IntelligenceDiscoveryService,
)
from intelligence.schemas.discovery import IntelligenceDiscoveryListResponse

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-discovery"])
ServiceDependency = Annotated[
    IntelligenceDiscoveryService,
    Depends(get_intelligence_discovery_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DiscoveryAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="discovery asset not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid discovery query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence discovery query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence discovery unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence discovery query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence discovery unavailable",
        ) from exc


@router.get(
    "/discovery",
    response_model=IntelligenceDiscoveryListResponse,
    summary="Read Asset-grouped Intelligence Discovery candidates",
    description=(
        "Read-only deterministic aggregation of ACTIVE FeedItems. "
        "The result is ordered by latest observed time only; it has no score, "
        "rank, weight, recommendation, or prediction semantics."
    ),
)
def get_intelligence_discovery(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    asset_id: Annotated[UUID | None, Query()] = None,
    event_type: Annotated[IntelligenceEventType | None, Query()] = None,
) -> IntelligenceDiscoveryListResponse:
    return _read(
        lambda: service.get_candidates(
            limit=limit,
            asset_id=asset_id,
            event_type=event_type,
        )
    )


__all__ = ["router"]
