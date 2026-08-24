from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    AssetIntelligenceSnapshot,
    InvestorAssetStateSnapshot,
    InvestorStateAggregationInput,
    OpinionTimelineEntry,
)
from intelligence.policies import aggregate_asset_intelligence, select_effective_opinions


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

    def to_snapshot(self, state: StateEntity) -> InvestorAssetStateSnapshot: ...


class OpinionEvidenceReader(Protocol):
    def list_timeline(self, investor_id: UUID, asset_id: UUID) -> list[OpinionTimelineEntry]: ...


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
    """Build a point-in-time derived snapshot without persistence or side effects."""

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

            for state in unit_of_work.states.list_by_asset(asset_id):
                investor = unit_of_work.investors.get(state.investor_id)
                if investor is None:
                    raise InvestorNotFoundError(f"investor not found: {state.investor_id}")

                state_snapshot = unit_of_work.states.to_snapshot(state)
                timeline = unit_of_work.opinions.list_timeline(state.investor_id, asset_id)
                effective = select_effective_opinions(
                    [opinion for opinion in timeline if opinion.published_time <= normalized_as_of]
                )
                source_event_ids = tuple(
                    sorted({opinion.event_id for opinion in effective}, key=lambda value: value.int)
                )
                inputs.append(
                    InvestorStateAggregationInput(
                        state_id=state.id,
                        state=state_snapshot,
                        quality_score=investor.quality_score,
                        source_event_ids=source_event_ids,
                    )
                )

        return aggregate_asset_intelligence(asset_id, normalized_as_of, inputs)
