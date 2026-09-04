from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.base import Base
from database.models import (
    Asset,
    AssetAlias,
    CrossInvestorAssetAlignment,
    EventAnalysis,
    Investor,
    InvestorActionClaim,
    InvestorActionConsistency,
    InvestorBehaviorSnapshot,
    Opinion,
    Portfolio,
    PortfolioAction,
    PortfolioSnapshotBatch,
    PositionSnapshot,
    RawEvent,
    RawEventImmutableError,
    ThesisChange,
)
from database.models.enums import EventType, OpinionDirection


def test_metadata_contains_mvp_tables_and_temporal_processing_tables() -> None:
    assert set(Base.metadata.tables) == {
        "assets",
        "asset_aliases",
        "attention_occurrences",
        "investors",
        "investor_asset_states",
        "investor_asset_state_changes",
        "opinions",
        "event_analyses",
        "portfolio",
        "position_snapshots",
        "portfolio_actions",
        "portfolio_snapshot_batches",
        "investor_action_claims",
        "investor_action_consistencies",
        "investor_behavior_snapshots",
        "cross_investor_asset_snapshots",
        "cross_investor_asset_alignments",
        "raw_events",
        "signals",
        "thesis_changes",
    }


def test_core_fact_and_interpretation_records_are_traceable(db_session: Session) -> None:
    investor = Investor(name="Example Investor", platform="xueqiu", platform_user_id="42")
    asset = Asset(name="Tencent Holdings", symbol="00700", market="HK")
    db_session.add_all([investor, asset])
    db_session.flush()

    raw_event = RawEvent(
        investor_id=investor.id,
        event_type=EventType.POST,
        source="xueqiu",
        url="https://example.test/posts/1",
        published_time=datetime.now(UTC),
        content="Example raw fact",
        raw_data={"source_id": "1"},
        hash="a" * 64,
    )
    db_session.add(raw_event)
    db_session.flush()

    opinion = Opinion(
        event_id=raw_event.id,
        investor_id=investor.id,
        asset_id=asset.id,
        direction=OpinionDirection.BULLISH,
        strength=85.0,
        confidence=0.91,
        thesis=["AI commercialization"],
        catalysts=["Advertising recovery"],
        risks=["Regulation"],
        time_horizon="LONG_TERM",
        model_version="bootstrap-test-model",
    )
    db_session.add(opinion)
    db_session.commit()

    assert opinion.event_id == raw_event.id
    assert opinion.investor_id == raw_event.investor_id == investor.id
    assert opinion.asset_id == asset.id
    assert opinion.generated_time is not None
    assert opinion.analysis_id is None


def test_raw_event_is_immutable_after_persistence(db_session: Session) -> None:
    investor = Investor(name="Example Investor", platform="manual", platform_user_id="1")
    db_session.add(investor)
    db_session.flush()
    raw_event = RawEvent(
        investor_id=investor.id,
        event_type=EventType.ARTICLE,
        source="manual",
        url="https://example.test/articles/1",
        published_time=datetime.now(UTC),
        content="Original content",
        raw_data={},
        hash="b" * 64,
    )
    db_session.add(raw_event)
    db_session.commit()

    raw_event.content = "Mutated content"
    with pytest.raises(RawEventImmutableError):
        db_session.commit()
    db_session.rollback()


def test_opinion_schema_has_ai_provenance_fields() -> None:
    columns = {column.name for column in inspect(Opinion).columns}
    assert {"event_id", "analysis_id", "confidence", "generated_time", "model_version"} <= columns
    assert {"event_id", "analysis_version", "status", "structured_output"} <= {
        column.name for column in inspect(EventAnalysis).columns
    }
    assert {
        "previous_opinion_id",
        "current_opinion_id",
        "effective_time",
        "comparison_version",
        "input_identity",
    } <= {column.name for column in inspect(ThesisChange).columns}


