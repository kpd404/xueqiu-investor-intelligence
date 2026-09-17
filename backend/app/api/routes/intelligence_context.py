"""Read-only HTTP projection for fact-time Intelligence Context."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_intelligence_context_service
from intelligence.context.schemas import IntelligenceContextView
from intelligence.context.service import (
    DiscoveryAssetNotFoundError,
    IntelligenceContextService,
)

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-context"])
ServiceDependency = Annotated[
    IntelligenceContextService,
    Depends(get_intelligence_context_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DiscoveryAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="context asset not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid context query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("intelligence context query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence context unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected intelligence context query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="intelligence context unavailable",
        ) from exc


@router.get(
    "/assets/{asset_id}/context",
    response_model=IntelligenceContextView,
    summary="Read fact-time Intelligence Context for one Asset",
    description=(
        "Read-only deterministic comparison of explicit current and previous "
        "observed-time windows. It does not score, rank, recommend, predict, "
        "or call an LLM."
    ),
)
def get_asset_context(
    asset_id: UUID,
    service: ServiceDependency,
) -> IntelligenceContextView:
    return _read(lambda: service.get_asset_context(asset_id))


__all__ = ["router"]
