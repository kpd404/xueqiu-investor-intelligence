"""Unified read-only Investor Intelligence Product endpoint."""

from collections.abc import Callable
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.dependencies import get_investor_intelligence_product_service
from intelligence.investor_product.schemas import InvestorIntelligenceView
from intelligence.investor_product.service import InvestorIntelligenceProductService
from intelligence.investor_read_scope import InvestorIntelligenceReadScopeNotFoundError

logger = getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence-investor-product"])
ServiceDependency = Annotated[
    InvestorIntelligenceProductService,
    Depends(get_investor_intelligence_product_service),
]


def _read[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except InvestorIntelligenceReadScopeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="investor intelligence view not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid investor intelligence view query",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Investor Product View failed at the database boundary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="investor intelligence view unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected Investor Product View failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="investor intelligence view unavailable",
        ) from exc


@router.get(
    "/investors/{investor_id}/view",
    response_model=InvestorIntelligenceView,
    summary="Read the unified Investor Intelligence Product View",
    description=(
        "Query-time composition of existing Attention, Opinion, ThesisChange, "
        "Asset, and RawEvent evidence. It does not rank Investors or infer skill."
    ),
)
def get_investor_intelligence_view(
    investor_id: UUID,
    service: ServiceDependency,
) -> InvestorIntelligenceView:
    return _read(lambda: service.get_investor_view(investor_id))


__all__ = ["router"]
