from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    PortfolioActionType,
    PortfolioDTO,
    PortfolioSnapshotBatchDTO,
    PortfolioStatus,
    PositionSnapshotDTO,
)
from database.models import Asset, Investor, PortfolioAction, PositionSnapshot
from database.repositories import (
    PortfolioActionRepository,
    PortfolioRepository,
    PortfolioSnapshotBatchRepository,
    PositionSnapshotRepository,
)
from database.unit_of_work import SqlAlchemyPortfolioUnitOfWork
from portfolio import PositionChangeDetectionService

SNAPSHOT_ONE = datetime(2026, 9, 3, 10, tzinfo=UTC)
SNAPSHOT_TWO = datetime(2026, 9, 4, 10, tzinfo=UTC)
UNRESOLVED_REFERENCE = UUID("00000000-0000-0000-0000-000000000901")


def _seed_transition(
    factory: sessionmaker[Session],
    previous: dict[str, float | None],
    current: dict[str, float | None],
) -> tuple[UUID, UUID, UUID, dict[str, UUID], dict[str, UUID]]:
    with factory() as session:
        investor = Investor(
            name="Position Change Investor",
            platform="manual",
            platform_user_id=f"position-change-{uuid4()}",
        )
        asset_a = Asset(name="Position Asset A", market="SH", symbol=f"PFA{uuid4().hex[:6]}")
        asset_b = Asset(name="Position Asset B", market="SH", symbol=f"PFB{uuid4().hex[:6]}")
        session.add_all([investor, asset_a, asset_b])
        session.flush()
        portfolio = PortfolioRepository(session).create(
            PortfolioDTO(
                investor_id=investor.id,
                source="manual",
                external_id=f"portfolio-{uuid4()}",
                name="Position Change Portfolio",
                status=PortfolioStatus.ACTIVE,
            )
        )
        batches = PortfolioSnapshotBatchRepository(session)
        previous_batch, _ = batches.get_or_create(
            PortfolioSnapshotBatchDTO(
                portfolio_id=portfolio.id,
                snapshot_time=SNAPSHOT_ONE,
                source="manual",
                external_id="snapshot-1",
            )
        )
        current_batch, _ = batches.get_or_create(
            PortfolioSnapshotBatchDTO(
                portfolio_id=portfolio.id,
                snapshot_time=SNAPSHOT_TWO,
                source="manual",
                external_id="snapshot-2",
            )
        )
        token_to_asset = {"A": asset_a.id, "B": asset_b.id}
        previous_ids = _create_positions(
            session,
            portfolio.id,
            previous_batch.id,
            SNAPSHOT_ONE,
            previous,
            token_to_asset,
            "previous",
        )
        current_ids = _create_positions(
            session,
            portfolio.id,
            current_batch.id,
            SNAPSHOT_TWO,
            current,
            token_to_asset,
            "current",
        )
        session.commit()
        return portfolio.id, previous_batch.id, current_batch.id, previous_ids, current_ids


def _create_positions(
    session: Session,
    portfolio_id: UUID,
    batch_id: UUID,
    snapshot_time: datetime,
    positions: dict[str, float | None],
    token_to_asset: dict[str, UUID],
    label: str,
) -> dict[str, UUID]:
    repository = PositionSnapshotRepository(session)
    result: dict[str, UUID] = {}
    for token, weight in positions.items():
        asset_id = token_to_asset.get(token)
        snapshot = repository.create(
            PositionSnapshotDTO(
                portfolio_id=portfolio_id,
                snapshot_batch_id=batch_id,
                asset_id=asset_id,
                asset_reference_id=None if asset_id is not None else UNRESOLVED_REFERENCE,
                weight=weight,
                snapshot_time=snapshot_time,
                source_type="manual",
                source_reference=f"{label}:{token}",
            )
        )
        result[token] = snapshot.id
    return result


def _service(factory: sessionmaker[Session]) -> PositionChangeDetectionService:
    return PositionChangeDetectionService(lambda: SqlAlchemyPortfolioUnitOfWork(factory))


def _actions(factory: sessionmaker[Session], portfolio_id: UUID) -> list:
    with factory() as session:
        return PortfolioActionRepository(session).list_by_portfolio(portfolio_id)


def test_position_added_has_current_provenance(
    db_session_factory: sessionmaker[Session],
) -> None:
    portfolio_id, previous_batch_id, current_batch_id, previous_ids, current_ids = _seed_transition(
        db_session_factory,
        {"A": 0.10},
        {"A": 0.10, "B": 0.20},
    )

    result = _service(db_session_factory).detect(previous_batch_id, current_batch_id)

    assert result.portfolio_id == portfolio_id
    assert result.created_count == 2
    with db_session_factory() as session:
        actions = PortfolioActionRepository(session).list_by_portfolio(portfolio_id)
        added = next(
            action
            for action in actions
            if action.asset_id is not None
            and action.current_position_snapshot_id == current_ids["B"]
        )
        unchanged = next(
            action for action in actions if action.current_position_snapshot_id == current_ids["A"]
        )
        assert added.action_type is PortfolioActionType.POSITION_ADDED
        assert added.previous_snapshot_batch_id == previous_batch_id
        assert added.current_snapshot_batch_id == current_batch_id
        assert added.previous_position_snapshot_id is None
        assert added.current_position_snapshot_id == current_ids["B"]
        assert added.effective_time == SNAPSHOT_TWO
        assert unchanged.action_type is PortfolioActionType.POSITION_UNCHANGED
        assert unchanged.previous_position_snapshot_id == previous_ids["A"]


