import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from collectors import ManualImportAdapter
from contracts import (
    AnalysisSpec,
    AttentionLevel,
    CollectionRequest,
    ConsensusDirection,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    OpinionCreate,
    OpinionDirection,
    PositionStatus,
)
from database.models import Asset, EventAnalysis, Investor, InvestorAssetState
from database.repositories import OpinionRepository, RawEventRepository
from database.unit_of_work import (
    SqlAlchemyIntelligenceUnitOfWork,
    SqlAlchemyStateUnitOfWork,
)
from intelligence import AssetIntelligenceService, StateUpdateService
from pipeline import DataPipeline

AS_OF = datetime(2026, 8, 25, tzinfo=UTC)
ACTIVE_SPEC = AnalysisSpec.from_model_version("intelligence-fixture-v1")
EFFECTIVE_POLICY = EffectiveAnalysisPolicy(active_spec=ACTIVE_SPEC)


def seed_asset(factory: sessionmaker[Session]) -> UUID:
    with factory() as session:
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add(asset)
        session.commit()
        return asset.id


def add_investor_state(
    factory: sessionmaker[Session],
    *,
    asset_id: UUID,
    direction: OpinionDirection,
    quality_score: float | None,
    published_time: datetime,
) -> UUID:
    platform_user_id = f"intelligence-investor-{uuid4()}"
    with factory() as session:
        investor = Investor(
            name=platform_user_id,
            platform="manual",
            platform_user_id=platform_user_id,
            quality_score=quality_score,
        )
        session.add(investor)
        session.commit()

        adapter = ManualImportAdapter(
            content=f"Intelligence fixture: {direction.value}",
            published_time=published_time,
            url=f"https://example.test/intelligence-events/{uuid4()}",
        )
        request = CollectionRequest(
            investor_id=investor.id,
            platform_user_id=investor.platform_user_id,
        )
        raw_pipeline = DataPipeline(RawEventRepository(session), session)
        event_id = asyncio.run(raw_pipeline.run(adapter, request)).events[0].event_id

        analysis = EventAnalysis(
            event_id=event_id,
            analysis_version=ACTIVE_SPEC.analysis_version,
            model_version=ACTIVE_SPEC.model_version,
            prompt_version=ACTIVE_SPEC.prompt_version,
            schema_version=ACTIVE_SPEC.schema_version,
            status=EventAnalysisStatus.SUCCESS,
            investment_related=True,
            generated_time=published_time + timedelta(hours=1),
            calculated_at=published_time + timedelta(hours=1),
            confidence=0.9,
            structured_output={"analysis_spec": ACTIVE_SPEC.model_dump(mode="json")},
            provider_metadata={},
        )
        session.add(analysis)
        session.flush()

        write_result = OpinionRepository(session).add_many(
            [
                OpinionCreate(
                    event_id=event_id,
                    analysis_id=analysis.id,
                    investor_id=investor.id,
                    asset_id=asset_id,
                    direction=direction,
                    strength=80,
                    confidence=0.9,
                    generated_time=published_time + timedelta(hours=1),
                    model_version=ACTIVE_SPEC.model_version,
                )
            ]
        )
        session.commit()
        opinion_id = write_result.opinion_ids[0]

    def state_unit_of_work_factory() -> SqlAlchemyStateUnitOfWork:
        return SqlAlchemyStateUnitOfWork(factory)

    StateUpdateService(state_unit_of_work_factory, EFFECTIVE_POLICY).update(opinion_id)
    return event_id


def build_service(factory: sessionmaker[Session]) -> AssetIntelligenceService:
    def unit_of_work_factory() -> SqlAlchemyIntelligenceUnitOfWork:
        return SqlAlchemyIntelligenceUnitOfWork(factory)

    return AssetIntelligenceService(unit_of_work_factory, EFFECTIVE_POLICY)


