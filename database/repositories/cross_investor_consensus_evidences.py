from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    ConsensusInvestorContribution,
    CrossInvestorConsensusEvidenceCreate,
    CrossInvestorConsensusEvidenceView,
)
from database.models.cross_investor_consensus_evidence import CrossInvestorConsensusEvidence


class CrossInvestorConsensusEvidenceRepository:
    """Persistence adapter for immutable Consensus/Divergence evidence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        evidence: CrossInvestorConsensusEvidenceCreate,
    ) -> CrossInvestorConsensusEvidenceView:
        entity = self._build_entity(evidence)
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def add_if_absent(
        self,
        evidence: CrossInvestorConsensusEvidenceCreate,
    ) -> tuple[CrossInvestorConsensusEvidenceView, bool]:
        existing = self.get_by_input_identity(evidence.input_identity)
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = self._build_entity(evidence)
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_input_identity(evidence.input_identity)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def get(self, evidence_id: UUID) -> CrossInvestorConsensusEvidenceView | None:
        entity = self._session.get(CrossInvestorConsensusEvidence, evidence_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_input_identity(
        self,
        input_identity: str,
    ) -> CrossInvestorConsensusEvidenceView | None:
        entity = self._session.scalar(
            select(CrossInvestorConsensusEvidence).where(
                CrossInvestorConsensusEvidence.input_identity == input_identity
            )
        )
        return self._to_view(entity) if entity is not None else None

    def list_by_asset(self, asset_id: UUID) -> list[CrossInvestorConsensusEvidenceView]:
        statement = (
            select(CrossInvestorConsensusEvidence)
            .where(CrossInvestorConsensusEvidence.asset_id == asset_id)
            .order_by(
                CrossInvestorConsensusEvidence.created_at,
                CrossInvestorConsensusEvidence.id,
            )
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_by_source_snapshot(
        self,
        source_snapshot_id: UUID,
    ) -> list[CrossInvestorConsensusEvidenceView]:
        statement = (
            select(CrossInvestorConsensusEvidence)
            .where(CrossInvestorConsensusEvidence.source_snapshot_id == source_snapshot_id)
            .order_by(
                CrossInvestorConsensusEvidence.consensus_policy_version,
                CrossInvestorConsensusEvidence.created_at,
                CrossInvestorConsensusEvidence.id,
            )
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @staticmethod
    def _build_entity(
        evidence: CrossInvestorConsensusEvidenceCreate,
    ) -> CrossInvestorConsensusEvidence:
        return CrossInvestorConsensusEvidence(
            asset_id=evidence.asset_id,
            source_snapshot_id=evidence.source_snapshot_id,
            source_alignment_id=evidence.source_alignment_id,
            attention_investor_count=evidence.attention_investor_count,
            opinion_investor_count=evidence.opinion_investor_count,
            bullish_investor_count=evidence.bullish_investor_count,
            bearish_investor_count=evidence.bearish_investor_count,
            neutral_investor_count=evidence.neutral_investor_count,
            opinion_coverage_state=evidence.opinion_coverage_state,
            consensus_state=evidence.consensus_state,
            contributing_investor_ids=[
                str(investor_id) for investor_id in evidence.contributing_investor_ids
            ],
            latest_opinions=[
                contribution.model_dump(mode="json") for contribution in evidence.latest_opinions
            ],
            consensus_policy_version=evidence.consensus_policy_version,
            input_identity=evidence.input_identity,
            calculated_at=evidence.calculated_at,
            created_at=evidence.created_at,
        )

    @classmethod
    def _to_view(
        cls,
        entity: CrossInvestorConsensusEvidence,
    ) -> CrossInvestorConsensusEvidenceView:
        contributing_investor_ids = tuple(
            UUID(str(value)) for value in (entity.contributing_investor_ids or [])
        )
        latest_opinions = tuple(
            ConsensusInvestorContribution.model_validate(value)
            for value in (entity.latest_opinions or [])
        )
        return CrossInvestorConsensusEvidenceView(
            id=entity.id,
            asset_id=entity.asset_id,
            source_snapshot_id=entity.source_snapshot_id,
            source_alignment_id=entity.source_alignment_id,
            attention_investor_count=entity.attention_investor_count,
            opinion_investor_count=entity.opinion_investor_count,
            bullish_investor_count=entity.bullish_investor_count,
            bearish_investor_count=entity.bearish_investor_count,
            neutral_investor_count=entity.neutral_investor_count,
            opinion_coverage_state=entity.opinion_coverage_state,
            consensus_state=entity.consensus_state,
            contributing_investor_ids=contributing_investor_ids,
            latest_opinions=latest_opinions,
            consensus_policy_version=entity.consensus_policy_version,
            input_identity=entity.input_identity,
            calculated_at=cls._as_utc(entity.calculated_at),
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["CrossInvestorConsensusEvidenceRepository"]
