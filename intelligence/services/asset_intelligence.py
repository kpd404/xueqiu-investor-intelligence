from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from contracts import (
    AssetIntelligenceSnapshot,
    InvestorStateAggregationInput,
    OpinionTimelineEntry,
)
from intelligence.policies import aggregate_asset_intelligence, reduce_investor_asset_state


class AssetNotFoundError(LookupError):
    pass


class InvestorNotFoundError(LookupError):
    pass


class AssetView(Protocol):
    id: UUID


class InvestorView(Protocol):
    quality_score: float | None


class StateEntity(Protocol):
    id: UUID
    investor_id: UUID
    asset_id: UUID


class AssetReader(Protocol):
    def get(self, asset_id: UUID) -> AssetView | None: ...


class InvestorReader(Protocol):
    def get(self, investor_id: UUID) -> InvestorView | None: ...


class StateReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> list[StateEntity]: ...


class OpinionEvidenceReader(Protocol):
    def list_timeline_by_asset(self, asset_id: UUID) -> list[OpinionTimelineEntry]: ...


class IntelligenceUnitOfWork(Protocol):
    assets: AssetReader
    investors: InvestorReader
    opinions: OpinionEvidenceReader
    states: StateReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


IntelligenceUnitOfWorkFactory = Callable[[], IntelligenceUnitOfWork]


class AssetIntelligenceService:
    """Build a point-in-time derived snapshot by replaying effective Opinions."""

    def __init__(self, unit_of_work_factory: IntelligenceUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def build(self, asset_id: UUID, as_of: datetime) -> AssetIntelligenceSnapshot:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        normalized_as_of = as_of.astimezone(UTC)

        inputs: list[InvestorStateAggregationInput] = []
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.assets.get(asset_id) is None:
                raise AssetNotFoundError(f"asset not found: {asset_id}")

            current_states = {
                state.investor_id: state for state in unit_of_work.states.list_by_asset(asset_id)
            }
            timelines: dict[UUID, list[OpinionTimelineEntry]] = defaultdict(list)
            for opinion in unit_of_work.opinions.list_timeline_by_asset(asset_id):
                timelines[opinion.investor_id].append(opinion)

            for investor_id, timeline in timelines.items():
                investor = unit_of_work.investors.get(investor_id)
                if investor is None:
                    raise InvestorNotFoundError(f"investor not found: {investor_id}")
                effective = [
                    opinion for opinion in timeline if opinion.published_time <= normalized_as_of
                ]
                if not effective:
                    continue
                historical_reduction = reduce_investor_asset_state(effective)
                current_state = current_states.get(investor_id)
                state_id = (
                    current_state.id
                    if current_state is not None
                    else uuid5(NAMESPACE_URL, f"historical-state:{investor_id}:{asset_id}")
                )
                source_event_ids = tuple(
                    sorted({opinion.event_id for opinion in effective}, key=lambda value: value.int)
                )
                inputs.append(
                    InvestorStateAggregationInput(
                        state_id=state_id,
                        state=historical_reduction.after,
                        quality_score=investor.quality_score,
                        source_event_ids=source_event_ids,
                    )
                )

        return aggregate_asset_intelligence(asset_id, normalized_as_of, inputs)
