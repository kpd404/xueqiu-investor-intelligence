from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    EventType,
    InvestorActionClaimDTO,
    InvestorActionClaimType,
    PortfolioActionDTO,
    PortfolioActionType,
    PortfolioDTO,
    PortfolioSnapshotBatchDTO,
    PortfolioStatus,
    PositionSnapshotDTO,
)
from database.models import Asset, Investor, Opinion, RawEvent
from database.repositories import (
    InvestorActionClaimRepository,
    PortfolioActionRepository,
    PortfolioRepository,
    PortfolioSnapshotBatchRepository,
    PositionSnapshotRepository,
)
from database.unit_of_work import SqlAlchemyPortfolioUnitOfWork


def _seed_investor_asset(session: Session) -> tuple[Investor, Asset]:
    investor = Investor(name="Portfolio Investor", platform="manual", platform_user_id=str(uuid4()))
    asset = Asset(name="Portfolio Asset", market="SH", symbol=f"PF{uuid4().hex[:6].upper()}")
    session.add_all([investor, asset])
    session.flush()
    return investor, asset


def _portfolio(investor_id, external_id: str) -> PortfolioDTO:
    return PortfolioDTO(
        investor_id=investor_id,
        source="manual",
        external_id=external_id,
        name=external_id,
        status=PortfolioStatus.ACTIVE,
    )


def test_one_investor_can_have_multiple_portfolios_and_identity_is_unique(
    db_session: Session,
) -> None:
    investor, _ = _seed_investor_asset(db_session)
    repository = PortfolioRepository(db_session)

    first = repository.create(_portfolio(investor.id, "portfolio-a"))
    second = repository.create(_portfolio(investor.id, "portfolio-b"))
    db_session.commit()

    assert first.id != second.id
    assert {item.external_id for item in repository.list(investor_id=investor.id)} == {
        "portfolio-a",
        "portfolio-b",
    }

    with pytest.raises(IntegrityError):
        repository.create(_portfolio(investor.id, "portfolio-a"))
    db_session.rollback()


def test_position_snapshot_supports_resolved_and_unresolved_identity(
    db_session: Session,
) -> None:
    investor, asset = _seed_investor_asset(db_session)
    portfolio = PortfolioRepository(db_session).create(_portfolio(investor.id, "portfolio"))
    batch, _ = PortfolioSnapshotBatchRepository(db_session).get_or_create(
        PortfolioSnapshotBatchDTO(
            portfolio_id=portfolio.id,
            snapshot_time=datetime(2026, 9, 3, 10, tzinfo=UTC),
            source="manual",
            external_id="portfolio",
        )
    )
    repository = PositionSnapshotRepository(db_session)
    observed_at = datetime(2026, 9, 3, 10, tzinfo=UTC)

    resolved = repository.create(
        PositionSnapshotDTO(
            portfolio_id=portfolio.id,
            snapshot_batch_id=batch.id,
            asset_id=asset.id,
            weight=0.25,
            snapshot_time=observed_at,
            source_type="manual",
            source_reference="snapshot-resolved",
        )
    )
    unresolved = repository.create(
        PositionSnapshotDTO(
            portfolio_id=portfolio.id,
            snapshot_batch_id=batch.id,
            asset_reference_id=uuid4(),
            snapshot_time=observed_at,
            source_type="manual",
            source_reference="snapshot-unresolved",
        )
    )
    db_session.commit()

    assert resolved.asset_id == asset.id
    assert unresolved.asset_id is None
    assert unresolved.asset_reference_id is not None
    assert len(repository.list(portfolio_id=portfolio.id)) == 2


