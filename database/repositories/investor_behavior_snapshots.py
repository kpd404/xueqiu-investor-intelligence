"""Persistence adapter for Investor Behavior Snapshot artifacts."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import InvestorBehaviorSnapshotCreate, InvestorBehaviorSnapshotView
from database.models.investor_behavior_snapshot import InvestorBehaviorSnapshot


class InvestorBehaviorSnapshotRepository:
    """Store immutable, window-scoped behavior aggregation results."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, snapshot: InvestorBehaviorSnapshotCreate) -> InvestorBehaviorSnapshotView:
        entity = self._build_entity(snapshot)
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def add_if_absent(
        self,
        snapshot: InvestorBehaviorSnapshotCreate,
    ) -> tuple[InvestorBehaviorSnapshotView, bool]:
        """Insert a snapshot or reuse its database-protected identity."""

        existing = self.get_by_identity(
            snapshot.investor_id,
            snapshot.window_start,
            snapshot.window_end,
            snapshot.behavior_policy_version,
        )
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = self._build_entity(snapshot)
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_identity(
                snapshot.investor_id,
                snapshot.window_start,
                snapshot.window_end,
                snapshot.behavior_policy_version,
            )
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    @staticmethod
    def _build_entity(snapshot: InvestorBehaviorSnapshotCreate) -> InvestorBehaviorSnapshot:
        return InvestorBehaviorSnapshot(
            investor_id=snapshot.investor_id,
            as_of=snapshot.as_of,
            window_start=snapshot.window_start,
            window_end=snapshot.window_end,
            attention_asset_count=snapshot.attention_asset_count,
            attention_occurrence_count=snapshot.attention_occurrence_count,
            new_attention_count=snapshot.new_attention_count,
            opinion_count=snapshot.opinion_count,
            bullish_count=snapshot.bullish_count,
            bearish_count=snapshot.bearish_count,
            thesis_change_count=snapshot.thesis_change_count,
            thesis_reinforced_count=snapshot.thesis_reinforced_count,
            thesis_changed_count=snapshot.thesis_changed_count,
            portfolio_action_count=snapshot.portfolio_action_count,
            position_increased_count=snapshot.position_increased_count,
            position_decreased_count=snapshot.position_decreased_count,
            positive_alignment_count=snapshot.positive_alignment_count,
            negative_alignment_count=snapshot.negative_alignment_count,
            behavior_policy_version=snapshot.behavior_policy_version,
            calculated_at=snapshot.calculated_at,
            input_identity=snapshot.input_identity,
        )

    def get(self, snapshot_id: UUID) -> InvestorBehaviorSnapshotView | None:
        entity = self._session.get(InvestorBehaviorSnapshot, snapshot_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_identity(
        self,
        investor_id: UUID,
        window_start: datetime,
        window_end: datetime,
        behavior_policy_version: str,
    ) -> InvestorBehaviorSnapshotView | None:
        statement = select(InvestorBehaviorSnapshot).where(
            InvestorBehaviorSnapshot.investor_id == investor_id,
            InvestorBehaviorSnapshot.window_start == self._as_utc(window_start),
            InvestorBehaviorSnapshot.window_end == self._as_utc(window_end),
            InvestorBehaviorSnapshot.behavior_policy_version == behavior_policy_version,
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def list_by_investor(self, investor_id: UUID) -> list[InvestorBehaviorSnapshotView]:
        statement = (
            select(InvestorBehaviorSnapshot)
            .where(InvestorBehaviorSnapshot.investor_id == investor_id)
            .order_by(
                InvestorBehaviorSnapshot.window_end,
                InvestorBehaviorSnapshot.window_start,
                InvestorBehaviorSnapshot.id,
            )
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @classmethod
    def _to_view(cls, entity: InvestorBehaviorSnapshot) -> InvestorBehaviorSnapshotView:
        return InvestorBehaviorSnapshotView(
            id=entity.id,
            investor_id=entity.investor_id,
            as_of=cls._as_utc(entity.as_of),
            window_start=cls._as_utc(entity.window_start),
            window_end=cls._as_utc(entity.window_end),
            attention_asset_count=entity.attention_asset_count,
            attention_occurrence_count=entity.attention_occurrence_count,
            new_attention_count=entity.new_attention_count,
            opinion_count=entity.opinion_count,
            bullish_count=entity.bullish_count,
            bearish_count=entity.bearish_count,
            thesis_change_count=entity.thesis_change_count,
            thesis_reinforced_count=entity.thesis_reinforced_count,
            thesis_changed_count=entity.thesis_changed_count,
            portfolio_action_count=entity.portfolio_action_count,
            position_increased_count=entity.position_increased_count,
            position_decreased_count=entity.position_decreased_count,
            positive_alignment_count=entity.positive_alignment_count,
            negative_alignment_count=entity.negative_alignment_count,
            behavior_policy_version=entity.behavior_policy_version,
            calculated_at=cls._as_utc(entity.calculated_at),
            input_identity=entity.input_identity,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["InvestorBehaviorSnapshotRepository"]
