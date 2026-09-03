from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    PortfolioPositionInput,
    PortfolioSnapshotImportCommand,
)
from database.models import Asset, Investor, Portfolio, PortfolioSnapshotBatch, PositionSnapshot
from database.repositories import PortfolioSnapshotBatchRepository
from database.unit_of_work import SqlAlchemyPortfolioUnitOfWork
from portfolio import PortfolioSnapshotImportService


def _seed_investor_assets(session: Session) -> tuple[Investor, Asset, Asset]:
    investor = Investor(
        name="Snapshot Import Investor",
        platform="manual",
        platform_user_id=f"snapshot-{uuid4()}",
    )
    merchant_ship = Asset(name="招商轮船", market="SH", symbol="601872")
    cosco_energy = Asset(name="中远海能", market="SH", symbol="600026")
    session.add_all([investor, merchant_ship, cosco_energy])
    session.commit()
    return investor, merchant_ship, cosco_energy


def _command(investor_id, snapshot_time: datetime) -> PortfolioSnapshotImportCommand:
    return PortfolioSnapshotImportCommand(
        source="XUEQIU",
        external_id="portfolio-001",
        portfolio_name="长期价值组合",
        investor_id=investor_id,
        snapshot_time=snapshot_time,
        positions=(
            PortfolioPositionInput(
                asset_name="招商轮船",
                symbol="601872",
                market="SH",
                weight=0.10,
            ),
            PortfolioPositionInput(
                asset_name="中远海能",
                symbol="600026",
                market="SH",
                weight=0.20,
                source_reference="https://example.test/position/cosco",
            ),
            PortfolioPositionInput(asset_name="某新能源ETF", weight=0.05),
        ),
    )


def test_snapshot_import_resolves_known_assets_and_preserves_unknown_identity(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        investor, merchant_ship, cosco_energy = _seed_investor_assets(session)

    service = PortfolioSnapshotImportService(
        lambda: SqlAlchemyPortfolioUnitOfWork(db_session_factory)
    )
    input_time = datetime(2026, 9, 3, 10, tzinfo=timezone(timedelta(hours=8)))
    first = service.import_snapshot(_command(investor.id, input_time))

    assert first.portfolio_created is True
    assert first.batch_created is True
    assert first.batch_reused is False
    assert first.created_count == 3
    assert first.reused_count == 0
    assert first.resolved_count == 2
    assert first.unresolved_count == 1
    with db_session_factory() as session:
        snapshots = list(
            session.scalars(
                select(PositionSnapshot)
                .where(PositionSnapshot.portfolio_id == first.portfolio_id)
                .order_by(PositionSnapshot.id)
            )
        )
        assert len(snapshots) == 3
        batch = session.get(PortfolioSnapshotBatch, first.snapshot_batch_id)
        assert batch is not None
        assert [
            item.id for item in PortfolioSnapshotBatchRepository(session).list_positions(batch.id)
        ] == [item.id for item in snapshots]
        assert {item.asset_id for item in snapshots if item.asset_id is not None} == {
            merchant_ship.id,
            cosco_energy.id,
        }
        unknown = next(item for item in snapshots if item.asset_id is None)
        assert unknown.asset_reference_id is not None
        assert unknown.snapshot_time.replace(tzinfo=UTC) == datetime(2026, 9, 3, 2, tzinfo=UTC)
        assert unknown.source_type == "xueqiu"
        assert session.scalar(select(func.count()).select_from(Asset)) == 2

    second = service.import_snapshot(_command(investor.id, input_time))
    assert second.portfolio_created is False
    assert second.batch_created is False
    assert second.batch_reused is True
    assert second.snapshot_batch_id == first.snapshot_batch_id
    assert second.created_count == 0
    assert second.reused_count == 3
    assert second.position_snapshot_ids == first.position_snapshot_ids
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PositionSnapshot)) == 3


def test_snapshot_import_uses_existing_portfolio_and_unit_of_work_boundary(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        investor, _, _ = _seed_investor_assets(session)

    service = PortfolioSnapshotImportService(
        lambda: SqlAlchemyPortfolioUnitOfWork(db_session_factory)
    )
    command = _command(investor.id, datetime(2026, 9, 4, tzinfo=UTC))
    result = service.import_(command)

    assert result.portfolio_id is not None
    with db_session_factory() as session:
        portfolio = session.get(Portfolio, result.portfolio_id)
        assert portfolio is not None
        assert portfolio.investor_id == investor.id
