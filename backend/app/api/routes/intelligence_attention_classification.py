"""Read-only HTTP projection for Asset Intelligence Attention Classification."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import (
    get_intelligence_attention_classification_service,
)
from contracts import IntelligenceAttentionClassificationView
from intelligence.attention_classification.service import (
    IntelligenceAttentionClassificationService,
)
from intelligence.discovery.service import DiscoveryAssetNotFoundError

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-attention-classification"])
ServiceDependency = Annotated[
    IntelligenceAttentionClassificationService,
    Depends(get_intelligence_attention_classification_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DiscoveryAssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="attention classification asset not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid attention classification query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("attention classification query failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="attention classification unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected attention classification query failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="attention classification unavailable",
        ) from exc


@router.get(
    "/assets/{asset_id}/attention-classification",
    response_model=IntelligenceAttentionClassificationView,
    summary="Read deterministic human-review Attention Classification",
    description=(
        "Read-only presentation/review semantics over existing Intelligence "
        "evidence. It does not rank, score, recommend, predict, or call an LLM."
    ),
)
def get_asset_attention_classification(
    asset_id: UUID,
    service: ServiceDependency,
) -> IntelligenceAttentionClassificationView:
    return _read(lambda: service.get_asset_attention_classification(asset_id))


__all__ = ["router"]
