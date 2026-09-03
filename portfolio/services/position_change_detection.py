"""Deterministic comparison of two Portfolio Snapshot batches."""

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    PortfolioActionDTO,
    PortfolioActionType,
    PortfolioActionView,
    PortfolioSnapshotBatchView,
    PositionChangeDetectionResult,
    PositionSnapshotView,
)


class SnapshotBatchReader(Protocol):
    def get(self, batch_id: UUID) -> PortfolioSnapshotBatchView | None: ...

    def list_positions(self, snapshot_batch_id: UUID) -> list[PositionSnapshotView]: ...


class PortfolioActionWriter(Protocol):
    def add_if_absent(self, action: PortfolioActionDTO) -> tuple[PortfolioActionView, bool]: ...


class PositionChangeUnitOfWork(Protocol):
    portfolio_snapshot_batches: SnapshotBatchReader
    portfolio_actions: PortfolioActionWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


PositionChangeUnitOfWorkFactory = Callable[[], PositionChangeUnitOfWork]


class PositionChangeDetectionService:
    """Compare two batches as facts; never infer trading intent."""

    def __init__(self, unit_of_work_factory: PositionChangeUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def detect(
        self,
        previous_snapshot_batch_id: UUID,
        current_snapshot_batch_id: UUID,
    ) -> PositionChangeDetectionResult:
        with self._unit_of_work_factory() as unit_of_work:
            previous_batch = unit_of_work.portfolio_snapshot_batches.get(previous_snapshot_batch_id)
            current_batch = unit_of_work.portfolio_snapshot_batches.get(current_snapshot_batch_id)
            if previous_batch is None:
                raise LookupError(
                    f"previous snapshot batch not found: {previous_snapshot_batch_id}"
                )
            if current_batch is None:
                raise LookupError(f"current snapshot batch not found: {current_snapshot_batch_id}")
            if previous_batch.portfolio_id != current_batch.portfolio_id:
                raise ValueError("snapshot batches must belong to the same portfolio")
            if current_batch.snapshot_time < previous_batch.snapshot_time:
                raise ValueError("current snapshot batch must not precede previous batch")

            previous_positions = self._index_positions(
                unit_of_work.portfolio_snapshot_batches.list_positions(previous_batch.id)
            )
            current_positions = self._index_positions(
                unit_of_work.portfolio_snapshot_batches.list_positions(current_batch.id)
            )
            calculated_at = datetime.now(UTC)
            action_ids: list[UUID] = []
            created_count = 0
            reused_count = 0
            for identity in sorted(
                set(previous_positions) | set(current_positions),
                key=lambda value: (value[0], value[1].int),
            ):
                previous = previous_positions.get(identity)
                current = current_positions.get(identity)
                action_type = self._action_type(previous, current)
                representative = current or previous
                assert representative is not None
                action = PortfolioActionDTO(
                    portfolio_id=current_batch.portfolio_id,
                    asset_id=representative.asset_id,
                    asset_reference_id=representative.asset_reference_id,
                    previous_snapshot_batch_id=previous_batch.id,
                    current_snapshot_batch_id=current_batch.id,
                    previous_position_snapshot_id=previous.id if previous is not None else None,
                    current_position_snapshot_id=current.id if current is not None else None,
                    action_type=action_type,
                    effective_time=current_batch.snapshot_time,
                    calculated_at=calculated_at,
                )
                persisted, created = unit_of_work.portfolio_actions.add_if_absent(action)
                action_ids.append(persisted.id)
                if created:
                    created_count += 1
                else:
                    reused_count += 1

            unit_of_work.commit()

        return PositionChangeDetectionResult(
            portfolio_id=current_batch.portfolio_id,
            previous_snapshot_batch_id=previous_batch.id,
            current_snapshot_batch_id=current_batch.id,
            action_ids=tuple(action_ids),
            created_count=created_count,
            reused_count=reused_count,
        )

    def process(
        self,
        previous_snapshot_batch_id: UUID,
        current_snapshot_batch_id: UUID,
    ) -> PositionChangeDetectionResult:
        """Compatibility alias for application callers using process terminology."""

        return self.detect(previous_snapshot_batch_id, current_snapshot_batch_id)

    @staticmethod
    def _index_positions(
        positions: list[PositionSnapshotView],
    ) -> dict[tuple[str, UUID], PositionSnapshotView]:
        indexed: dict[tuple[str, UUID], PositionSnapshotView] = {}
        for position in positions:
            if position.asset_id is not None:
                identity = ("asset", position.asset_id)
            elif position.asset_reference_id is not None:
                identity = ("reference", position.asset_reference_id)
            else:
                raise ValueError(f"position snapshot has no asset identity: {position.id}")
            if identity in indexed:
                raise ValueError(f"duplicate position identity in snapshot batch: {identity[1]}")
            indexed[identity] = position
        return indexed

    @staticmethod
    def _action_type(
        previous: PositionSnapshotView | None,
        current: PositionSnapshotView | None,
    ) -> PortfolioActionType:
        if previous is None:
            return PortfolioActionType.POSITION_ADDED
        if current is None:
            return PortfolioActionType.POSITION_REMOVED
        # A missing weight cannot prove an increase or decrease in this V0.
        if previous.weight is None or current.weight is None or current.weight == previous.weight:
            return PortfolioActionType.POSITION_UNCHANGED
        if current.weight > previous.weight:
            return PortfolioActionType.POSITION_INCREASED
        return PortfolioActionType.POSITION_DECREASED


__all__ = ["PositionChangeDetectionService"]