def test_portfolio_fact_models_have_expected_identity_fields() -> None:
    assert {
        "investor_id",
        "source",
        "external_id",
        "status",
        "created_at",
        "updated_at",
    } <= {column.name for column in inspect(Portfolio).columns}
    assert {
        "portfolio_id",
        "snapshot_time",
        "source",
        "external_id",
        "completeness",
        "created_at",
    } <= {column.name for column in inspect(PortfolioSnapshotBatch).columns}
    assert {
        "portfolio_id",
        "snapshot_batch_id",
        "asset_id",
        "asset_reference_id",
        "snapshot_time",
        "source_type",
        "source_reference",
    } <= {column.name for column in inspect(PositionSnapshot).columns}
    assert {
        "portfolio_id",
        "previous_snapshot_batch_id",
        "current_snapshot_batch_id",
        "previous_position_snapshot_id",
        "current_position_snapshot_id",
        "asset_reference_id",
        "asset_id",
        "previous_snapshot_id",
        "current_snapshot_id",
        "action_type",
        "effective_time",
        "calculated_at",
    } <= {column.name for column in inspect(PortfolioAction).columns}
    assert {
        "investor_id",
        "asset_id",
        "asset_reference_id",
        "event_id",
        "claim_type",
        "evidence_text",
        "published_time",
        "analysis_version",
    } <= {column.name for column in inspect(InvestorActionClaim).columns}
    assert {
        "investor_id",
        "asset_id",
        "opinion_id",
        "portfolio_action_id",
        "consistency_type",
        "effective_time",
        "opinion_analysis_version",
        "consistency_policy_version",
        "input_identity",
    } <= {column.name for column in inspect(InvestorActionConsistency).columns}
    assert {
        "asset_id",
        "source_snapshot_id",
        "opinion_coverage_state",
        "directional_alignment_state",
        "alignment_policy_version",
        "input_identity",
        "calculated_at",
        "created_at",
    } <= {column.name for column in inspect(CrossInvestorAssetAlignment).columns}
    alignment_constraints = {
        constraint.name for constraint in CrossInvestorAssetAlignment.__table__.constraints
    }
    assert "cross_investor_asset_alignment_input_identity" in alignment_constraints
    assert {
        "investor_id",
        "as_of",
        "window_start",
        "window_end",
        "attention_asset_count",
        "opinion_count",
        "behavior_policy_version",
        "calculated_at",
        "input_identity",
        "active_analysis_version",
        "thesis_comparison_version",
        "consistency_policy_version",
        "attention_policy_version",
    } <= {column.name for column in inspect(InvestorBehaviorSnapshot).columns}
    unique_constraints = {
        constraint.name for constraint in InvestorBehaviorSnapshot.__table__.constraints
    }
    assert "investor_behavior_snapshot_input_identity" in unique_constraints
    assert "investor_behavior_snapshot_identity" not in unique_constraints


def test_asset_alias_is_scoped_to_asset_and_normalized_identity(db_session: Session) -> None:
    asset = Asset(name="Tencent Holdings", symbol="00700", market="HK")
    db_session.add(asset)
    db_session.flush()
    db_session.add(
        AssetAlias(
            asset_id=asset.id,
            alias="Tencent",
            normalized_alias="TENCENT",
            alias_type="NAME",
            market="HK",
        )
    )
    db_session.commit()

    assert asset.aliases[0].normalized_alias == "TENCENT"

    db_session.add(
        AssetAlias(
            asset_id=asset.id,
            alias="Tencent Holdings",
            normalized_alias="TENCENT",
            alias_type="NAME",
            market="SH",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    second_asset = Asset(name="Another Tencent", symbol="TENCENT-ALT", market="HK")
    db_session.add(second_asset)
    db_session.flush()
    db_session.add(
        AssetAlias(
            asset_id=second_asset.id,
            alias="Tencent",
            normalized_alias="TENCENT",
            alias_type="NAME",
            market="HK",
        )
    )
    db_session.commit()

    assert len(db_session.query(AssetAlias).filter_by(normalized_alias="TENCENT").all()) == 2
