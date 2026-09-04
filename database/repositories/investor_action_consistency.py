from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    CONSISTENCY_POLICY_VERSION,
    EffectiveAnalysisPolicy,
    OpinionActionConsistencyCreate,
    OpinionActionConsistencyView,
    OpinionTimelineEntry,
)
from database.models.investor_action_consistency import InvestorActionConsistency
from database.repositories.opinions import OpinionRepository
from database.repositories.portfolio_actions import PortfolioActionRepository


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

    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        consistency_policy_version: str = CONSISTENCY_POLICY_VERSION,
        as_of: datetime | None = None,
    ) -> list[OpinionActionConsistencyView]:
        actions = PortfolioActionRepository(self._session).list_effective_by_investor(
            investor_id,
            as_of=as_of,
        )
        return self._effective_for_actions(
            investor_id,
            actions,
            policy,
            consistency_policy_version=consistency_policy_version,
            as_of=as_of,
        )

    def list_effective_by_investor_asset(
        self,
        investor_id: UUID,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        consistency_policy_version: str = CONSISTENCY_POLICY_VERSION,
        as_of: datetime | None = None,
    ) -> list[OpinionActionConsistencyView]:
        actions = PortfolioActionRepository(self._session).list_effective_by_investor_asset(
            investor_id,
            asset_id,
            as_of=as_of,
        )
        return self._effective_for_actions(
            investor_id,
            actions,
            policy,
            consistency_policy_version=consistency_policy_version,
            as_of=as_of,
            asset_id=asset_id,
        )

    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        consistency_policy_version: str = CONSISTENCY_POLICY_VERSION,
        as_of: datetime | None = None,
    ) -> list[OpinionActionConsistencyView]:
        investor_ids = self._session.scalars(
            select(InvestorActionConsistency.investor_id)
            .where(
                InvestorActionConsistency.asset_id == asset_id,
                InvestorActionConsistency.consistency_policy_version == consistency_policy_version,
            )
            .distinct()
        )
        artifacts = [
            artifact
            for investor_id in investor_ids
            for artifact in self.list_effective_by_investor_asset(
                investor_id,
                asset_id,
                policy,
                consistency_policy_version=consistency_policy_version,
                as_of=as_of,
            )
        ]
        return sorted(artifacts, key=lambda value: (value.effective_time, value.id.int))

    def _effective_for_actions(
        self,
        investor_id: UUID,
        actions: list[object],
        policy: EffectiveAnalysisPolicy,
        *,
        consistency_policy_version: str,
        as_of: datetime | None,
        asset_id: UUID | None = None,
    ) -> list[OpinionActionConsistencyView]:
        opinions_by_asset: dict[UUID, list[OpinionTimelineEntry]] = {}
        opinion_repository = OpinionRepository(self._session)
        for action in actions:
            if action.asset_id is None:
                continue
            if asset_id is not None and action.asset_id != asset_id:
                continue
            if action.asset_id not in opinions_by_asset:
                opinions = opinion_repository.list_effective_timeline(
                    investor_id,
                    action.asset_id,
                    policy,
                )
                if as_of is not None:
                    normalized_as_of = self._as_utc(as_of)
                    opinions = [
                        opinion
                        for opinion in opinions
                        if self._as_utc(opinion.published_time) <= normalized_as_of
                    ]
                opinions_by_asset[action.asset_id] = opinions

        action_ids = [action.id for action in actions]
        if not action_ids:
            return []
        statement = select(InvestorActionConsistency).where(
            InvestorActionConsistency.investor_id == investor_id,
            InvestorActionConsistency.portfolio_action_id.in_(action_ids),
            InvestorActionConsistency.opinion_analysis_version == policy.active_analysis_version,
            InvestorActionConsistency.consistency_policy_version == consistency_policy_version,
        )
        if asset_id is not None:
            statement = statement.where(InvestorActionConsistency.asset_id == asset_id)
        if as_of is not None:
            statement = statement.where(
                InvestorActionConsistency.effective_time <= self._as_utc(as_of)
            )
        candidates = list(self._session.scalars(statement))
        by_pair = {
            (entity.portfolio_action_id, entity.opinion_id): self._to_view(entity)
            for entity in candidates
        }
        effective: list[OpinionActionConsistencyView] = []
        for action in actions:
            if action.asset_id is None:
                continue
            opinion = self._latest_opinion_before(
                opinions_by_asset.get(action.asset_id, []),
                action.effective_time,
            )
            if opinion is None:
                continue
            artifact = by_pair.get((action.id, opinion.opinion_id))
            if artifact is not None and artifact.asset_id == action.asset_id:
                effective.append(artifact)
        return effective

    @staticmethod
    def _latest_opinion_before(
        opinions: list[OpinionTimelineEntry],
        action_time: datetime,
    ) -> OpinionTimelineEntry | None:
        candidates = [opinion for opinion in opinions if opinion.published_time <= action_time]
        return candidates[-1] if candidates else None

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
