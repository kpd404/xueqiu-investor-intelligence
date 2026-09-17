"""Read-only HTTP projection for Intelligence Patterns."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_intelligence_pattern_service
from intelligence.discovery.service import DiscoveryAssetNotFoundError
from intelligence.patterns.schemas import IntelligencePatternView
from intelligence.patterns.service import IntelligencePatternService

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-patterns"])
ServiceDependency = Annotated[
    IntelligencePatternService,
    Depends(get_intelligence_pattern_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DiscoveryAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pattern asset not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid pattern query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence pattern query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence pattern unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence pattern query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence pattern unavailable",
        ) from exc


@router.get(
    "/assets/{asset_id}/patterns",
    response_model=IntelligencePatternView,
    summary="Read deterministic Intelligence Patterns for one Asset",
    description=(
        "Read-only fact classification over Context and existing Intelligence "
        "artifacts. It does not score, rank, recommend, predict, or call an LLM."
    ),
)
def get_asset_patterns(
    asset_id: UUID,
    service: ServiceDependency,
) -> IntelligencePatternView:
    return _read(lambda: service.get_asset_patterns(asset_id))


__all__ = ["router"]
