"""Operational refresh status API."""

from fastapi import APIRouter

from contracts import OperationalStatusView
from operations.status import OperationalStatusService

router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/status", response_model=OperationalStatusView)
def get_operational_status() -> OperationalStatusView:
    return OperationalStatusService().get_status()


__all__ = ["router"]
