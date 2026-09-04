"""Application workflow for importing one external portfolio snapshot."""

import json
from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from contracts import (
    AssetReference,
    AssetResolutionResult,
    AssetResolutionStatus,
    PortfolioDTO,
    PortfolioPositionInput,
    PortfolioSnapshotBatchDTO,
    PortfolioSnapshotBatchView,
    PortfolioSnapshotImportCommand,
    PortfolioSnapshotImportResult,
    PortfolioView,
    PositionSnapshotDTO,
    PositionSnapshotView,
    normalize_asset_reference,
)


class AssetResolverPort(Protocol):
    def resolve(self, reference: AssetReference) -> AssetResolutionResult: ...


class PortfolioWriter(Protocol):
    def get_by_identity(self, source: str, external_id: str) -> PortfolioView | None: ...

    def upsert(self, portfolio: PortfolioDTO) -> PortfolioView: ...


class PositionSnapshotWriter(Protocol):
    def get_by_identity(
        self,
        snapshot_batch_id: UUID,
        *,
        asset_id: UUID | None = None,
        asset_reference_id: UUID | None = None,
    ) -> PositionSnapshotView | None: ...

    def create(self, snapshot: PositionSnapshotDTO) -> PositionSnapshotView: ...

    def add_if_absent(self, snapshot: PositionSnapshotDTO) -> tuple[PositionSnapshotView, bool]: ...


class PortfolioSnapshotBatchWriter(Protocol):
    def get_or_create(
        self,
        batch: PortfolioSnapshotBatchDTO,
    ) -> tuple[PortfolioSnapshotBatchView, bool]: ...


class PortfolioSnapshotImportUnitOfWork(Protocol):
    portfolios: PortfolioWriter
    portfolio_snapshot_batches: PortfolioSnapshotBatchWriter
    position_snapshots: PositionSnapshotWriter
    asset_resolver: AssetResolverPort

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


PortfolioSnapshotImportUnitOfWorkFactory = Callable[[], PortfolioSnapshotImportUnitOfWork]


class PortfolioSnapshotImportService:
    """Resolve and persist one externally supplied snapshot without AI or collectors."""

    def __init__(self, unit_of_work_factory: PortfolioSnapshotImportUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def import_snapshot(
        self,
        command: PortfolioSnapshotImportCommand,
    ) -> PortfolioSnapshotImportResult:
        with self._unit_of_work_factory() as unit_of_work:
            existing_portfolio = unit_of_work.portfolios.get_by_identity(
                command.source,
                command.external_id,
            )
            portfolio = unit_of_work.portfolios.upsert(
                PortfolioDTO(
                    investor_id=command.investor_id,
                    source=command.source,
                    external_id=command.external_id,
                    name=command.portfolio_name,
                )
            )

            portfolio_id = portfolio.id
            batch, batch_created = unit_of_work.portfolio_snapshot_batches.get_or_create(
                PortfolioSnapshotBatchDTO(
                    portfolio_id=portfolio_id,
                    snapshot_time=command.snapshot_time,
                    source=command.source,
                    external_id=command.external_id,
                    completeness=command.completeness,
                )
            )
            snapshot_batch_id = batch.id
            snapshot_ids: list[UUID] = []
            created_count = 0
            reused_count = 0
            resolved_count = 0
            unresolved_count = 0
            for position_index, position in enumerate(command.positions):
                reference = AssetReference(
                    name_hint=position.asset_name,
                    symbol_hint=position.symbol,
                    market_hint=position.market,
                )
                resolution = unit_of_work.asset_resolver.resolve(reference)
                asset_id, asset_reference_id = self._identity_for_resolution(
                    reference,
                    resolution,
                )
                if asset_id is not None:
                    resolved_count += 1
                else:
                    unresolved_count += 1

                snapshot, created = unit_of_work.position_snapshots.add_if_absent(
                    PositionSnapshotDTO(
                        portfolio_id=portfolio_id,
                        snapshot_batch_id=snapshot_batch_id,
                        asset_id=asset_id,
                        asset_reference_id=asset_reference_id,
                        weight=position.weight,
                        snapshot_time=command.snapshot_time,
                        source_type=command.source,
                        source_reference=self._source_reference(
                            command,
                            position,
                            reference,
                            position_index,
                        ),
                    )
                )
                snapshot_ids.append(snapshot.id)
                if created:
                    created_count += 1
                else:
                    reused_count += 1

            unit_of_work.commit()

        return PortfolioSnapshotImportResult(
            portfolio_id=portfolio_id,
            snapshot_batch_id=snapshot_batch_id,
            portfolio_created=existing_portfolio is None,
            batch_created=batch_created,
            batch_reused=not batch_created,
            position_snapshot_ids=tuple(snapshot_ids),
            created_count=created_count,
            reused_count=reused_count,
            resolved_count=resolved_count,
            unresolved_count=unresolved_count,
        )

    def import_(self, command: PortfolioSnapshotImportCommand) -> PortfolioSnapshotImportResult:
        """Compatibility alias for callers that avoid the descriptive method name."""

        return self.import_snapshot(command)

    @staticmethod
    def _identity_for_resolution(
        reference: AssetReference,
        resolution: AssetResolutionResult,
    ) -> tuple[UUID | None, UUID | None]:
        if resolution.status is AssetResolutionStatus.RESOLVED:
            if resolution.asset_id is None:
                raise ValueError("resolved AssetResolutionResult must include asset_id")
            return resolution.asset_id, None
        return None, PortfolioSnapshotImportService._asset_reference_id(reference)

    @staticmethod
    def _asset_reference_id(reference: AssetReference) -> UUID:
        normalized_reference = normalize_asset_reference(reference)
        normalized = {
            "name_hint": normalized_reference.name,
            "symbol_hint": normalized_reference.symbol,
            "market_hint": normalized_reference.market,
        }
        canonical = json.dumps(
            normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return uuid5(NAMESPACE_URL, f"portfolio-asset-reference:{canonical}")

    @staticmethod
    def _source_reference(
        command: PortfolioSnapshotImportCommand,
        position: PortfolioPositionInput,
        reference: AssetReference,
        position_index: int,
    ) -> str:
        if position.source_reference is not None:
            return position.source_reference
        identity = json.dumps(
            {
                "name_hint": reference.name_hint,
                "symbol_hint": reference.symbol_hint,
                "market_hint": reference.market_hint,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return (
            f"{command.source}:{command.external_id}:{command.snapshot_time.isoformat()}"
            f":position:{position_index}:{identity}"
        )


__all__ = ["PortfolioSnapshotImportService"]
