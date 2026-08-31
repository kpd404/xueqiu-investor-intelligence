from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    STATE_POLICY_VERSION,
    EffectiveAnalysisPolicy,
    InvestorAssetStateSnapshot,
    OpinionTimelineEntry,
    StateChangeCreate,
    StateUpdateResult,
)
from intelligence.policies.state_reducer import reduce_investor_asset_state


class OpinionNotFoundError(LookupError):
    pass


class StateEntity(Protocol):
    id: UUID


class OpinionEntity(Protocol):
    opinion_id: UUID


class OpinionHistoryReader(Protocol):
    def get_effective_view(
        self,
        opinion_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> OpinionTimelineEntry | None: ...

    def list_effective_timeline(
        self,
        investor_id: UUID,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> list[OpinionTimelineEntry]: ...


class StateWriter(Protocol):
    def get_for_update(self, investor_id: UUID, asset_id: UUID) -> StateEntity | None: ...

    def upsert(
        self,
        snapshot: InvestorAssetStateSnapshot,
        current: StateEntity | None = None,
    ) -> StateEntity: ...

    def to_snapshot(self, state: StateEntity) -> InvestorAssetStateSnapshot: ...


class StateChangeWriter(Protocol):
    def add_if_absent(self, command: StateChangeCreate) -> object: ...


class StateUnitOfWork(Protocol):
    opinions: OpinionHistoryReader
    states: StateWriter
    state_changes: StateChangeWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


StateUnitOfWorkFactory = Callable[[], StateUnitOfWork]


def utc_now() -> datetime:
    return datetime.now(UTC)


class StateUpdateService:
    def __init__(
        self,
        unit_of_work_factory: StateUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        state_policy_version: str = STATE_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._state_policy_version = state_policy_version

    def update(self, opinion_id: UUID) -> StateUpdateResult:
        with self._unit_of_work_factory() as unit_of_work:
            triggering_opinion = unit_of_work.opinions.get_effective_view(
                opinion_id,
                self._effective_analysis_policy,
            )
            if triggering_opinion is None:
                raise OpinionNotFoundError(f"opinion not found: {opinion_id}")

            current = unit_of_work.states.get_for_update(
                triggering_opinion.investor_id,
                triggering_opinion.asset_id,
            )
            before = unit_of_work.states.to_snapshot(current) if current is not None else None
            history = unit_of_work.opinions.list_effective_timeline(
                triggering_opinion.investor_id,
                triggering_opinion.asset_id,
                self._effective_analysis_policy,
            )
            reduction = reduce_investor_asset_state(history, before)

            if reduction.projection_changed:
                state = unit_of_work.states.upsert(reduction.after, current)
            else:
                if current is None:
                    raise RuntimeError("unchanged reduction requires an existing state")
                state = current

            state_change_id: UUID | None = None
            if reduction.material_change:
                if reduction.after.last_activity_time is None:
                    raise RuntimeError("material state change requires an activity time")
                state_change = unit_of_work.state_changes.add_if_absent(
                    StateChangeCreate(
                        investor_id=reduction.after.investor_id,
                        asset_id=reduction.after.asset_id,
                        transition_type=reduction.transition.value,
                        effective_time=reduction.after.last_activity_time,
                        calculated_at=utc_now(),
                        before=(
                            reduction.before.model_dump(mode="json")
                            if reduction.before is not None
                            else None
                        ),
                        after=reduction.after.model_dump(mode="json"),
                        triggering_opinion_id=opinion_id,
                        source_event_ids=reduction.source_event_ids,
                        state_policy_version=self._state_policy_version,
                    )
                )
                state_change_id = state_change.id
            unit_of_work.commit()

        return StateUpdateResult(
            state_id=state.id,
            projection_changed=reduction.projection_changed,
            material_change=reduction.material_change,
            before=reduction.before,
            after=reduction.after,
            transition=reduction.transition,
            applied_opinion_ids=reduction.applied_opinion_ids,
            source_event_ids=reduction.source_event_ids,
            state_change_id=state_change_id,
        )
