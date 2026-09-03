import json
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    EffectiveAnalysisPolicy,
    RawEventView,
    ThesisChangeCreate,
    ThesisChangeResult,
    ThesisChangeType,
    ThesisChangeView,
    ThesisComparator,
    ThesisComparisonInput,
    ThesisComparisonResult,
    ThesisComparisonSpec,
    ThesisOpinionView,
    current_author_text,
)


class ThesisOpinionReader(Protocol):
    def get_effective_comparison_view(
        self,
        opinion_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> ThesisOpinionView | None: ...

    def list_effective_comparison_timeline(
        self,
        investor_id: UUID,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisOpinionView]: ...


class ThesisRawEventReader(Protocol):
    def get_view(self, event_id: UUID) -> RawEventView | None: ...


class ThesisChangeWriter(Protocol):
    def get_by_input_identity(self, input_identity: str) -> ThesisChangeView | None: ...

    def add_if_absent(self, command: ThesisChangeCreate) -> ThesisChangeView: ...


class ThesisChangeUnitOfWork(Protocol):
    opinions: ThesisOpinionReader
    raw_events: ThesisRawEventReader
    thesis_changes: ThesisChangeWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


ThesisChangeUnitOfWorkFactory = Callable[[], ThesisChangeUnitOfWork]


class ThesisOpinionNotFoundError(LookupError):
    pass


class ThesisEventNotFoundError(LookupError):
    pass


class ThesisChangeService:
    """Compare each effective Opinion with its immediate fact-time predecessor."""

    def __init__(
        self,
        unit_of_work_factory: ThesisChangeUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        comparator: ThesisComparator,
        comparison_spec: ThesisComparisonSpec | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._comparator = comparator
        if comparison_spec is not None and comparison_spec != comparator.comparison_spec:
            raise ValueError("comparison_spec must match comparator.comparison_spec")
        self._comparison_spec = comparison_spec or comparator.comparison_spec

    async def process(
        self,
        current_opinion_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> ThesisChangeResult:
        normalized_as_of = self._normalize_as_of(as_of)
        with self._unit_of_work_factory() as read_unit_of_work:
            current = read_unit_of_work.opinions.get_effective_comparison_view(
                current_opinion_id,
                self._effective_analysis_policy,
            )
            if current is None:
                raise ThesisOpinionNotFoundError(
                    f"effective Opinion not found: {current_opinion_id}"
                )
            if normalized_as_of is not None and current.published_time > normalized_as_of:
                raise ThesisOpinionNotFoundError(
                    f"Opinion is after requested as_of: {current_opinion_id}"
                )

            timeline = read_unit_of_work.opinions.list_effective_comparison_timeline(
                current.investor_id,
                current.asset_id,
                self._effective_analysis_policy,
                as_of=normalized_as_of,
            )
            current_index = next(
                (
                    index
                    for index, candidate in enumerate(timeline)
                    if candidate.opinion_id == current_opinion_id
                ),
                None,
            )
            if current_index is None:
                raise ThesisOpinionNotFoundError(
                    f"Opinion is not present in effective timeline: {current_opinion_id}"
                )
            previous = timeline[current_index - 1] if current_index > 0 else None

            current_event = read_unit_of_work.raw_events.get_view(current.event_id)
            if current_event is None:
                raise ThesisEventNotFoundError(f"raw event not found: {current.event_id}")
            previous_event = (
                read_unit_of_work.raw_events.get_view(previous.event_id)
                if previous is not None
                else None
            )
            if previous is not None and previous_event is None:
                raise ThesisEventNotFoundError(f"raw event not found: {previous.event_id}")

            comparison_input = self._build_input(
                current=current,
                current_event=current_event,
                previous=previous,
                previous_event=previous_event,
            )
            input_identity = self._input_identity(previous, current)
            existing = read_unit_of_work.thesis_changes.get_by_input_identity(input_identity)

        if existing is not None:
            return self._result(existing, created=False)

        calculated_at = datetime.now(UTC)
        comparison = (
            self._new_thesis_result(current)
            if previous is None
            else await self._comparator.compare(comparison_input)
        )
        if previous is not None and comparison.change_type is ThesisChangeType.NEW_THESIS:
            raise ValueError("NEW_THESIS is only valid for the first effective Opinion")
        command = ThesisChangeCreate(
            investor_id=current.investor_id,
            asset_id=current.asset_id,
            previous_opinion_id=previous.opinion_id if previous is not None else None,
            current_opinion_id=current.opinion_id,
            previous_event_id=previous.event_id if previous is not None else None,
            current_event_id=current.event_id,
            effective_time=current.published_time,
            change_type=comparison.change_type,
            confidence=comparison.confidence,
            summary=comparison.summary,
            evidence=comparison.evidence,
            opinion_analysis_version=current.analysis_version,
            comparison_version=self._comparison_spec.comparison_version,
            calculated_at=calculated_at,
            input_identity=input_identity,
        )

        with self._unit_of_work_factory() as write_unit_of_work:
            existing = write_unit_of_work.thesis_changes.get_by_input_identity(input_identity)
            if existing is not None:
                artifact = existing
                created = False
            else:
                artifact = write_unit_of_work.thesis_changes.add_if_absent(command)
                created = True
            write_unit_of_work.commit()
        return self._result(artifact, created=created)

    @staticmethod
    def _normalize_as_of(as_of: datetime | None) -> datetime | None:
        if as_of is None:
            return None
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return as_of.astimezone(UTC)

    @staticmethod
    def _build_input(
        *,
        current: ThesisOpinionView,
        current_event: RawEventView,
        previous: ThesisOpinionView | None,
        previous_event: RawEventView | None,
    ) -> ThesisComparisonInput:
        current_view = current.model_copy(
            update={
                "current_author_text": current_author_text(
                    current_event.content,
                    current_event.raw_data,
                )
            }
        )
        previous_view = (
            previous.model_copy(
                update={
                    "current_author_text": current_author_text(
                        previous_event.content,
                        previous_event.raw_data,
                    )
                }
            )
            if previous is not None and previous_event is not None
            else None
        )
        return ThesisComparisonInput(
            asset_id=current.asset_id,
            asset_name=current_view.asset_name,
            market=current_view.market,
            symbol=current_view.symbol,
            previous=previous_view,
            current=current_view,
        )

    def _input_identity(
        self,
        previous: ThesisOpinionView | None,
        current: ThesisOpinionView,
    ) -> str:
        payload = {
            "comparison_version": self._comparison_spec.comparison_version,
            "current_opinion_id": str(current.opinion_id),
            "previous_opinion_id": str(previous.opinion_id) if previous is not None else "NONE",
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _new_thesis_result(current: ThesisOpinionView) -> ThesisComparisonResult:
        return ThesisComparisonResult(
            change_type=ThesisChangeType.NEW_THESIS,
            confidence=current.confidence,
            summary="First effective Opinion for this Investor × Asset.",
            evidence=("No earlier effective Opinion exists in the fact-time timeline.",),
        )

    @staticmethod
    def _result(artifact: ThesisChangeView, *, created: bool) -> ThesisChangeResult:
        return ThesisChangeResult(
            thesis_change_id=artifact.id,
            investor_id=artifact.investor_id,
            asset_id=artifact.asset_id,
            previous_opinion_id=artifact.previous_opinion_id,
            current_opinion_id=artifact.current_opinion_id,
            change_type=artifact.change_type,
            confidence=artifact.confidence,
            comparison_version=artifact.comparison_version,
            effective_time=artifact.effective_time,
            created=created,
        )
