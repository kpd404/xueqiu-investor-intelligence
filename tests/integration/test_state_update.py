import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from collectors import ManualImportAdapter
from contracts import (
    AnalysisSpec,
    AttentionLevel,
    CollectionRequest,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    OpinionCreate,
    OpinionDirection,
    PositionStatus,
    StateTransitionType,
)
from database.models import Asset, EventAnalysis, Investor, InvestorAssetState
from database.repositories import (
    InvestorAssetStateRepository,
    OpinionRepository,
    RawEventRepository,
)
from database.unit_of_work import SqlAlchemyStateUnitOfWork
from intelligence import StateUpdateService
from pipeline import DataPipeline

ACTIVE_SPEC = AnalysisSpec.from_model_version("state-fixture-v1")
EFFECTIVE_POLICY = EffectiveAnalysisPolicy(active_spec=ACTIVE_SPEC)


def seed_investor_asset(factory: sessionmaker[Session]) -> tuple[UUID, UUID]:
    with factory() as session:
        investor = Investor(
            name="State Test Investor",
            platform="manual",
            platform_user_id="state-test-investor",
        )
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.commit()
        return investor.id, asset.id


def add_opinion(
    factory: sessionmaker[Session],
    *,
    investor_id: UUID,
    asset_id: UUID,
    direction: OpinionDirection,
    published_time: datetime,
    strength: float = 80,
    confidence: float = 0.9,
) -> tuple[UUID, UUID]:
    with factory() as session:
        adapter = ManualImportAdapter(
            content=f"Ordinary post opinion: {direction.value}",
            published_time=published_time,
            url=f"https://example.test/state-events/{uuid4()}",
        )
        request = CollectionRequest(
            investor_id=investor_id,
            platform_user_id="state-test-investor",
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
            confidence=confidence,
            structured_output={"analysis_spec": ACTIVE_SPEC.model_dump(mode="json")},
            provider_metadata={},
        )
        session.add(analysis)
        session.flush()

        opinion_result = OpinionRepository(session).add_many(
            [
                OpinionCreate(
                    event_id=event_id,
                    analysis_id=analysis.id,
                    investor_id=investor_id,
                    asset_id=asset_id,
                    direction=direction,
                    strength=strength,
                    confidence=confidence,
                    model_version=ACTIVE_SPEC.model_version,
                    generated_time=published_time + timedelta(hours=1),
                )
            ]
        )
        session.commit()
        return opinion_result.opinion_ids[0], event_id


def build_state_service(factory: sessionmaker[Session]) -> StateUpdateService:
    def unit_of_work_factory() -> SqlAlchemyStateUnitOfWork:
        return SqlAlchemyStateUnitOfWork(factory)

    return StateUpdateService(unit_of_work_factory, EFFECTIVE_POLICY)


def test_first_asset_opinion_creates_new_attention(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id = seed_investor_asset(db_session_factory)
    opinion_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.NEUTRAL,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )

    result = build_state_service(db_session_factory).update(opinion_id)

    assert result.transition == StateTransitionType.NEW_ATTENTION
    assert result.changed is True
    assert result.before is None
    assert result.after.attention_level == AttentionLevel.DISCOVERED
    assert result.after.mention_count == 1
    assert result.after.position_status == PositionStatus.NO_POSITION


def test_neutral_to_bullish_is_opinion_upgrade(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id = seed_investor_asset(db_session_factory)
    neutral_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.NEUTRAL,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )
    service = build_state_service(db_session_factory)
    service.update(neutral_id)
    bullish_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 21, tzinfo=UTC),
    )

    result = service.update(bullish_id)

    assert result.transition == StateTransitionType.OPINION_UPGRADE
    assert result.before is not None
    assert result.before.direction == OpinionDirection.NEUTRAL
    assert result.after.direction == OpinionDirection.BULLISH


def test_bearish_to_bullish_is_opinion_reversal(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id = seed_investor_asset(db_session_factory)
    bearish_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BEARISH,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )
    service = build_state_service(db_session_factory)
    service.update(bearish_id)
    bullish_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 21, tzinfo=UTC),
    )

    result = service.update(bullish_id)

    assert result.transition == StateTransitionType.OPINION_REVERSAL
    assert result.after.direction == OpinionDirection.BULLISH


def test_repeated_same_direction_is_not_reversal(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id = seed_investor_asset(db_session_factory)
    first_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )
    service = build_state_service(db_session_factory)
    service.update(first_id)
    second_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 21, tzinfo=UTC),
    )

    result = service.update(second_id)

    assert result.transition == StateTransitionType.NO_MATERIAL_CHANGE
    assert result.changed is True
    assert result.after.direction == OpinionDirection.BULLISH
    assert result.after.mention_count == 2
    assert result.after.attention_level == AttentionLevel.TRACKING


def test_repeating_state_update_is_idempotent(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id = seed_investor_asset(db_session_factory)
    opinion_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )
    service = build_state_service(db_session_factory)

    first = service.update(opinion_id)
    second = service.update(opinion_id)

    assert first.changed is True
    assert second.changed is False
    assert second.after.mention_count == first.after.mention_count == 1
    assert second.after.last_change_time == first.after.last_change_time
    assert second.before == second.after
    assert second.state_id == first.state_id

    with db_session_factory() as session:
        state = InvestorAssetStateRepository(session).get(investor_id, asset_id)
        assert state is not None
        assert state.mention_count == 1


def test_last_opinion_time_comes_from_latest_raw_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id = seed_investor_asset(db_session_factory)
    first_time = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    second_time = datetime(2026, 8, 21, 15, 30, tzinfo=UTC)
    first_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.NEUTRAL,
        published_time=first_time,
    )
    service = build_state_service(db_session_factory)
    service.update(first_id)
    second_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=second_time,
    )

    result = service.update(second_id)

    assert result.after.last_opinion_time == second_time
    assert result.after.last_opinion_time != second_time + timedelta(hours=1)


def test_ordinary_post_opinion_preserves_position_status(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id = seed_investor_asset(db_session_factory)
    with db_session_factory() as session:
        session.add(
            InvestorAssetState(
                investor_id=investor_id,
                asset_id=asset_id,
                attention_level=AttentionLevel.UNKNOWN,
                direction=OpinionDirection.NEUTRAL,
                conviction=0,
                mention_count=0,
                position_status=PositionStatus.WATCHING,
            )
        )
        session.commit()
    opinion_id, _ = add_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )

    result = build_state_service(db_session_factory).update(opinion_id)

    assert result.after.position_status == PositionStatus.WATCHING
