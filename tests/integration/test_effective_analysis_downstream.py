from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from contracts import AnalysisSpec, EffectiveAnalysisPolicy, EventAnalysisStatus, OpinionDirection
from database.models import Asset, EventAnalysis, Investor, Opinion, RawEvent
from database.unit_of_work import SqlAlchemyIntelligenceUnitOfWork, SqlAlchemyStateUnitOfWork
from intelligence import AssetIntelligenceService, StateUpdateService
from intelligence.services.state_update import OpinionNotFoundError

ACTIVE_SPEC = AnalysisSpec.from_model_version("effective-active-v1")
OLD_SPEC = AnalysisSpec.from_model_version("effective-old-v1")
POLICY = EffectiveAnalysisPolicy(active_spec=ACTIVE_SPEC)


def add_fact(
    session: Session,
    *,
    investor: Investor,
    asset: Asset,
    spec: AnalysisSpec,
    direction: OpinionDirection,
    published_time: datetime,
    status: EventAnalysisStatus = EventAnalysisStatus.SUCCESS,
    generated_offset_days: int = 0,
) -> Opinion:
    event = RawEvent(
        investor_id=investor.id,
        event_type="POST",
        source="manual",
        url=f"https://example.test/effective/{uuid4()}",
        published_time=published_time,
        content=f"{spec.analysis_version} {direction.value}",
        raw_data={},
        hash=uuid4().hex + uuid4().hex,
        collected_time=published_time,
    )
    session.add(event)
    session.flush()
    generated_time = published_time + timedelta(days=generated_offset_days)
    analysis = EventAnalysis(
        event_id=event.id,
        analysis_version=spec.analysis_version,
        model_version=spec.model_version,
        prompt_version=spec.prompt_version,
        schema_version=spec.schema_version,
        status=status,
        investment_related=True,
        generated_time=generated_time,
        calculated_at=generated_time,
        confidence=0.8,
        structured_output={"analysis_spec": spec.model_dump(mode="json")},
        provider_metadata={},
    )
    session.add(analysis)
    session.flush()
    opinion = Opinion(
        event_id=event.id,
        analysis_id=analysis.id,
        investor_id=investor.id,
        asset_id=asset.id,
        direction=direction,
        strength=70,
        confidence=0.8,
        thesis=[direction.value],
        catalysts=[],
        risks=[],
        generated_time=generated_time,
        model_version=spec.model_version,
    )
    session.add(opinion)
    session.flush()
    return opinion


def test_state_and_historical_replay_only_use_active_analysis(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        investor = Investor(
            name="Effective Investor",
            platform="manual",
            platform_user_id="effective-one",
            quality_score=80,
        )
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.flush()
        inactive = add_fact(
            session,
            investor=investor,
            asset=asset,
            spec=OLD_SPEC,
            direction=OpinionDirection.BEARISH,
            published_time=datetime(2026, 8, 1, tzinfo=UTC),
            generated_offset_days=30,
        )
        active = add_fact(
            session,
            investor=investor,
            asset=asset,
            spec=ACTIVE_SPEC,
            direction=OpinionDirection.BULLISH,
            published_time=datetime(2026, 8, 2, tzinfo=UTC),
        )
        session.commit()
        asset_id = asset.id

    state = StateUpdateService(
        lambda: SqlAlchemyStateUnitOfWork(db_session_factory),
        POLICY,
    )
    result = state.update(active.id)

    assert result.after.direction is OpinionDirection.BULLISH
    assert result.after.mention_count == 1
    assert result.applied_opinion_ids == (active.id,)
    with pytest.raises(OpinionNotFoundError):
        state.update(inactive.id)

    snapshot = AssetIntelligenceService(
        lambda: SqlAlchemyIntelligenceUnitOfWork(db_session_factory),
        POLICY,
    ).build(asset_id, datetime(2026, 9, 1, tzinfo=UTC))
    assert snapshot.observed_investor_count == 1
    assert snapshot.investor_states[0].direction is OpinionDirection.BULLISH
    assert snapshot.investor_states[0].mention_count == 1


def test_failed_active_analysis_does_not_fallback_to_old_success(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        investor = Investor(
            name="No Fallback Investor",
            platform="manual",
            platform_user_id="effective-two",
            quality_score=80,
        )
        asset = Asset(name="No Fallback", symbol="NF", market="HK")
        session.add_all([investor, asset])
        session.flush()
        add_fact(
            session,
            investor=investor,
            asset=asset,
            spec=OLD_SPEC,
            direction=OpinionDirection.BULLISH,
            published_time=datetime(2026, 8, 1, tzinfo=UTC),
        )
        failed_active = add_fact(
            session,
            investor=investor,
            asset=asset,
            spec=ACTIVE_SPEC,
            direction=OpinionDirection.BEARISH,
            published_time=datetime(2026, 8, 2, tzinfo=UTC),
            status=EventAnalysisStatus.FAILED,
        )
        session.commit()
        asset_id = asset.id

    state = StateUpdateService(
        lambda: SqlAlchemyStateUnitOfWork(db_session_factory),
        POLICY,
    )
    with pytest.raises(OpinionNotFoundError):
        state.update(failed_active.id)

    snapshot = AssetIntelligenceService(
        lambda: SqlAlchemyIntelligenceUnitOfWork(db_session_factory),
        POLICY,
    ).build(asset_id, datetime(2026, 9, 1, tzinfo=UTC))
    assert snapshot.observed_investor_count == 0
    assert snapshot.investor_states == ()
