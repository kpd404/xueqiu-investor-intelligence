from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts import InvestorActionClaimDTO, InvestorActionClaimView
from database.models.investor_action_claim import InvestorActionClaim
from database.models.raw_event import RawEvent


class InvestorActionClaimRepository:
    """Persistence adapter for investor text claims, not Portfolio Facts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, claim: InvestorActionClaimDTO) -> InvestorActionClaimView:
        self._validate_event_provenance(claim)
        entity = InvestorActionClaim(
            investor_id=claim.investor_id,
            asset_id=claim.asset_id,
            asset_reference_id=claim.asset_reference_id,
            event_id=claim.event_id,
            claim_type=claim.claim_type,
            confidence=claim.confidence,
            evidence_text=claim.evidence_text,
            published_time=claim.published_time,
            analysis_version=claim.analysis_version,
            created_at=claim.created_at,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def get(self, claim_id: UUID) -> InvestorActionClaimView | None:
        entity = self._session.get(InvestorActionClaim, claim_id)
        return self._to_view(entity) if entity is not None else None

    def list(
        self,
        *,
        investor_id: UUID | None = None,
        event_id: UUID | None = None,
    ) -> list[InvestorActionClaimView]:
        statement = select(InvestorActionClaim)
        if investor_id is not None:
            statement = statement.where(InvestorActionClaim.investor_id == investor_id)
        if event_id is not None:
            statement = statement.where(InvestorActionClaim.event_id == event_id)
        statement = statement.order_by(
            InvestorActionClaim.published_time,
            InvestorActionClaim.id,
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def _validate_event_provenance(self, claim: InvestorActionClaimDTO) -> None:
        event = self._session.get(RawEvent, claim.event_id)
        if event is None:
            raise ValueError("event_id does not reference a RawEvent")
        if event.investor_id != claim.investor_id:
            raise ValueError("claim investor_id must match the source RawEvent")
        if self._as_utc(claim.published_time) != self._as_utc(event.published_time):
            raise ValueError("claim published_time must match the source RawEvent")

    @classmethod
    def _to_view(cls, entity: InvestorActionClaim) -> InvestorActionClaimView:
        return InvestorActionClaimView(
            id=entity.id,
            investor_id=entity.investor_id,
            asset_id=entity.asset_id,
            asset_reference_id=entity.asset_reference_id,
            event_id=entity.event_id,
            claim_type=entity.claim_type,
            confidence=entity.confidence,
            evidence_text=entity.evidence_text,
            published_time=cls._as_utc(entity.published_time),
            analysis_version=entity.analysis_version,
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
