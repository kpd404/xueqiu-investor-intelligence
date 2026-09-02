from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import EffectiveAnalysisPolicy, EventAnalysisStatus, InvestorAssetStateSnapshot
from database.models.event_analysis import EventAnalysis
from database.models.investor_asset_state import InvestorAssetState
from database.models.opinion import Opinion


class InvestorAssetStateRepository:
    """Persistence-only operations for the derived state snapshot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, investor_id: UUID, asset_id: UUID) -> InvestorAssetState | None:
        statement = select(InvestorAssetState).where(
            InvestorAssetState.investor_id == investor_id,
            InvestorAssetState.asset_id == asset_id,
        )
        return self._session.scalar(statement)

    def list_by_asset(self, asset_id: UUID) -> list[InvestorAssetState]:
        statement = (
            select(InvestorAssetState)
            .where(InvestorAssetState.asset_id == asset_id)
            .order_by(InvestorAssetState.investor_id, InvestorAssetState.id)
        )
        return list(self._session.scalars(statement))

    def list_effective(self, policy: EffectiveAnalysisPolicy) -> list[InvestorAssetState]:
        """Return projections backed by at least one active interpretation."""

        active_opinion = (
            select(Opinion.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(
                Opinion.investor_id == InvestorAssetState.investor_id,
                Opinion.asset_id == InvestorAssetState.asset_id,
                EventAnalysis.analysis_version == policy.active_analysis_version,
                EventAnalysis.status.in_(
                    [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                ),
            )
            .exists()
        )
        statement = (
            select(InvestorAssetState)
            .where(active_opinion)
            .order_by(InvestorAssetState.investor_id, InvestorAssetState.asset_id)
        )
        return list(self._session.scalars(statement))

    def get_for_update(self, investor_id: UUID, asset_id: UUID) -> InvestorAssetState | None:
        statement = (
            select(InvestorAssetState)
            .where(
                InvestorAssetState.investor_id == investor_id,
                InvestorAssetState.asset_id == asset_id,
            )
            .with_for_update()
        )
        return self._session.scalar(statement)

    def upsert(
        self,
        snapshot: InvestorAssetStateSnapshot,
        current: InvestorAssetState | None = None,
    ) -> InvestorAssetState:
        state = current or self.get_for_update(snapshot.investor_id, snapshot.asset_id)
        if state is not None:
            self._apply_snapshot(state, snapshot)
            self._session.flush()
            return state

        state = InvestorAssetState(
            investor_id=snapshot.investor_id,
            asset_id=snapshot.asset_id,
        )
        self._apply_snapshot(state, snapshot)
        try:
            with self._session.begin_nested():
                self._session.add(state)
                self._session.flush()
        except IntegrityError:
            state = self.get_for_update(snapshot.investor_id, snapshot.asset_id)
            if state is None:
                raise
            self._apply_snapshot(state, snapshot)
            self._session.flush()
        return state

    def to_snapshot(self, state: InvestorAssetState) -> InvestorAssetStateSnapshot:
        return InvestorAssetStateSnapshot(
            investor_id=state.investor_id,
            asset_id=state.asset_id,
            attention_level=state.attention_level,
            direction=state.direction,
            conviction=state.conviction,
            mention_count=state.mention_count,
            position_status=state.position_status,
            last_activity_time=self._as_utc_optional(state.last_activity_time),
            last_material_change_time=self._as_utc_optional(state.last_material_change_time),
        )

    @staticmethod
    def _apply_snapshot(
        state: InvestorAssetState,
        snapshot: InvestorAssetStateSnapshot,
    ) -> None:
        state.attention_level = snapshot.attention_level
        state.direction = snapshot.direction
        state.conviction = snapshot.conviction
        state.mention_count = snapshot.mention_count
        state.position_status = snapshot.position_status
        state.last_activity_time = snapshot.last_activity_time
        state.last_material_change_time = snapshot.last_material_change_time

    @staticmethod
    def _as_utc_optional(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
