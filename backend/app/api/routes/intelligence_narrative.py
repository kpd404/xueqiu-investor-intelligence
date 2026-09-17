"""Read-only HTTP projection for fact-only Intelligence Narratives."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_intelligence_narrative_service
from intelligence.discovery.service import DiscoveryAssetNotFoundError
from intelligence.narrative.schemas import IntelligenceNarrativeView
from intelligence.narrative.service import IntelligenceNarrativeService

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-narrative"])
ServiceDependency = Annotated[
    IntelligenceNarrativeService,
    Depends(get_intelligence_narrative_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DiscoveryAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="narrative asset not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid narrative query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence narrative query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence narrative unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence narrative query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence narrative unavailable",
        ) from exc


@router.get(
    "/assets/{asset_id}/narrative",
    response_model=IntelligenceNarrativeView,
    summary="Read a fact-only Intelligence Narrative for one Asset",
    description=(
        "Read-only deterministic template projection over an existing Discovery "
        "candidate. It does not rank, score, recommend, predict, or call an LLM."
    ),
)
def get_asset_narrative(
    asset_id: UUID,
    service: ServiceDependency,
) -> IntelligenceNarrativeView:
    return _read(lambda: service.get_asset_narrative(asset_id))


__all__ = ["router"]
