from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import PositionSnapshotDTO, PositionSnapshotView
from database.models.portfolio_snapshot import PortfolioSnapshotBatch
from database.models.position_snapshot import PositionSnapshot


class PositionSnapshotRepository:
    """Persistence adapter for observed portfolio position snapshots."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, snapshot: PositionSnapshotDTO) -> PositionSnapshotView:
        self._validate_batch_provenance(snapshot)
        entity = PositionSnapshot(
            portfolio_id=snapshot.portfolio_id,
            snapshot_batch_id=snapshot.snapshot_batch_id,
            asset_id=snapshot.asset_id,
            asset_reference_id=snapshot.asset_reference_id,
            weight=snapshot.weight,
            snapshot_time=snapshot.snapshot_time,
            source_type=snapshot.source_type,
            source_reference=snapshot.source_reference,
            created_at=snapshot.created_at,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def add_if_absent(self, snapshot: PositionSnapshotDTO) -> tuple[PositionSnapshotView, bool]:
        """Insert one position or reuse its database-protected identity."""

        self._validate_batch_provenance(snapshot)
        existing = self.get_by_identity(
            snapshot.snapshot_batch_id,
            asset_id=snapshot.asset_id,
            asset_reference_id=snapshot.asset_reference_id,
        )
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = PositionSnapshot(
                    portfolio_id=snapshot.portfolio_id,
                    snapshot_batch_id=snapshot.snapshot_batch_id,
                    asset_id=snapshot.asset_id,
                    asset_reference_id=snapshot.asset_reference_id,
                    weight=snapshot.weight,
                    snapshot_time=snapshot.snapshot_time,
                    source_type=snapshot.source_type,
                    source_reference=snapshot.source_reference,
                    created_at=snapshot.created_at,
                )
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_identity(
                snapshot.snapshot_batch_id,
                asset_id=snapshot.asset_id,
                asset_reference_id=snapshot.asset_reference_id,
            )
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def _validate_batch_provenance(self, snapshot: PositionSnapshotDTO) -> None:
        batch = self._session.get(PortfolioSnapshotBatch, snapshot.snapshot_batch_id)
        if batch is None:
            raise ValueError("snapshot_batch_id does not reference a PortfolioSnapshotBatch")
        if batch.portfolio_id != snapshot.portfolio_id:
            raise ValueError("snapshot batch must belong to the snapshot portfolio")
        if self._as_utc(batch.snapshot_time) != self._as_utc(snapshot.snapshot_time):
            raise ValueError("snapshot_time must equal the parent batch snapshot_time")

    def get(self, snapshot_id: UUID) -> PositionSnapshotView | None:
        entity = self._session.get(PositionSnapshot, snapshot_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_identity(
        self,
        snapshot_batch_id: UUID,
        *,
        asset_id: UUID | None = None,
        asset_reference_id: UUID | None = None,
    ) -> PositionSnapshotView | None:
        """Find one position within a portfolio snapshot by its asset identity."""

        if (asset_id is None) == (asset_reference_id is None):
            raise ValueError("exactly one asset identity is required")
        statement = select(PositionSnapshot).where(
            PositionSnapshot.snapshot_batch_id == snapshot_batch_id,
        )
        if asset_id is not None:
            statement = statement.where(PositionSnapshot.asset_id == asset_id)
        else:
            statement = statement.where(PositionSnapshot.asset_reference_id == asset_reference_id)
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def list_by_snapshot_batch(self, snapshot_batch_id: UUID) -> list[PositionSnapshotView]:
        statement = (
            select(PositionSnapshot)
            .where(PositionSnapshot.snapshot_batch_id == snapshot_batch_id)
            .order_by(PositionSnapshot.id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list(
        self,
        *,
        portfolio_id: UUID | None = None,
        snapshot_batch_id: UUID | None = None,
        asset_id: UUID | None = None,
    ) -> list[PositionSnapshotView]:
        statement = select(PositionSnapshot)
        if portfolio_id is not None:
            statement = statement.where(PositionSnapshot.portfolio_id == portfolio_id)
        if snapshot_batch_id is not None:
            statement = statement.where(PositionSnapshot.snapshot_batch_id == snapshot_batch_id)
        if asset_id is not None:
            statement = statement.where(PositionSnapshot.asset_id == asset_id)
        statement = statement.order_by(
            PositionSnapshot.snapshot_time,
            PositionSnapshot.id,
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @classmethod
    def _to_view(cls, entity: PositionSnapshot) -> PositionSnapshotView:
        return PositionSnapshotView(
            id=entity.id,
            portfolio_id=entity.portfolio_id,
            snapshot_batch_id=entity.snapshot_batch_id,
            asset_id=entity.asset_id,
            asset_reference_id=entity.asset_reference_id,
            weight=entity.weight,
            snapshot_time=cls._as_utc(entity.snapshot_time),
            source_type=entity.source_type,
            source_reference=entity.source_reference,
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
