"""Read complete saved evidence without invoking analysis or materialization."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import _read_only_session
from intelligence.product.evidence import (
    EvidenceReadingService,
    EvidenceReadingView,
    EvidenceUnavailable,
)
from intelligence.read_scope import AssetIntelligenceReadScopeNotFoundError

router = APIRouter(prefix="/api/intelligence", tags=["evidence-reading"])


def get_evidence_reading_service():
    return EvidenceReadingService(_read_only_session)


@router.get("/assets/{asset_id}/evidence", response_model=EvidenceReadingView)
def read_evidence(
    asset_id: UUID,
    service: Annotated[EvidenceReadingService, Depends(get_evidence_reading_service)],
    feed_id: UUID | None = None,
    event_id: UUID | None = None,
    signal_id: UUID | None = None,
    thesis_change_id: UUID | None = None,
    history: bool = False,
):
    try:
        return service.read(
            asset_id,
            feed_id=feed_id,
            event_id=event_id,
            signal_id=signal_id,
            thesis_change_id=thesis_change_id,
            history=history,
        )
    except AssetIntelligenceReadScopeNotFoundError as exc:
        raise HTTPException(404, "标的不存在。") from exc
    except EvidenceUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
