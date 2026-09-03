from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import PortfolioSnapshotBatchDTO, PortfolioSnapshotBatchView, PositionSnapshotView
from database.models.portfolio_snapshot import PortfolioSnapshotBatch
from database.repositories.position_snapshots import PositionSnapshotRepository


class PortfolioSnapshotBatchRepository:
    """Persistence adapter for one parent fact per observed portfolio snapshot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, batch: PortfolioSnapshotBatchDTO) -> PortfolioSnapshotBatchView:
        entity = PortfolioSnapshotBatch(
            portfolio_id=batch.portfolio_id,
            snapshot_time=batch.snapshot_time,
            source=batch.source,
            external_id=batch.external_id,
            created_at=batch.created_at,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def get(self, batch_id: UUID) -> PortfolioSnapshotBatchView | None:
        entity = self._session.get(PortfolioSnapshotBatch, batch_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_identity(
        self,
        portfolio_id: UUID,
        snapshot_time: datetime,
        source: str,
        external_id: str,
    ) -> PortfolioSnapshotBatchView | None:
        statement = select(PortfolioSnapshotBatch).where(
            PortfolioSnapshotBatch.portfolio_id == portfolio_id,
            PortfolioSnapshotBatch.snapshot_time == self._as_utc(snapshot_time),
            PortfolioSnapshotBatch.source == source.strip().lower(),
            PortfolioSnapshotBatch.external_id == external_id.strip(),
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def get_or_create(
        self,
        batch: PortfolioSnapshotBatchDTO,
    ) -> tuple[PortfolioSnapshotBatchView, bool]:
        existing = self.get_by_identity(
            batch.portfolio_id,
            batch.snapshot_time,
            batch.source,
            batch.external_id,
        )
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = PortfolioSnapshotBatch(
                    portfolio_id=batch.portfolio_id,
                    snapshot_time=batch.snapshot_time,
                    source=batch.source,
                    external_id=batch.external_id,
                    created_at=batch.created_at,
                )
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_identity(
                batch.portfolio_id,
                batch.snapshot_time,
                batch.source,
                batch.external_id,
            )
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def list_positions(self, snapshot_batch_id: UUID) -> list[PositionSnapshotView]:
        return PositionSnapshotRepository(self._session).list_by_snapshot_batch(snapshot_batch_id)

    @classmethod
    def _to_view(cls, entity: PortfolioSnapshotBatch) -> PortfolioSnapshotBatchView:
        return PortfolioSnapshotBatchView(
            id=entity.id,
            portfolio_id=entity.portfolio_id,
            snapshot_time=cls._as_utc(entity.snapshot_time),
            source=entity.source,
            external_id=entity.external_id,
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
