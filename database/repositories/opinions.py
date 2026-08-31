from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    OpinionCreate,
    OpinionTimelineEntry,
    OpinionWriteResult,
)
from database.models.event_analysis import EventAnalysis
from database.models.opinion import Opinion
from database.models.raw_event import RawEvent


class OpinionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_event(self, event_id: UUID) -> list[Opinion]:
        statement = select(Opinion).where(Opinion.event_id == event_id).order_by(Opinion.id)
        return list(self._session.scalars(statement))

    def list_by_analysis(self, analysis_id: UUID) -> list[Opinion]:
        statement = select(Opinion).where(Opinion.analysis_id == analysis_id).order_by(Opinion.id)
        return list(self._session.scalars(statement))

    def get(self, opinion_id: UUID) -> Opinion | None:
        return self._session.get(Opinion, opinion_id)

    def get_view(self, opinion_id: UUID) -> OpinionTimelineEntry | None:
        statement = (
            select(Opinion, RawEvent.published_time)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .where(Opinion.id == opinion_id)
        )
        row = self._session.execute(statement).one_or_none()
        if row is None:
            return None
        return self._timeline_entry(row[0], row[1])

    def get_effective_view(
        self,
        opinion_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> OpinionTimelineEntry | None:
        statement = (
            select(Opinion, RawEvent.published_time)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(
                Opinion.id == opinion_id,
                *self._effective_analysis_predicates(policy),
            )
        )
        row = self._session.execute(statement).one_or_none()
        if row is None:
            return None
        return self._timeline_entry(row[0], row[1])

    def list_timeline(self, investor_id: UUID, asset_id: UUID) -> list[OpinionTimelineEntry]:
        statement = (
            select(Opinion, RawEvent.published_time)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .where(
                Opinion.investor_id == investor_id,
                Opinion.asset_id == asset_id,
            )
            .order_by(RawEvent.published_time, RawEvent.id, Opinion.id)
        )
        return [self._timeline_entry(row[0], row[1]) for row in self._session.execute(statement)]

    def list_effective_timeline(
        self,
        investor_id: UUID,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> list[OpinionTimelineEntry]:
        statement = (
            select(Opinion, RawEvent.published_time)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(
                Opinion.investor_id == investor_id,
                Opinion.asset_id == asset_id,
                *self._effective_analysis_predicates(policy),
            )
            .order_by(RawEvent.published_time, RawEvent.id, Opinion.id)
        )
        return [self._timeline_entry(row[0], row[1]) for row in self._session.execute(statement)]

    def list_timeline_by_asset(self, asset_id: UUID) -> list[OpinionTimelineEntry]:
        statement = (
            select(Opinion, RawEvent.published_time)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .where(Opinion.asset_id == asset_id)
            .order_by(Opinion.investor_id, RawEvent.published_time, RawEvent.id, Opinion.id)
        )
        return [self._timeline_entry(row[0], row[1]) for row in self._session.execute(statement)]

    def list_effective_timeline_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> list[OpinionTimelineEntry]:
        statement = (
            select(Opinion, RawEvent.published_time)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(
                Opinion.asset_id == asset_id,
                *self._effective_analysis_predicates(policy),
            )
            .order_by(Opinion.investor_id, RawEvent.published_time, RawEvent.id, Opinion.id)
        )
        return [self._timeline_entry(row[0], row[1]) for row in self._session.execute(statement)]

    def list_effective_by_event(
        self,
        event_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> list[Opinion]:
        statement = (
            select(Opinion)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(
                Opinion.event_id == event_id,
                *self._effective_analysis_predicates(policy),
            )
            .order_by(Opinion.id)
        )
        return list(self._session.scalars(statement))

    def exists(self, event_id: UUID, asset_id: UUID, model_version: str) -> bool:
        statement = select(Opinion.id).where(
            Opinion.event_id == event_id,
            Opinion.asset_id == asset_id,
            Opinion.model_version == model_version,
        )
        return self._session.scalar(statement) is not None

    def add_many(self, commands: Sequence[OpinionCreate]) -> OpinionWriteResult:
        opinion_ids: list[UUID] = []
        created_count = 0

        for command in commands:
            existing = self._get_by_identity(
                command.event_id,
                command.asset_id,
                command.model_version,
                command.analysis_id,
            )
            if existing is not None:
                opinion_ids.append(existing.id)
                continue

            opinion = Opinion(
                event_id=command.event_id,
                analysis_id=command.analysis_id,
                investor_id=command.investor_id,
                asset_id=command.asset_id,
                direction=command.direction,
                strength=command.strength,
                confidence=command.confidence,
                thesis=list(command.thesis),
                catalysts=list(command.catalysts),
                risks=list(command.risks),
                time_horizon=command.time_horizon,
                generated_time=command.generated_time,
                model_version=command.model_version,
            )

            try:
                with self._session.begin_nested():
                    self._session.add(opinion)
                    self._session.flush()
            except IntegrityError:
                existing = self._get_by_identity(
                    command.event_id,
                    command.asset_id,
                    command.model_version,
                    command.analysis_id,
                )
                if existing is None:
                    raise
                opinion_ids.append(existing.id)
                continue

            opinion_ids.append(opinion.id)
            created_count += 1

        return OpinionWriteResult(
            opinion_ids=tuple(opinion_ids),
            created_count=created_count,
        )

    def _get_by_identity(
        self,
        event_id: UUID,
        asset_id: UUID,
        model_version: str,
        analysis_id: UUID | None,
    ) -> Opinion | None:
        predicates = [
            Opinion.event_id == event_id,
            Opinion.asset_id == asset_id,
        ]
        if analysis_id is None:
            predicates.extend(
                [Opinion.analysis_id.is_(None), Opinion.model_version == model_version]
            )
        else:
            predicates.append(Opinion.analysis_id == analysis_id)
        return self._session.scalar(select(Opinion).where(*predicates))

    @staticmethod
    def _effective_analysis_predicates(policy: EffectiveAnalysisPolicy) -> tuple[object, ...]:
        return (
            EventAnalysis.analysis_version == policy.active_analysis_version,
            EventAnalysis.status.in_(
                [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
            ),
        )

    @classmethod
    def _timeline_entry(
        cls,
        opinion: Opinion,
        published_time: datetime,
    ) -> OpinionTimelineEntry:
        return OpinionTimelineEntry(
            opinion_id=opinion.id,
            event_id=opinion.event_id,
            investor_id=opinion.investor_id,
            asset_id=opinion.asset_id,
            direction=opinion.direction,
            strength=opinion.strength,
            confidence=opinion.confidence,
            published_time=cls._as_utc(published_time),
            generated_time=cls._as_utc(opinion.generated_time),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
