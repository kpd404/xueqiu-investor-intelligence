from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    InvestorActionClaimDTO,
    InvestorActionClaimType,
    PortfolioActionDTO,
    PortfolioActionType,
    PortfolioDTO,
    PortfolioSnapshotBatchDTO,
    PortfolioSnapshotImportResult,
    PortfolioStatus,
    PositionSnapshotDTO,
)


def test_portfolio_contract_is_frozen_and_timezone_aware() -> None:
    created_at = datetime(2026, 9, 3, 9, tzinfo=UTC)
    portfolio = PortfolioDTO(
        investor_id=uuid4(),
        source=" Manual ",
        external_id=" portfolio-1 ",
        name=" Main Portfolio ",
        status=PortfolioStatus.ACTIVE,
        created_at=created_at,
        updated_at=created_at,
    )

    assert portfolio.source == "manual"
    assert portfolio.external_id == "portfolio-1"
    assert portfolio.name == "Main Portfolio"
    assert portfolio.created_at.tzinfo is not None
    with pytest.raises(ValidationError):
        portfolio.name = "changed"

    with pytest.raises(ValidationError):
        PortfolioDTO(
            investor_id=uuid4(),
            source="manual",
            external_id="portfolio-2",
            name="Portfolio",
            created_at=created_at + timedelta(minutes=1),
            updated_at=created_at,
        )


def test_position_snapshot_requires_exactly_one_asset_identity() -> None:
    common = {
        "portfolio_id": uuid4(),
        "snapshot_batch_id": uuid4(),
        "snapshot_time": datetime(2026, 9, 3, tzinfo=UTC),
        "source_type": " Manual ",
        "source_reference": " source-1 ",
    }
    resolved = PositionSnapshotDTO(asset_id=uuid4(), **common)
    unresolved = PositionSnapshotDTO(asset_reference_id=uuid4(), **common)

    assert resolved.asset_reference_id is None
    assert unresolved.asset_id is None
    assert unresolved.source_type == "manual"
    assert unresolved.source_reference == "source-1"

    with pytest.raises(ValidationError):
        PositionSnapshotDTO(**common)
    with pytest.raises(ValidationError):
        PositionSnapshotDTO(asset_id=uuid4(), asset_reference_id=uuid4(), **common)


def test_portfolio_action_derives_effective_time_from_snapshot_time() -> None:
    snapshot_time = datetime(2026, 9, 3, 10, tzinfo=UTC)
    previous_batch_id = uuid4()
    current_batch_id = uuid4()
    current_position_id = uuid4()
    action = PortfolioActionDTO(
        portfolio_id=uuid4(),
        asset_id=uuid4(),
        previous_snapshot_batch_id=previous_batch_id,
        current_snapshot_batch_id=current_batch_id,
        current_position_snapshot_id=current_position_id,
        action_type=PortfolioActionType.POSITION_ADDED,
        effective_time=snapshot_time,
        calculated_at=datetime(2026, 9, 3, 11, tzinfo=UTC),
    )

    assert action.effective_time == snapshot_time
    assert action.action_type is PortfolioActionType.POSITION_ADDED
    assert action.current_position_snapshot_id == current_position_id
    assert action.calculated_at != action.effective_time


def test_snapshot_batch_and_import_result_are_batch_scoped() -> None:
    batch_time = datetime(2026, 9, 3, 10, tzinfo=UTC)
    batch = PortfolioSnapshotBatchDTO(
        portfolio_id=uuid4(),
        snapshot_time=batch_time,
        source=" XUEQIU ",
        external_id=" batch-1 ",
    )
    result = PortfolioSnapshotImportResult(
        portfolio_id=batch.portfolio_id,
        snapshot_batch_id=uuid4(),
        portfolio_created=True,
        batch_created=True,
        batch_reused=False,
        position_snapshot_ids=(uuid4(),),
        created_count=1,
        reused_count=0,
        resolved_count=1,
        unresolved_count=0,
    )

    assert batch.source == "xueqiu"
    assert batch.external_id == "batch-1"
    assert batch.snapshot_time == batch_time
    assert result.batch_id == result.snapshot_batch_id
    with pytest.raises(ValidationError):
        result.position_snapshot_ids += (uuid4(),)


def test_investor_action_claim_preserves_event_provenance_and_identity_rules() -> None:
    claim = InvestorActionClaimDTO(
        investor_id=uuid4(),
        asset_reference_id=uuid4(),
        event_id=uuid4(),
        claim_type=InvestorActionClaimType.BUY,
        confidence=0.8,
        evidence_text="I bought the position",
        published_time=datetime(2026, 9, 3, tzinfo=UTC),
        analysis_version="opinion-analysis-v3",
    )

    assert claim.event_id is not None
    assert claim.asset_id is None
    assert claim.evidence_text == "I bought the position"
    with pytest.raises(ValidationError):
        invalid_claim = claim.model_dump()
        invalid_claim["asset_id"] = uuid4()
        InvestorActionClaimDTO(
            **invalid_claim,
        )