def test_position_removed_has_previous_provenance(
    db_session_factory: sessionmaker[Session],
) -> None:
    portfolio_id, previous_batch_id, current_batch_id, previous_ids, _ = _seed_transition(
        db_session_factory,
        {"A": 0.10, "B": 0.20},
        {"A": 0.10},
    )

    result = _service(db_session_factory).detect(previous_batch_id, current_batch_id)

    assert result.created_count == 2
    actions = _actions(db_session_factory, portfolio_id)
    removed = next(
        action for action in actions if action.previous_position_snapshot_id == previous_ids["B"]
    )
    assert removed.action_type is PortfolioActionType.POSITION_REMOVED
    assert removed.previous_snapshot_batch_id == previous_batch_id
    assert removed.current_snapshot_batch_id == current_batch_id
    assert removed.previous_position_snapshot_id == previous_ids["B"]
    assert removed.current_position_snapshot_id is None
    assert removed.effective_time == SNAPSHOT_TWO


@pytest.mark.parametrize(
    ("previous_weight", "current_weight", "expected"),
    [
        (0.10, 0.20, PortfolioActionType.POSITION_INCREASED),
        (0.20, 0.10, PortfolioActionType.POSITION_DECREASED),
        (0.10, 0.10, PortfolioActionType.POSITION_UNCHANGED),
        (None, 0.10, PortfolioActionType.POSITION_UNCHANGED),
    ],
)
def test_weight_change_classification_uses_only_snapshot_weight(
    db_session_factory: sessionmaker[Session],
    previous_weight: float | None,
    current_weight: float | None,
    expected: PortfolioActionType,
) -> None:
    portfolio_id, previous_batch_id, current_batch_id, _, _ = _seed_transition(
        db_session_factory,
        {"A": previous_weight},
        {"A": current_weight},
    )

    result = _service(db_session_factory).detect(previous_batch_id, current_batch_id)

    assert result.created_count == 1
    assert _actions(db_session_factory, portfolio_id)[0].action_type is expected


def test_unresolved_reference_matches_only_same_reference(
    db_session_factory: sessionmaker[Session],
) -> None:
    portfolio_id, previous_batch_id, current_batch_id, previous_ids, current_ids = _seed_transition(
        db_session_factory,
        {"U": 0.10},
        {"U": 0.20},
    )

    result = _service(db_session_factory).detect(previous_batch_id, current_batch_id)

    assert result.created_count == 1
    action = _actions(db_session_factory, portfolio_id)[0]
    assert action.asset_id is None
    assert action.asset_reference_id == UNRESOLVED_REFERENCE
    assert action.action_type is PortfolioActionType.POSITION_INCREASED
    assert action.previous_position_snapshot_id == previous_ids["U"]
    assert action.current_position_snapshot_id == current_ids["U"]


def test_resolved_and_unresolved_identities_do_not_match(
    db_session_factory: sessionmaker[Session],
) -> None:
    portfolio_id, previous_batch_id, current_batch_id, _, _ = _seed_transition(
        db_session_factory,
        {"A": 0.10},
        {"U": 0.10},
    )

    result = _service(db_session_factory).detect(previous_batch_id, current_batch_id)

    assert result.created_count == 2
    actions = _actions(db_session_factory, portfolio_id)
    assert {action.action_type for action in actions} == {
        PortfolioActionType.POSITION_ADDED,
        PortfolioActionType.POSITION_REMOVED,
    }
    assert all(
        not (action.asset_id is None and action.asset_reference_id is None) for action in actions
    )


def test_detection_is_idempotent_and_repository_can_query_transition(
    db_session_factory: sessionmaker[Session],
) -> None:
    portfolio_id, previous_batch_id, current_batch_id, _, current_ids = _seed_transition(
        db_session_factory,
        {"A": 0.10},
        {"A": 0.10, "B": 0.20},
    )
    service = _service(db_session_factory)

    first = service.detect(previous_batch_id, current_batch_id)
    second = service.detect(previous_batch_id, current_batch_id)

    assert first.created_count == 2
    assert first.reused_count == 0
    assert second.created_count == 0
    assert second.reused_count == 2
    assert first.action_ids == second.action_ids
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PortfolioAction)) == 2
        added = PortfolioActionRepository(session).get_by_snapshot_transition(
            portfolio_id,
            previous_batch_id,
            current_batch_id,
            asset_id=next(
                position.asset_id
                for position in session.scalars(
                    select(PositionSnapshot).where(PositionSnapshot.id == current_ids["B"])
                )
                if position.asset_id is not None
            ),
            action_type=PortfolioActionType.POSITION_ADDED,
        )
        assert added is not None
