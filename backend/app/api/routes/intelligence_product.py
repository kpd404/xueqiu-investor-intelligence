"""Unified read-only Product V0 Asset Intelligence endpoint."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_asset_intelligence_product_service
from intelligence.product.schemas import AssetIntelligenceView
from intelligence.product.service import AssetIntelligenceProductService
from intelligence.read_scope import AssetIntelligenceReadScopeNotFoundError

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-product"])
ServiceDependency = Annotated[
    AssetIntelligenceProductService,
    Depends(get_asset_intelligence_product_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except AssetIntelligenceReadScopeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset intelligence view not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid asset intelligence view query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("asset intelligence Product View failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="asset intelligence view unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected asset intelligence Product View failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="asset intelligence view unavailable",
        ) from exc


@router.get(
    "/assets/{asset_id}/view",
    response_model=AssetIntelligenceView,
    summary="Read the unified Asset Intelligence Product View",
    description=(
        "Query-time composition of existing Discovery, Narrative, Context, Pattern, "
        "Evolution, Feed/Event lifecycle, and Attention Classification projections. "
        "It adds no persisted Intelligence semantic, score, ranking, or recommendation."
    ),
)
def get_asset_intelligence_view(
    asset_id: UUID,
    service: ServiceDependency,
) -> AssetIntelligenceView:
    return _read(lambda: service.get_asset_view(asset_id))


__all__ = ["router"]
