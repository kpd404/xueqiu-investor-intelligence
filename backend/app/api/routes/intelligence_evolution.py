"""Read-only HTTP projection for Asset Intelligence Evolution."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_intelligence_evolution_service
from intelligence.discovery.service import DiscoveryAssetNotFoundError
from intelligence.evolution.schemas import IntelligenceEvolutionView
from intelligence.evolution.service import IntelligenceEvolutionService

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-evolution"])
ServiceDependency = Annotated[
    IntelligenceEvolutionService,
    Depends(get_intelligence_evolution_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DiscoveryAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evolution asset not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid evolution query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence evolution query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence evolution unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence evolution query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence evolution unavailable",
        ) from exc


@router.get(
    "/assets/{asset_id}/evolution",
    response_model=IntelligenceEvolutionView,
    summary="Read fact-time Intelligence Evolution for one Asset",
    description=(
        "Read-only deterministic ordered timeline over persisted evidence. "
        "It does not rank, score, recommend, predict, or call an LLM."
    ),
)
def get_asset_evolution(
    asset_id: UUID,
    service: ServiceDependency,
) -> IntelligenceEvolutionView:
    return _read(lambda: service.get_asset_evolution(asset_id))


__all__ = ["router"]