def test_portfolio_action_uses_current_snapshot_fact_time_and_upsert_is_idempotent(
    db_session: Session,
) -> None:
    investor, asset = _seed_investor_asset(db_session)
    portfolio = PortfolioRepository(db_session).create(_portfolio(investor.id, "portfolio"))
    batch_repository = PortfolioSnapshotBatchRepository(db_session)
    snapshots = PositionSnapshotRepository(db_session)
    first_time = datetime(2026, 9, 3, 10, tzinfo=UTC)
    second_time = datetime(2026, 9, 4, 10, tzinfo=UTC)
    previous_batch, _ = batch_repository.get_or_create(
        PortfolioSnapshotBatchDTO(
            portfolio_id=portfolio.id,
            snapshot_time=first_time,
            source="manual",
            external_id="portfolio-1",
        )
    )
    current_batch, _ = batch_repository.get_or_create(
        PortfolioSnapshotBatchDTO(
            portfolio_id=portfolio.id,
            snapshot_time=second_time,
            source="manual",
            external_id="portfolio-2",
        )
    )
    previous = snapshots.create(
        PositionSnapshotDTO(
            portfolio_id=portfolio.id,
            snapshot_batch_id=previous_batch.id,
            asset_id=asset.id,
            weight=0.10,
            snapshot_time=first_time,
            source_type="manual",
            source_reference="snapshot-1",
        )
    )
    current = snapshots.create(
        PositionSnapshotDTO(
            portfolio_id=portfolio.id,
            snapshot_batch_id=current_batch.id,
            asset_id=asset.id,
            weight=0.20,
            snapshot_time=second_time,
            source_type="manual",
            source_reference="snapshot-2",
        )
    )
    db_session.flush()

    repository = PortfolioActionRepository(db_session)
    action = PortfolioActionDTO(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        previous_snapshot_batch_id=previous_batch.id,
        current_snapshot_batch_id=current_batch.id,
        previous_position_snapshot_id=previous.id,
        current_position_snapshot_id=current.id,
        action_type=PortfolioActionType.POSITION_INCREASED,
        effective_time=second_time,
        calculated_at=datetime(2026, 9, 4, 11, tzinfo=UTC),
    )
    created = repository.create(action)
    db_session.commit()

    assert created.effective_time == second_time
    assert created.calculated_at == datetime(2026, 9, 4, 11, tzinfo=UTC)

    bad_time = action.model_copy(update={"effective_time": second_time + timedelta(minutes=1)})
    with pytest.raises(ValueError, match="effective_time"):
        repository.create(bad_time)

    updated = action.model_copy(update={"calculated_at": datetime(2026, 9, 4, 12, tzinfo=UTC)})
    reused = repository.upsert(updated)
    db_session.commit()
    assert reused.id == created.id
    assert reused.calculated_at == created.calculated_at


def test_investor_action_claim_keeps_event_provenance_and_does_not_create_opinion(
    db_session: Session,
) -> None:
    investor, asset = _seed_investor_asset(db_session)
    published_time = datetime(2026, 9, 3, 12, tzinfo=UTC)
    event = RawEvent(
        investor_id=investor.id,
        event_type=EventType.POST,
        source="manual",
        url=f"https://example.test/action/{uuid4()}",
        published_time=published_time,
        content="I increased this position.",
        raw_data={},
        hash=uuid4().hex + uuid4().hex,
        collected_time=published_time,
    )
    db_session.add(event)
    db_session.flush()
    repository = InvestorActionClaimRepository(db_session)
    claim = repository.create(
        InvestorActionClaimDTO(
            investor_id=investor.id,
            asset_id=asset.id,
            event_id=event.id,
            claim_type=InvestorActionClaimType.ADD_POSITION,
            confidence=0.9,
            evidence_text="I increased this position.",
            published_time=published_time,
            analysis_version="opinion-analysis-v3",
        )
    )
    db_session.commit()

    assert claim.event_id == event.id
    assert claim.asset_id == asset.id
    assert db_session.query(Opinion).count() == 0
    assert repository.list(investor_id=investor.id)[0].event_id == event.id


def test_portfolio_unit_of_work_composes_all_repositories(
    db_session_factory: sessionmaker[Session],
) -> None:
    with SqlAlchemyPortfolioUnitOfWork(db_session_factory) as unit_of_work:
        assert isinstance(unit_of_work.portfolios, PortfolioRepository)
        assert isinstance(unit_of_work.position_snapshots, PositionSnapshotRepository)
        assert isinstance(unit_of_work.portfolio_actions, PortfolioActionRepository)
        assert isinstance(unit_of_work.investor_action_claims, InvestorActionClaimRepository)
