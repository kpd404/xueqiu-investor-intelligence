from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    EffectiveAnalysisPolicy,
    EffectiveStateChangeView,
    EventAnalysisStatus,
    StateChangeCreate,
    StateChangeView,
)
from database.models.event_analysis import EventAnalysis
from database.models.opinion import Opinion
from database.models.state_change import InvestorAssetStateChange


class InvestorAssetStateChangeRepository:
    """Append-only persistence adapter for material state transitions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_identity(
        self,
        triggering_opinion_id: UUID,
        state_policy_version: str,
    ) -> StateChangeView | None:
        statement = select(InvestorAssetStateChange).where(
            InvestorAssetStateChange.triggering_opinion_id == triggering_opinion_id,
            InvestorAssetStateChange.state_policy_version == state_policy_version,
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def add_if_absent(self, command: StateChangeCreate) -> StateChangeView:
        existing = self.get_by_identity(command.triggering_opinion_id, command.state_policy_version)
        if existing is not None:
            return existing

        entity = InvestorAssetStateChange(
            investor_id=command.investor_id,
            asset_id=command.asset_id,
            transition_type=command.transition_type,
            effective_time=command.effective_time,
            calculated_at=command.calculated_at,
            before=command.before,
            after=command.after,
            triggering_opinion_id=command.triggering_opinion_id,
            source_event_ids=[str(value) for value in command.source_event_ids],
            state_policy_version=command.state_policy_version,
        )
        try:
            with self._session.begin_nested():
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_identity(
                command.triggering_opinion_id,
                command.state_policy_version,
            )
            if existing is None:
                raise
            return existing
        return self._to_view(entity)

    def list_effective(
        self,
        policy: EffectiveAnalysisPolicy,
    ) -> list[EffectiveStateChangeView]:
        """Return only ledger rows triggered by the active analysis."""

        statement = (
            select(InvestorAssetStateChange, Opinion.analysis_id, EventAnalysis.analysis_version)
            .join(Opinion, InvestorAssetStateChange.triggering_opinion_id == Opinion.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(
                EventAnalysis.analysis_version == policy.active_analysis_version,
                EventAnalysis.status.in_(
                    [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                ),
            )
            .order_by(
                InvestorAssetStateChange.effective_time,
                InvestorAssetStateChange.id,
            )
        )
        return [
            self._to_effective_view(entity, analysis_id, analysis_version)
            for entity, analysis_id, analysis_version in self._session.execute(statement)
        ]

    @classmethod
    def _to_view(cls, entity: InvestorAssetStateChange) -> StateChangeView:
        transition_type = getattr(entity.transition_type, "value", entity.transition_type)
        return StateChangeView(
            id=entity.id,
            investor_id=entity.investor_id,
            asset_id=entity.asset_id,
            transition_type=transition_type,
            effective_time=cls._as_utc(entity.effective_time),
            calculated_at=cls._as_utc(entity.calculated_at),
            before=entity.before,
            after=entity.after,
            triggering_opinion_id=entity.triggering_opinion_id,
            source_event_ids=tuple(UUID(value) for value in entity.source_event_ids),
            state_policy_version=entity.state_policy_version,
        )

    @classmethod
    def _to_effective_view(
        cls,
        entity: InvestorAssetStateChange,
        analysis_id: UUID | None,
        analysis_version: str,
    ) -> EffectiveStateChangeView:
        if analysis_id is None:
            raise ValueError("effective StateChange must reference an analysis")
        base = cls._to_view(entity)
        return EffectiveStateChangeView(
            **base.model_dump(),
            analysis_id=analysis_id,
            analysis_version=analysis_version,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
