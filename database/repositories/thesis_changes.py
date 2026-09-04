from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    ThesisChangeCreate,
    ThesisChangeView,
)
from database.models.event_analysis import EventAnalysis
from database.models.opinion import Opinion
from database.models.raw_event import RawEvent
from database.models.thesis_change import ThesisChange


class ThesisChangeRepository:
    """Persistence-only access to versioned Thesis Change artifacts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, thesis_change_id: UUID) -> ThesisChangeView | None:
        entity = self._session.get(ThesisChange, thesis_change_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_input_identity(self, input_identity: str) -> ThesisChangeView | None:
        statement = select(ThesisChange).where(ThesisChange.input_identity == input_identity)
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def add_if_absent(self, command: ThesisChangeCreate) -> ThesisChangeView:
        existing = self.get_by_input_identity(command.input_identity)
        if existing is not None:
            return existing

        entity = ThesisChange(
            investor_id=command.investor_id,
            asset_id=command.asset_id,
            previous_opinion_id=command.previous_opinion_id,
            current_opinion_id=command.current_opinion_id,
            previous_event_id=command.previous_event_id,
            current_event_id=command.current_event_id,
            effective_time=command.effective_time,
            change_type=command.change_type,
            confidence=command.confidence,
            summary=command.summary,
            evidence=list(command.evidence),
            opinion_analysis_version=command.opinion_analysis_version,
            comparison_version=command.comparison_version,
            calculated_at=command.calculated_at,
            input_identity=command.input_identity,
        )
        try:
            with self._session.begin_nested():
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_input_identity(command.input_identity)
            if existing is None:
                raise
            return existing
        return self._to_view(entity)

    def list_by_pair(
        self,
        investor_id: UUID,
        asset_id: UUID,
        comparison_version: str | None = None,
    ) -> list[ThesisChangeView]:
        statement = select(ThesisChange).where(
            ThesisChange.investor_id == investor_id,
            ThesisChange.asset_id == asset_id,
        )
        if comparison_version is not None:
            statement = statement.where(ThesisChange.comparison_version == comparison_version)
        statement = statement.order_by(ThesisChange.effective_time, ThesisChange.id)
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_effective(
        self,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]:
        """Return artifacts matching the current fact-time predecessor timeline.

        An artifact remains append-only even when a late historical Opinion changes
        the predecessor for the same current Opinion. Only the artifact whose
        previous/current identities match the active timeline is effective.
        """

        expected_predecessors = self._expected_predecessors(policy, as_of=as_of)

        statement = (
            select(ThesisChange)
            .join(Opinion, ThesisChange.current_opinion_id == Opinion.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .join(RawEvent, ThesisChange.current_event_id == RawEvent.id)
            .where(
                EventAnalysis.analysis_version == policy.active_analysis_version,
                EventAnalysis.status.in_(
                    [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                ),
                ThesisChange.investor_id == Opinion.investor_id,
                ThesisChange.asset_id == Opinion.asset_id,
                ThesisChange.current_event_id == Opinion.event_id,
                ThesisChange.opinion_analysis_version == policy.active_analysis_version,
            )
        )
        if comparison_version is not None:
            statement = statement.where(ThesisChange.comparison_version == comparison_version)
        if as_of is not None:
            statement = statement.where(RawEvent.published_time <= as_of)
        statement = statement.order_by(RawEvent.published_time, RawEvent.id, ThesisChange.id)

        effective: list[ThesisChangeView] = []
        for entity in self._session.scalars(statement):
            expected = expected_predecessors.get(entity.current_opinion_id)
            if expected is None:
                continue
            expected_previous_opinion_id, expected_previous_event_id = expected
            if (
                entity.previous_opinion_id != expected_previous_opinion_id
                or entity.previous_event_id != expected_previous_event_id
            ):
                continue
            effective.append(self._to_view(entity))
        return effective

    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]:
        """Return effective Thesis Change artifacts for one investor."""

        return [
            artifact
            for artifact in self.list_effective(
                policy,
                comparison_version,
                as_of=as_of,
            )
            if artifact.investor_id == investor_id
        ]

    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]:
        """Return effective ThesisChange artifacts for one Asset."""

        return [
            artifact
            for artifact in self.list_effective(
                policy,
                comparison_version,
                as_of=as_of,
            )
            if artifact.asset_id == asset_id
        ]

    def _expected_predecessors(
        self,
        policy: EffectiveAnalysisPolicy,
        *,
        as_of: datetime | None = None,
    ) -> dict[UUID, tuple[UUID | None, UUID | None]]:
        """Build current predecessor identities from the effective fact timeline."""

        statement = (
            select(
                Opinion.investor_id,
                Opinion.asset_id,
                Opinion.id,
                Opinion.event_id,
                RawEvent.published_time,
                RawEvent.id,
            )
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(*self._effective_analysis_predicates(policy))
        )
        if as_of is not None:
            statement = statement.where(RawEvent.published_time <= as_of)
        statement = statement.order_by(
            Opinion.investor_id,
            Opinion.asset_id,
            RawEvent.published_time,
            RawEvent.id,
            Opinion.id,
        )

        expected: dict[UUID, tuple[UUID | None, UUID | None]] = {}
        previous_by_pair: dict[tuple[UUID, UUID], tuple[UUID, UUID]] = {}
        for row in self._session.execute(statement):
            investor_id, asset_id, opinion_id, event_id = row[0], row[1], row[2], row[3]
            pair = (investor_id, asset_id)
            previous = previous_by_pair.get(pair)
            expected[opinion_id] = previous or (None, None)
            previous_by_pair[pair] = (opinion_id, event_id)
        return expected

    @staticmethod
    def _effective_analysis_predicates(policy: EffectiveAnalysisPolicy) -> tuple[object, ...]:
        return (
            EventAnalysis.analysis_version == policy.active_analysis_version,
            EventAnalysis.status.in_(
                [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
            ),
        )

    @classmethod
    def _to_view(cls, entity: ThesisChange) -> ThesisChangeView:
        return ThesisChangeView(
            id=entity.id,
            investor_id=entity.investor_id,
            asset_id=entity.asset_id,
            previous_opinion_id=entity.previous_opinion_id,
            current_opinion_id=entity.current_opinion_id,
            previous_event_id=entity.previous_event_id,
            current_event_id=entity.current_event_id,
            effective_time=cls._as_utc(entity.effective_time),
            change_type=entity.change_type,
            confidence=entity.confidence,
            summary=entity.summary,
            evidence=tuple(entity.evidence),
            opinion_analysis_version=entity.opinion_analysis_version,
            comparison_version=entity.comparison_version,
            calculated_at=cls._as_utc(entity.calculated_at),
            input_identity=entity.input_identity,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
