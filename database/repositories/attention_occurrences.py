from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from contracts import (
    PRODUCTION_ATTENTION_POLICY_VERSION,
    AttentionOccurrenceCreate,
    AttentionOccurrenceView,
    AttentionOccurrenceWriteResult,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
)
from database.models.attention_occurrence import AttentionOccurrence
from database.models.event_analysis import EventAnalysis


class AttentionOccurrenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_event(
        self,
        event_id: UUID,
        attention_policy_version: str,
    ) -> list[AttentionOccurrenceView]:
        statement = (
            select(AttentionOccurrence)
            .where(
                AttentionOccurrence.event_id == event_id,
                AttentionOccurrence.attention_policy_version == attention_policy_version,
            )
            .order_by(AttentionOccurrence.asset_id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def replace_for_event(
        self,
        event_id: UUID,
        attention_policy_version: str,
        commands: Sequence[AttentionOccurrenceCreate],
    ) -> AttentionOccurrenceWriteResult:
        command_by_asset = {command.asset_id: command for command in commands}
        if len(command_by_asset) != len(commands):
            raise ValueError("attention occurrence commands must be unique by asset")
        existing = {
            entity.asset_id: entity
            for entity in self._session.scalars(
                select(AttentionOccurrence).where(
                    AttentionOccurrence.event_id == event_id,
                    AttentionOccurrence.attention_policy_version == attention_policy_version,
                )
            )
        }

        deleted_count = 0
        for asset_id, entity in existing.items():
            if asset_id not in command_by_asset:
                self._session.delete(entity)
                deleted_count += 1

        created_count = 0
        updated_count = 0
        occurrence_ids: list[UUID] = []
        for command in sorted(commands, key=lambda value: value.asset_id.int):
            entity = existing.get(command.asset_id)
            if entity is None:
                entity = AttentionOccurrence(
                    investor_id=command.investor_id,
                    asset_id=command.asset_id,
                    event_id=command.event_id,
                    published_time=command.published_time,
                    evidence_types=[value.value for value in command.evidence_types],
                    evidence=[value.model_dump(mode="json") for value in command.evidence],
                    analysis_id=command.analysis_id,
                    opinion_id=command.opinion_id,
                    attention_policy_version=command.attention_policy_version,
                    calculated_at=command.calculated_at,
                )
                self._session.add(entity)
                created_count += 1
            else:
                entity.investor_id = command.investor_id
                entity.published_time = command.published_time
                entity.evidence_types = [value.value for value in command.evidence_types]
                entity.evidence = [value.model_dump(mode="json") for value in command.evidence]
                entity.analysis_id = command.analysis_id
                entity.opinion_id = command.opinion_id
                entity.calculated_at = command.calculated_at
                updated_count += 1
            self._session.flush()
            occurrence_ids.append(entity.id)

        return AttentionOccurrenceWriteResult(
            occurrence_ids=tuple(occurrence_ids),
            created_count=created_count,
            updated_count=updated_count,
            deleted_count=deleted_count,
        )

    def list_effective(
        self,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]:
        """Return occurrences whose interpretation evidence is active.

        Occurrences with only explicit-mention or repost evidence have no
        analysis_id and remain eligible; OPINION evidence must link to the
        active successful/partially-resolved analysis.
        """

        statement = (
            select(AttentionOccurrence)
            .outerjoin(EventAnalysis, AttentionOccurrence.analysis_id == EventAnalysis.id)
            .where(
                AttentionOccurrence.attention_policy_version == attention_policy_version,
                or_(
                    AttentionOccurrence.analysis_id.is_(None),
                    and_(
                        EventAnalysis.analysis_version == policy.active_analysis_version,
                        EventAnalysis.status.in_(
                            [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                        ),
                    ),
                ),
            )
        )
        if as_of is not None:
            statement = statement.where(AttentionOccurrence.published_time <= self._as_utc(as_of))
        statement = statement.order_by(AttentionOccurrence.published_time, AttentionOccurrence.id)
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]:
        """Return one investor's active occurrences in published-time order."""

        statement = (
            select(AttentionOccurrence)
            .outerjoin(EventAnalysis, AttentionOccurrence.analysis_id == EventAnalysis.id)
            .where(
                AttentionOccurrence.investor_id == investor_id,
                AttentionOccurrence.attention_policy_version == attention_policy_version,
                or_(
                    AttentionOccurrence.analysis_id.is_(None),
                    and_(
                        EventAnalysis.analysis_version == policy.active_analysis_version,
                        EventAnalysis.status.in_(
                            [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                        ),
                    ),
                ),
            )
        )
        if as_of is not None:
            statement = statement.where(AttentionOccurrence.published_time <= self._as_utc(as_of))
        statement = statement.order_by(AttentionOccurrence.published_time, AttentionOccurrence.id)
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]:
        """Return effective occurrences for one Asset in fact-time order."""

        statement = (
            select(AttentionOccurrence)
            .outerjoin(EventAnalysis, AttentionOccurrence.analysis_id == EventAnalysis.id)
            .where(
                AttentionOccurrence.asset_id == asset_id,
                AttentionOccurrence.attention_policy_version == attention_policy_version,
                or_(
                    AttentionOccurrence.analysis_id.is_(None),
                    and_(
                        EventAnalysis.analysis_version == policy.active_analysis_version,
                        EventAnalysis.status.in_(
                            [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                        ),
                    ),
                ),
            )
        )
        if as_of is not None:
            statement = statement.where(AttentionOccurrence.published_time <= self._as_utc(as_of))
        statement = statement.order_by(AttentionOccurrence.published_time, AttentionOccurrence.id)
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @classmethod
    def _to_view(cls, entity: AttentionOccurrence) -> AttentionOccurrenceView:
        return AttentionOccurrenceView(
            id=entity.id,
            investor_id=entity.investor_id,
            asset_id=entity.asset_id,
            event_id=entity.event_id,
            published_time=cls._as_utc(entity.published_time),
            evidence_types=tuple(entity.evidence_types),
            evidence=tuple(entity.evidence),
            analysis_id=entity.analysis_id,
            opinion_id=entity.opinion_id,
            attention_policy_version=entity.attention_policy_version,
            calculated_at=cls._as_utc(entity.calculated_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
