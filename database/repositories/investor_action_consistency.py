from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    OpinionActionConsistencyCreate,
    OpinionActionConsistencyView,
)
from database.models.investor_action_consistency import InvestorActionConsistency


class InvestorActionConsistencyRepository:
    """Persistence-only adapter for versioned consistency artifacts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        artifact: OpinionActionConsistencyCreate,
    ) -> OpinionActionConsistencyView:
        entity = InvestorActionConsistency(
            investor_id=artifact.investor_id,
            asset_id=artifact.asset_id,
            opinion_id=artifact.opinion_id,
            opinion_direction=artifact.opinion_direction,
            portfolio_action_id=artifact.portfolio_action_id,
            action_type=artifact.action_type,
            consistency_type=artifact.consistency_type,
            confidence=artifact.confidence,
            evidence=dict(artifact.evidence),
            effective_time=artifact.effective_time,
            calculated_at=artifact.calculated_at,
            opinion_analysis_version=artifact.opinion_analysis_version,
            consistency_policy_version=artifact.consistency_policy_version,
            input_identity=artifact.input_identity,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def add_if_absent(
        self,
        artifact: OpinionActionConsistencyCreate,
    ) -> tuple[OpinionActionConsistencyView, bool]:
        existing = self.get_by_input_identity(artifact.input_identity)
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = InvestorActionConsistency(
                    investor_id=artifact.investor_id,
                    asset_id=artifact.asset_id,
                    opinion_id=artifact.opinion_id,
                    opinion_direction=artifact.opinion_direction,
                    portfolio_action_id=artifact.portfolio_action_id,
                    action_type=artifact.action_type,
                    consistency_type=artifact.consistency_type,
                    confidence=artifact.confidence,
                    evidence=dict(artifact.evidence),
                    effective_time=artifact.effective_time,
                    calculated_at=artifact.calculated_at,
                    opinion_analysis_version=artifact.opinion_analysis_version,
                    consistency_policy_version=artifact.consistency_policy_version,
                    input_identity=artifact.input_identity,
                )
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_input_identity(artifact.input_identity)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def get(self, artifact_id: UUID) -> OpinionActionConsistencyView | None:
        entity = self._session.get(InvestorActionConsistency, artifact_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_input_identity(self, input_identity: str) -> OpinionActionConsistencyView | None:
        statement = select(InvestorActionConsistency).where(
            InvestorActionConsistency.input_identity == input_identity
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def list_by_investor(
        self,
        investor_id: UUID,
        *,
        opinion_analysis_version: str | None = None,
        consistency_policy_version: str | None = None,
    ) -> list[OpinionActionConsistencyView]:
        statement = select(InvestorActionConsistency).where(
            InvestorActionConsistency.investor_id == investor_id
        )
        if opinion_analysis_version is not None:
            statement = statement.where(
                InvestorActionConsistency.opinion_analysis_version == opinion_analysis_version
            )
        if consistency_policy_version is not None:
            statement = statement.where(
                InvestorActionConsistency.consistency_policy_version == consistency_policy_version
            )
        statement = statement.order_by(
            InvestorActionConsistency.effective_time,
            InvestorActionConsistency.id,
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_by_asset(self, asset_id: UUID) -> list[OpinionActionConsistencyView]:
        statement = (
            select(InvestorActionConsistency)
            .where(InvestorActionConsistency.asset_id == asset_id)
            .order_by(InvestorActionConsistency.effective_time, InvestorActionConsistency.id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @classmethod
    def _to_view(cls, entity: InvestorActionConsistency) -> OpinionActionConsistencyView:
        return OpinionActionConsistencyView(
            id=entity.id,
            investor_id=entity.investor_id,
            asset_id=entity.asset_id,
            opinion_id=entity.opinion_id,
            opinion_direction=entity.opinion_direction,
            portfolio_action_id=entity.portfolio_action_id,
            action_type=entity.action_type,
            consistency_type=entity.consistency_type,
            confidence=entity.confidence,
            evidence=entity.evidence,
            effective_time=cls._as_utc(entity.effective_time),
            calculated_at=cls._as_utc(entity.calculated_at),
            opinion_analysis_version=entity.opinion_analysis_version,
            consistency_policy_version=entity.consistency_policy_version,
            input_identity=entity.input_identity,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
