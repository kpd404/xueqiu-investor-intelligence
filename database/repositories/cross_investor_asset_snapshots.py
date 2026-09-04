from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import (
    CrossInvestorAssetSnapshotCreate,
    CrossInvestorAssetSnapshotView,
    CrossInvestorContribution,
)
from database.models.cross_investor_asset_snapshot import CrossInvestorAssetSnapshot


class CrossInvestorAssetSnapshotRepository:
    """Persistence adapter for immutable asset-centric snapshots."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        snapshot: CrossInvestorAssetSnapshotCreate,
    ) -> CrossInvestorAssetSnapshotView:
        entity = self._build_entity(snapshot)
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def add_if_absent(
        self,
        snapshot: CrossInvestorAssetSnapshotCreate,
    ) -> tuple[CrossInvestorAssetSnapshotView, bool]:
        existing = self.get_by_input_identity(snapshot.input_identity)
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = self._build_entity(snapshot)
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_input_identity(snapshot.input_identity)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def get(self, snapshot_id: UUID) -> CrossInvestorAssetSnapshotView | None:
        entity = self._session.get(CrossInvestorAssetSnapshot, snapshot_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_input_identity(self, input_identity: str) -> CrossInvestorAssetSnapshotView | None:
        entity = self._session.scalar(
            select(CrossInvestorAssetSnapshot).where(
                CrossInvestorAssetSnapshot.input_identity == input_identity
            )
        )
        return self._to_view(entity) if entity is not None else None

    def list_by_asset(self, asset_id: UUID) -> list[CrossInvestorAssetSnapshotView]:
        statement = (
            select(CrossInvestorAssetSnapshot)
            .where(CrossInvestorAssetSnapshot.asset_id == asset_id)
            .order_by(
                CrossInvestorAssetSnapshot.window_end,
                CrossInvestorAssetSnapshot.window_start,
                CrossInvestorAssetSnapshot.as_of,
                CrossInvestorAssetSnapshot.id,
            )
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_versions_by_scope(
        self,
        asset_id: UUID,
        window_start: datetime,
        window_end: datetime,
        cross_investor_policy_version: str,
    ) -> list[CrossInvestorAssetSnapshotView]:
        statement = (
            select(CrossInvestorAssetSnapshot)
            .where(
                CrossInvestorAssetSnapshot.asset_id == asset_id,
                CrossInvestorAssetSnapshot.window_start == self._as_utc(window_start),
                CrossInvestorAssetSnapshot.window_end == self._as_utc(window_end),
                CrossInvestorAssetSnapshot.cross_investor_policy_version
                == cross_investor_policy_version,
            )
            .order_by(CrossInvestorAssetSnapshot.input_identity, CrossInvestorAssetSnapshot.id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    @staticmethod
    def _build_entity(snapshot: CrossInvestorAssetSnapshotCreate) -> CrossInvestorAssetSnapshot:
        return CrossInvestorAssetSnapshot(
            asset_id=snapshot.asset_id,
            as_of=snapshot.as_of,
            window_start=snapshot.window_start,
            window_end=snapshot.window_end,
            attention_occurrence_count=snapshot.attention_occurrence_count,
            attention_investor_count=snapshot.attention_investor_count,
            new_attention_investor_count=snapshot.new_attention_investor_count,
            opinion_count=snapshot.opinion_count,
            opinion_investor_count=snapshot.opinion_investor_count,
            bullish_investor_count=snapshot.bullish_investor_count,
            bearish_investor_count=snapshot.bearish_investor_count,
            neutral_investor_count=snapshot.neutral_investor_count,
            thesis_change_count=snapshot.thesis_change_count,
            thesis_change_investor_count=snapshot.thesis_change_investor_count,
            thesis_reinforced_investor_count=snapshot.thesis_reinforced_investor_count,
            thesis_changed_investor_count=snapshot.thesis_changed_investor_count,
            portfolio_action_count=snapshot.portfolio_action_count,
            portfolio_action_investor_count=snapshot.portfolio_action_investor_count,
            position_increased_count=snapshot.position_increased_count,
            position_decreased_count=snapshot.position_decreased_count,
            consistency_count=snapshot.consistency_count,
            consistency_investor_count=snapshot.consistency_investor_count,
            positive_alignment_count=snapshot.positive_alignment_count,
            negative_alignment_count=snapshot.negative_alignment_count,
            contributions=[
                contribution.model_dump(mode="json") for contribution in snapshot.contributions
            ],
            opinion_analysis_version=snapshot.opinion_analysis_version,
            attention_policy_version=snapshot.attention_policy_version,
            thesis_comparison_version=snapshot.thesis_comparison_version,
            consistency_policy_version=snapshot.consistency_policy_version,
            cross_investor_policy_version=snapshot.cross_investor_policy_version,
            calculated_at=snapshot.calculated_at,
            input_identity=snapshot.input_identity,
        )

    @classmethod
    def _to_view(cls, entity: CrossInvestorAssetSnapshot) -> CrossInvestorAssetSnapshotView:
        contributions = tuple(
            CrossInvestorContribution.model_validate(value)
            for value in (entity.contributions or [])
        )
        return CrossInvestorAssetSnapshotView(
            id=entity.id,
            asset_id=entity.asset_id,
            as_of=cls._as_utc(entity.as_of),
            window_start=cls._as_utc(entity.window_start),
            window_end=cls._as_utc(entity.window_end),
            attention_occurrence_count=entity.attention_occurrence_count,
            attention_investor_count=entity.attention_investor_count,
            new_attention_investor_count=entity.new_attention_investor_count,
            opinion_count=entity.opinion_count,
            opinion_investor_count=entity.opinion_investor_count,
            bullish_investor_count=entity.bullish_investor_count,
            bearish_investor_count=entity.bearish_investor_count,
            neutral_investor_count=entity.neutral_investor_count,
            thesis_change_count=entity.thesis_change_count,
            thesis_change_investor_count=entity.thesis_change_investor_count,
            thesis_reinforced_investor_count=entity.thesis_reinforced_investor_count,
            thesis_changed_investor_count=entity.thesis_changed_investor_count,
            portfolio_action_count=entity.portfolio_action_count,
            portfolio_action_investor_count=entity.portfolio_action_investor_count,
            position_increased_count=entity.position_increased_count,
            position_decreased_count=entity.position_decreased_count,
            consistency_count=entity.consistency_count,
            consistency_investor_count=entity.consistency_investor_count,
            positive_alignment_count=entity.positive_alignment_count,
            negative_alignment_count=entity.negative_alignment_count,
            contributions=contributions,
            opinion_analysis_version=entity.opinion_analysis_version,
            attention_policy_version=entity.attention_policy_version,
            thesis_comparison_version=entity.thesis_comparison_version,
            consistency_policy_version=entity.consistency_policy_version,
            cross_investor_policy_version=entity.cross_investor_policy_version,
            calculated_at=cls._as_utc(entity.calculated_at),
            input_identity=entity.input_identity,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["CrossInvestorAssetSnapshotRepository"]
