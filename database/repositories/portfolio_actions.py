from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import PortfolioActionDTO, PortfolioActionType, PortfolioActionView
from database.models.portfolio import Portfolio
from database.models.portfolio_action import PortfolioAction
from database.models.portfolio_snapshot import PortfolioSnapshotBatch
from database.models.position_snapshot import PositionSnapshot


class PortfolioActionRepository:
    """Persistence adapter for traceable, derived position changes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, action: PortfolioActionDTO) -> PortfolioActionView:
        self._validate_snapshot_provenance(action)
        entity = PortfolioAction(
            portfolio_id=action.portfolio_id,
            asset_id=action.asset_id,
            asset_reference_id=action.asset_reference_id,
            previous_snapshot_batch_id=action.previous_snapshot_batch_id,
            current_snapshot_batch_id=action.current_snapshot_batch_id,
            previous_position_snapshot_id=action.previous_position_snapshot_id,
            current_position_snapshot_id=action.current_position_snapshot_id,
            # Preserve the pre-2E.3-D column values for old readers.
            previous_snapshot_id=action.previous_position_snapshot_id,
            current_snapshot_id=action.current_position_snapshot_id,
            action_type=action.action_type,
            effective_time=action.effective_time,
            calculated_at=action.calculated_at,
            created_at=action.created_at,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def add_if_absent(self, action: PortfolioActionDTO) -> tuple[PortfolioActionView, bool]:
        """Insert one transition or reuse its database-protected identity."""

        existing = self.get_by_snapshot_transition(
            action.portfolio_id,
            action.previous_snapshot_batch_id,
            action.current_snapshot_batch_id,
            asset_id=action.asset_id,
            asset_reference_id=action.asset_reference_id,
            action_type=action.action_type,
        )
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                entity = PortfolioAction(
                    portfolio_id=action.portfolio_id,
                    asset_id=action.asset_id,
                    asset_reference_id=action.asset_reference_id,
                    previous_snapshot_batch_id=action.previous_snapshot_batch_id,
                    current_snapshot_batch_id=action.current_snapshot_batch_id,
                    previous_position_snapshot_id=action.previous_position_snapshot_id,
                    current_position_snapshot_id=action.current_position_snapshot_id,
                    previous_snapshot_id=action.previous_position_snapshot_id,
                    current_snapshot_id=action.current_position_snapshot_id,
                    action_type=action.action_type,
                    effective_time=action.effective_time,
                    calculated_at=action.calculated_at,
                    created_at=action.created_at,
                )
                self._validate_snapshot_provenance(action)
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_snapshot_transition(
                action.portfolio_id,
                action.previous_snapshot_batch_id,
                action.current_snapshot_batch_id,
                asset_id=action.asset_id,
                asset_reference_id=action.asset_reference_id,
                action_type=action.action_type,
            )
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def get(self, action_id: UUID) -> PortfolioActionView | None:
        entity = self._session.get(PortfolioAction, action_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_snapshot_transition(
        self,
        portfolio_id: UUID,
        previous_snapshot_batch_id: UUID,
        current_snapshot_batch_id: UUID,
        *,
        asset_id: UUID | None = None,
        asset_reference_id: UUID | None = None,
        action_type: PortfolioActionType | None = None,
    ) -> PortfolioActionView | None:
        if (asset_id is None) == (asset_reference_id is None):
            raise ValueError("exactly one asset identity is required")
        statement = select(PortfolioAction).where(
            PortfolioAction.portfolio_id == portfolio_id,
            PortfolioAction.previous_snapshot_batch_id == previous_snapshot_batch_id,
            PortfolioAction.current_snapshot_batch_id == current_snapshot_batch_id,
        )
        if asset_id is not None:
            statement = statement.where(PortfolioAction.asset_id == asset_id)
        else:
            statement = statement.where(PortfolioAction.asset_reference_id == asset_reference_id)
        if action_type is not None:
            statement = statement.where(PortfolioAction.action_type == action_type)
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def get_by_current_snapshot(self, snapshot_id: UUID) -> PortfolioActionView | None:
        statement = select(PortfolioAction).where(
            or_(
                PortfolioAction.current_position_snapshot_id == snapshot_id,
                PortfolioAction.current_snapshot_id == snapshot_id,
            )
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def list_by_portfolio(self, portfolio_id: UUID) -> list[PortfolioActionView]:
        statement = (
            select(PortfolioAction)
            .where(PortfolioAction.portfolio_id == portfolio_id)
            .order_by(PortfolioAction.effective_time, PortfolioAction.id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_by_investor_asset(
        self,
        investor_id: UUID,
        asset_id: UUID,
    ) -> list[PortfolioActionView]:
        statement = (
            select(PortfolioAction)
            .join(Portfolio, PortfolioAction.portfolio_id == Portfolio.id)
            .where(
                Portfolio.investor_id == investor_id,
                PortfolioAction.asset_id == asset_id,
            )
            .order_by(PortfolioAction.effective_time, PortfolioAction.id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list_by_investor(self, investor_id: UUID) -> list[PortfolioActionView]:
        """Return all derived portfolio actions for one investor."""

        statement = (
            select(PortfolioAction)
            .join(Portfolio, PortfolioAction.portfolio_id == Portfolio.id)
            .where(Portfolio.investor_id == investor_id)
            .order_by(PortfolioAction.effective_time, PortfolioAction.id)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def list(
        self,
        *,
        portfolio_id: UUID | None = None,
        asset_id: UUID | None = None,
    ) -> list[PortfolioActionView]:
        if portfolio_id is None:
            statement = select(PortfolioAction)
            if asset_id is not None:
                statement = statement.where(PortfolioAction.asset_id == asset_id)
            statement = statement.order_by(PortfolioAction.effective_time, PortfolioAction.id)
            return [self._to_view(entity) for entity in self._session.scalars(statement)]
        return [
            action
            for action in self.list_by_portfolio(portfolio_id)
            if asset_id is None or action.asset_id == asset_id
        ]

    def upsert(self, action: PortfolioActionDTO) -> PortfolioActionView:
        existing = self.get_by_snapshot_transition(
            action.portfolio_id,
            action.previous_snapshot_batch_id,
            action.current_snapshot_batch_id,
            asset_id=action.asset_id,
            asset_reference_id=action.asset_reference_id,
            action_type=action.action_type,
        )
        if existing is not None:
            return existing
        return self.create(action)

    def _validate_snapshot_provenance(self, action: PortfolioActionDTO) -> None:
        previous_batch = self._session.get(
            PortfolioSnapshotBatch, action.previous_snapshot_batch_id
        )
        current_batch = self._session.get(PortfolioSnapshotBatch, action.current_snapshot_batch_id)
        if previous_batch is None or current_batch is None:
            raise ValueError("both snapshot batch IDs must reference PortfolioSnapshotBatch")
        if previous_batch.portfolio_id != action.portfolio_id:
            raise ValueError("previous snapshot batch must match the action portfolio")
        if current_batch.portfolio_id != action.portfolio_id:
            raise ValueError("current snapshot batch must match the action portfolio")
        if self._as_utc(action.effective_time) != self._as_utc(current_batch.snapshot_time):
            raise ValueError("effective_time must equal current snapshot batch snapshot_time")
        if (action.asset_id is None) == (action.asset_reference_id is None):
            raise ValueError("exactly one asset identity is required")

        previous = self._position(action.previous_position_snapshot_id)
        current = self._position(action.current_position_snapshot_id)
        if previous is None and current is None:
            raise ValueError("action requires a previous or current position snapshot")
        if previous is not None:
            self._validate_position(
                previous,
                action,
                expected_batch_id=action.previous_snapshot_batch_id,
            )
        if current is not None:
            self._validate_position(
                current,
                action,
                expected_batch_id=action.current_snapshot_batch_id,
            )

        if action.action_type is PortfolioActionType.POSITION_ADDED and (
            previous is not None or current is None
        ):
            raise ValueError("POSITION_ADDED requires only a current position")
        if action.action_type is PortfolioActionType.POSITION_REMOVED and (
            previous is None or current is not None
        ):
            raise ValueError("POSITION_REMOVED requires only a previous position")
        if action.action_type in {
            PortfolioActionType.POSITION_INCREASED,
            PortfolioActionType.POSITION_DECREASED,
            PortfolioActionType.POSITION_UNCHANGED,
        } and (previous is None or current is None):
            raise ValueError("weight changes require both position snapshots")

    def _position(self, position_id: UUID | None) -> PositionSnapshot | None:
        return self._session.get(PositionSnapshot, position_id) if position_id else None

    @staticmethod
    def _validate_position(
        position: PositionSnapshot,
        action: PortfolioActionDTO,
        *,
        expected_batch_id: UUID,
    ) -> None:
        if position.portfolio_id != action.portfolio_id:
            raise ValueError("position snapshot must match the action portfolio")
        if position.snapshot_batch_id != expected_batch_id:
            raise ValueError("position snapshot must belong to its provenance batch")
        if action.asset_id is not None:
            if position.asset_id != action.asset_id or position.asset_reference_id is not None:
                raise ValueError("position asset identity does not match action asset_id")
        elif (
            position.asset_reference_id != action.asset_reference_id
            or position.asset_id is not None
        ):
            raise ValueError("position asset identity does not match action asset_reference_id")

    @classmethod
    def _to_view(cls, entity: PortfolioAction) -> PortfolioActionView:
        previous_position_snapshot_id = (
            entity.previous_position_snapshot_id or entity.previous_snapshot_id
        )
        current_position_snapshot_id = (
            entity.current_position_snapshot_id or entity.current_snapshot_id
        )
        return PortfolioActionView(
            id=entity.id,
            portfolio_id=entity.portfolio_id,
            asset_id=entity.asset_id,
            asset_reference_id=entity.asset_reference_id,
            previous_snapshot_batch_id=entity.previous_snapshot_batch_id,
            current_snapshot_batch_id=entity.current_snapshot_batch_id,
            previous_position_snapshot_id=previous_position_snapshot_id,
            current_position_snapshot_id=current_position_snapshot_id,
            action_type=entity.action_type,
            effective_time=cls._as_utc(entity.effective_time),
            calculated_at=cls._as_utc(entity.calculated_at),
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
