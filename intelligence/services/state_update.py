from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    InvestorAssetStateSnapshot,
    OpinionTimelineEntry,
    StateUpdateResult,
)
from intelligence.policies.state_reducer import reduce_investor_asset_state


class OpinionNotFoundError(LookupError):
    pass


class StateEntity(Protocol):
    id: UUID


class OpinionHistoryReader(Protocol):
    def get_view(self, opinion_id: UUID) -> OpinionTimelineEntry | None: ...

    def list_timeline(self, investor_id: UUID, asset_id: UUID) -> list[OpinionTimelineEntry]: ...


class StateWriter(Protocol):
    def get_for_update(self, investor_id: UUID, asset_id: UUID) -> StateEntity | None: ...

    def upsert(
        self,
        snapshot: InvestorAssetStateSnapshot,
        current: StateEntity | None = None,
    ) -> StateEntity: ...

    def to_snapshot(self, state: StateEntity) -> InvestorAssetStateSnapshot: ...


class StateUnitOfWork(Protocol):
    opinions: OpinionHistoryReader
    states: StateWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


StateUnitOfWorkFactory = Callable[[], StateUnitOfWork]


class StateUpdateService:
    def __init__(self, unit_of_work_factory: StateUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def update(self, opinion_id: UUID) -> StateUpdateResult:
        with self._unit_of_work_factory() as unit_of_work:
            triggering_opinion = unit_of_work.opinions.get_view(opinion_id)
            if triggering_opinion is None:
                raise OpinionNotFoundError(f"opinion not found: {opinion_id}")

            current = unit_of_work.states.get_for_update(
                triggering_opinion.investor_id,
                triggering_opinion.asset_id,
            )
            before = unit_of_work.states.to_snapshot(current) if current is not None else None
            history = unit_of_work.opinions.list_timeline(
                triggering_opinion.investor_id,
                triggering_opinion.asset_id,
            )
            reduction = reduce_investor_asset_state(history, before)

            if reduction.changed:
                state = unit_of_work.states.upsert(reduction.after, current)
            else:
                if current is None:
                    raise RuntimeError("unchanged reduction requires an existing state")
                state = current
            unit_of_work.commit()

        return StateUpdateResult(
            state_id=state.id,
            changed=reduction.changed,
            before=reduction.before,
            after=reduction.after,
            transition=reduction.transition,
            applied_opinion_ids=reduction.applied_opinion_ids,
            source_event_ids=reduction.source_event_ids,
        )
