from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    AnalysisSpec,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    OpinionDirection,
    UnresolvedAsset,
)
from database.models import (
    Asset,
    AssetAlias,
    AttentionOccurrence,
    EventAnalysis,
    Investor,
    InvestorAssetState,
    InvestorAssetStateChange,
    Opinion,
    RawEvent,
)
from database.unit_of_work import (
    SqlAlchemyAttentionUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
)
from intelligence import AttentionOccurrenceService, StateUpdateService
from pipeline import RecoveryReconciliationService
from resolution import AssetRecoveryService

ACTIVE_SPEC = AnalysisSpec.from_model_version("recovery-active-v1")
POLICY = EffectiveAnalysisPolicy(active_spec=ACTIVE_SPEC)


def build_workflow(factory: sessionmaker[Session]) -> RecoveryReconciliationService:
    return RecoveryReconciliationService(
        AssetRecoveryService(lambda: SqlAlchemyOpinionUnitOfWork(factory)),
        StateUpdateService(lambda: SqlAlchemyStateUnitOfWork(factory), POLICY),
        AttentionOccurrenceService(
            lambda: SqlAlchemyAttentionUnitOfWork(factory),
            POLICY,
        ),
    )


def test_recovery_reconciliation_uses_original_fact_time_and_is_idempotent(
    db_session_factory: sessionmaker[Session],
) -> None:
    published_time = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    generated_time = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
    with db_session_factory() as session:
        investor = Investor(
            name="Recovery Reconciliation Investor",
            platform="manual",
            platform_user_id="recovery-reconciliation",
        )
        asset = Asset(name="Tencent Holdings", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.flush()
        session.add(
            AssetAlias(
                asset_id=asset.id,
                alias="腾讯",
                normalized_alias="腾讯",
                alias_type="NAME",
                market="HK",
            )
        )
        event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="manual",
            url="https://example.test/recovery-reconciliation",
            published_time=published_time,
            content="腾讯长期增长值得关注。",
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
            collected_time=published_time,
        )
        session.add(event)
        session.flush()
        unresolved = UnresolvedAsset(
            asset_name="腾讯",
            direction=OpinionDirection.BULLISH,
            strength=75,
            confidence=0.8,
            thesis=("长期增长",),
        )
        analysis = EventAnalysis(
            event_id=event.id,
            analysis_version=ACTIVE_SPEC.analysis_version,
            model_version=ACTIVE_SPEC.model_version,
            prompt_version=ACTIVE_SPEC.prompt_version,
            schema_version=ACTIVE_SPEC.schema_version,
            status=EventAnalysisStatus.PARTIALLY_RESOLVED,
            investment_related=True,
            generated_time=generated_time,
            calculated_at=generated_time,
            confidence=0.8,
            structured_output={
                "analysis_spec": ACTIVE_SPEC.model_dump(mode="json"),
                "unresolved_assets": [unresolved.model_dump(mode="json")],
            },
            provider_metadata={},
        )
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id
        asset_id = asset.id

    workflow = build_workflow(db_session_factory)
    first = workflow.reconcile(analysis_id=analysis_id)
    second = workflow.reconcile(analysis_id=analysis_id)

    assert first.recovery.created_count == 1
    assert second.recovery.created_count == 0
    assert second.recovery.reused_count == 1
    assert first.affected_asset_ids == (asset_id,)
    assert first.skipped_inactive_opinion_ids == ()
    assert first.state_updates[0].after.last_activity_time == published_time
    with db_session_factory() as session:
        opinion = session.scalar(select(Opinion).where(Opinion.analysis_id == analysis_id))
        state = session.scalar(select(InvestorAssetState))
        occurrence = session.scalar(select(AttentionOccurrence))
        state_change = session.scalar(select(InvestorAssetStateChange))
        assert opinion is not None
        assert opinion.generated_time.replace(tzinfo=UTC) == generated_time
        assert state is not None and state.last_activity_time.replace(tzinfo=UTC) == published_time
        assert occurrence is not None
        assert occurrence.published_time.replace(tzinfo=UTC) == published_time
        assert state_change is not None
        assert state_change.effective_time.replace(tzinfo=UTC) == published_time
        assert session.scalar(select(func.count()).select_from(Opinion)) == 1
        assert session.scalar(select(func.count()).select_from(AttentionOccurrence)) == 1
        assert session.scalar(select(func.count()).select_from(InvestorAssetStateChange)) == 1