def test_one_bullish_investor_is_insufficient_data(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    add_investor_state(
        db_session_factory,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        quality_score=90,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )

    snapshot = build_service(db_session_factory).build(asset_id, AS_OF)

    assert snapshot.observed_investor_count == 1
    assert snapshot.active_investor_count == 1
    assert snapshot.bullish_count == 1
    assert snapshot.consensus_direction == ConsensusDirection.INSUFFICIENT_DATA
    assert snapshot.consensus_strength == 0


def test_two_bullish_and_one_neutral_produce_bullish_consensus(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    for index, direction in enumerate(
        [OpinionDirection.BULLISH, OpinionDirection.BULLISH, OpinionDirection.NEUTRAL]
    ):
        add_investor_state(
            db_session_factory,
            asset_id=asset_id,
            direction=direction,
            quality_score=None,
            published_time=datetime(2026, 8, 20 + index, tzinfo=UTC),
        )

    snapshot = build_service(db_session_factory).build(asset_id, AS_OF)

    assert snapshot.observed_investor_count == 3
    assert snapshot.active_investor_count == 3
    assert snapshot.bullish_count == 2
    assert snapshot.neutral_count == 1
    assert snapshot.bearish_count == 0
    assert snapshot.weighted_bullish == 1.0
    assert snapshot.weighted_neutral == 0.5
    assert snapshot.consensus_direction == ConsensusDirection.BULLISH
    assert snapshot.consensus_strength == 33.3333


def test_close_bullish_and_bearish_weights_are_mixed(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    for direction in [OpinionDirection.BULLISH, OpinionDirection.BEARISH]:
        add_investor_state(
            db_session_factory,
            asset_id=asset_id,
            direction=direction,
            quality_score=50,
            published_time=datetime(2026, 8, 20, tzinfo=UTC),
        )

    snapshot = build_service(db_session_factory).build(asset_id, AS_OF)

    assert snapshot.weighted_bullish == snapshot.weighted_bearish == 0.5
    assert snapshot.consensus_direction == ConsensusDirection.MIXED
    assert snapshot.consensus_strength == 0


def test_high_quality_investor_has_more_weight_than_low_quality_investor(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    add_investor_state(
        db_session_factory,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        quality_score=90,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )
    add_investor_state(
        db_session_factory,
        asset_id=asset_id,
        direction=OpinionDirection.BEARISH,
        quality_score=10,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )

    snapshot = build_service(db_session_factory).build(asset_id, AS_OF)

    assert snapshot.bullish_count == snapshot.bearish_count == 1
    assert snapshot.weighted_bullish == 0.9
    assert snapshot.weighted_bearish == 0.1
    assert snapshot.consensus_direction == ConsensusDirection.BULLISH
    assert snapshot.consensus_strength == 80


def test_repeated_calculation_returns_identical_snapshot(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    for direction in [OpinionDirection.BULLISH, OpinionDirection.BULLISH]:
        add_investor_state(
            db_session_factory,
            asset_id=asset_id,
            direction=direction,
            quality_score=50,
            published_time=datetime(2026, 8, 20, tzinfo=UTC),
        )
    service = build_service(db_session_factory)

    first = service.build(asset_id, AS_OF)
    second = service.build(asset_id, AS_OF)

    assert first == second


def test_source_event_ids_reference_real_raw_events(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    expected_event_ids = {
        add_investor_state(
            db_session_factory,
            asset_id=asset_id,
            direction=direction,
            quality_score=50,
            published_time=datetime(2026, 8, 20, tzinfo=UTC),
        )
        for direction in [OpinionDirection.BULLISH, OpinionDirection.NEUTRAL]
    }

    snapshot = build_service(db_session_factory).build(asset_id, AS_OF)

    assert set(snapshot.source_event_ids) == expected_event_ids
    assert {
        event_id
        for contribution in snapshot.investor_states
        for event_id in contribution.source_event_ids
    } == expected_event_ids

    with db_session_factory() as session:
        assert all(
            RawEventRepository(session).get(event_id) is not None for event_id in expected_event_ids
        )


def test_no_valid_state_is_insufficient_data(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    with db_session_factory() as session:
        investor = Investor(
            name="No Evidence Investor",
            platform="manual",
            platform_user_id="no-evidence-investor",
            quality_score=100,
        )
        session.add(investor)
        session.flush()
        session.add(
            InvestorAssetState(
                investor_id=investor.id,
                asset_id=asset_id,
                attention_level=AttentionLevel.UNKNOWN,
                direction=OpinionDirection.BULLISH,
                conviction=100,
                mention_count=0,
                position_status=PositionStatus.NO_POSITION,
            )
        )
        session.commit()

    snapshot = build_service(db_session_factory).build(asset_id, AS_OF)

    assert snapshot.observed_investor_count == 0
    assert snapshot.active_investor_count == 0
    assert snapshot.investor_states == ()
    assert snapshot.source_event_ids == ()
    assert snapshot.consensus_direction == ConsensusDirection.INSUFFICIENT_DATA
