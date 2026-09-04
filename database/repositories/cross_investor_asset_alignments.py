from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    CrossInvestorAssetAlignmentCreate,
    CrossInvestorAssetAlignmentView,
)
from database.models.cross_investor_asset_alignment import CrossInvestorAssetAlignment


class CrossInvestorAssetAlignmentRepository:
    """Persistence adapter for immutable coverage/alignment artifacts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        alignment: CrossInvestorAssetAlignmentCreate,
    ) -> CrossInvestorAssetAlignmentView:
        entity = self._build_entity(alignment)
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def add_if_absent(
        self,
        alignment: CrossInvestorAssetAlignmentCreate,
    ) -> tuple[CrossInvestorAssetAlignmentView, bool]:
        existing = self.get_by_input_identity(alignment.input_identity)
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = self._build_entity(alignment)
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_input_identity(alignment.input_identity)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def get(self, alignment_id: UUID) -> CrossInvestorAssetAlignmentView | None:
        entity = self._session.get(CrossInvestorAssetAlignment, alignment_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_input_identity(self, input_identity: str) -> CrossInvestorAssetAlignmentView | None:
        statement = select(CrossInvestorAssetAlignment).where(
            CrossInvestorAssetAlignment.input_identity == input_identity
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def list_by_asset(self, asset_id: UUID) -> list[CrossInvestorAssetAlignmentView]:
        statement = (
            select(CrossInvestorAssetAlignment)
            .where(CrossInvestorAssetAlignment.asset_id == asset_id)
            .order_by(
                CrossInvestorAssetAlignment.created_at,
                CrossInvestorAssetAlignment.alignment_policy_version,
                CrossInvestorAssetAlignment.id,
            )
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_by_source_snapshot(
        self,
        source_snapshot_id: UUID,
    ) -> list[CrossInvestorAssetAlignmentView]:
        statement = (
            select(CrossInvestorAssetAlignment)
            .where(CrossInvestorAssetAlignment.source_snapshot_id == source_snapshot_id)
            .order_by(
                CrossInvestorAssetAlignment.alignment_policy_version,
                CrossInvestorAssetAlignment.created_at,
                CrossInvestorAssetAlignment.id,
            )
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @staticmethod
    def _build_entity(
        alignment: CrossInvestorAssetAlignmentCreate,
    ) -> CrossInvestorAssetAlignment:
        return CrossInvestorAssetAlignment(
            asset_id=alignment.asset_id,
            source_snapshot_id=alignment.source_snapshot_id,
            opinion_coverage_state=alignment.opinion_coverage_state,
            directional_alignment_state=alignment.directional_alignment_state,
            alignment_policy_version=alignment.alignment_policy_version,
            input_identity=alignment.input_identity,
            calculated_at=alignment.calculated_at,
            created_at=alignment.created_at,
        )

    @classmethod
    def _to_view(
        cls,
        entity: CrossInvestorAssetAlignment,
    ) -> CrossInvestorAssetAlignmentView:
        return CrossInvestorAssetAlignmentView(
            id=entity.id,
            asset_id=entity.asset_id,
            source_snapshot_id=entity.source_snapshot_id,
            opinion_coverage_state=entity.opinion_coverage_state,
            directional_alignment_state=entity.directional_alignment_state,
            alignment_policy_version=entity.alignment_policy_version,
            input_identity=entity.input_identity,
            calculated_at=cls._as_utc(entity.calculated_at),
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["CrossInvestorAssetAlignmentRepository"]
