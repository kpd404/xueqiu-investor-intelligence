import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai import MockOpinionExtractor, OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import (
    AssetOpinionExtraction,
    CollectionRequest,
    ConsensusDirection,
    OpinionDirection,
    OpinionExtractionResult,
    OpinionProcessingStatus,
    ProcessRawEventCommand,
    RawEventView,
)
from database.models import Asset, Investor, InvestorAssetState, Opinion, RawEvent
from database.repositories import RawEventRepository
from database.unit_of_work import (
    SqlAlchemyIntelligenceUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
)
from intelligence import AssetIntelligenceService, StateUpdateService
from pipeline import DataPipeline, IntelligencePipeline

MOCK_VERSION = "mock-opinion-v1"
FIXTURE_VERSION = "core-fixture-v1"
AS_OF = datetime(2026, 8, 25, tzinfo=UTC)


class DirectionalFixtureExtractor:
    async def extract(self, event: RawEventView) -> OpinionExtractionResult:
        direction = (
            OpinionDirection.NEUTRAL
            if "DIRECTION:NEUTRAL" in event.content
            else OpinionDirection.BULLISH
        )
        opinions = [
            AssetOpinionExtraction(
                asset_name="Tencent",
                symbol="00700",
                market="HK",
                direction=direction,
                strength=80 if direction == OpinionDirection.BULLISH else 50,
                confidence=0.9,
                thesis=("Core pipeline fixture",),
            )
        ]
        if "UNRESOLVED" in event.content:
            opinions.append(
                AssetOpinionExtraction(
                    asset_name="Unknown Asset",
                    symbol="UNKNOWN",
                    market="HK",
                    direction=OpinionDirection.BULLISH,
                    strength=60,
                    confidence=0.8,
                )
            )
        return OpinionExtractionResult(
            investment_related=True,
            opinions=tuple(opinions),
            model_version=FIXTURE_VERSION,
        )


def build_pipeline(
    factory: sessionmaker[Session],
    extractor: object,
) -> IntelligencePipeline:
    def opinion_unit_of_work() -> SqlAlchemyOpinionUnitOfWork:
        return SqlAlchemyOpinionUnitOfWork(factory)

    def state_unit_of_work() -> SqlAlchemyStateUnitOfWork:
        return SqlAlchemyStateUnitOfWork(factory)

    def intelligence_unit_of_work() -> SqlAlchemyIntelligenceUnitOfWork:
        return SqlAlchemyIntelligenceUnitOfWork(factory)

    return IntelligencePipeline(
        OpinionProcessingService(extractor, opinion_unit_of_work),  # type: ignore[arg-type]
        StateUpdateService(state_unit_of_work),
        AssetIntelligenceService(intelligence_unit_of_work),
    )


def seed_asset(factory: sessionmaker[Session]) -> UUID:
    with factory() as session:
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add(asset)
        session.commit()
        return asset.id


def seed_investor(
    factory: sessionmaker[Session],
    *,
    quality_score: float,
) -> Investor:
    with factory() as session:
        investor = Investor(
            name="Core Pipeline Investor",
            platform="manual",
            platform_user_id=f"core-{uuid4()}",
            quality_score=quality_score,
        )
        session.add(investor)
        session.commit()
        return investor


def persist_raw_event(
    factory: sessionmaker[Session],
    *,
    investor: Investor,
    content: str,
    published_time: datetime,
) -> UUID:
    with factory() as session:
        adapter = ManualImportAdapter(
            content=content,
            published_time=published_time,
            url=f"https://example.test/core-events/{uuid4()}",
        )
        request = CollectionRequest(
            investor_id=investor.id,
            platform_user_id=investor.platform_user_id,
            limit=1,
        )
        result = asyncio.run(
            DataPipeline(RawEventRepository(session), session).run(adapter, request)
        )
        return result.events[0].event_id


def test_raw_event_runs_through_complete_core_pipeline(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    investor = seed_investor(db_session_factory, quality_score=80)
    event_id = persist_raw_event(
        db_session_factory,
        investor=investor,
        content="腾讯AI商业化空间正在扩大，广告恢复可能推动盈利改善。",
        published_time=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
    )

    result = asyncio.run(
        build_pipeline(db_session_factory, MockOpinionExtractor(MOCK_VERSION)).process(
            ProcessRawEventCommand(
                event_id=event_id,
                model_version=MOCK_VERSION,
                as_of=AS_OF,
            )
        )
    )

    assert result.opinion_processing_status == OpinionProcessingStatus.PROCESSED
    assert len(result.opinion_ids) == 1
    assert len(result.state_updates) == 1
    assert result.affected_asset_ids == (asset_id,)
    assert len(result.asset_intelligence_snapshots) == 1
    snapshot = result.asset_intelligence_snapshots[0]
    assert snapshot.asset_id == asset_id
    assert snapshot.active_investor_count == 1
    assert snapshot.consensus_direction == ConsensusDirection.INSUFFICIENT_DATA
    assert event_id in snapshot.source_event_ids
    assert result.warnings == ()


def test_multiple_investors_produce_bullish_asset_consensus(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    pipeline = build_pipeline(db_session_factory, DirectionalFixtureExtractor())
    event_ids: set[UUID] = set()
    final_result = None

    for index, direction in enumerate(["BULLISH", "BULLISH", "NEUTRAL"]):
        investor = seed_investor(db_session_factory, quality_score=80)
        event_id = persist_raw_event(
            db_session_factory,
            investor=investor,
            content=f"DIRECTION:{direction}",
            published_time=datetime(2026, 8, 22, tzinfo=UTC) + timedelta(days=index),
        )
        event_ids.add(event_id)
        final_result = asyncio.run(
            pipeline.process(
                ProcessRawEventCommand(
                    event_id=event_id,
                    model_version=FIXTURE_VERSION,
                    as_of=AS_OF,
                )
            )
        )

    assert final_result is not None
    snapshot = final_result.asset_intelligence_snapshots[0]
    assert snapshot.asset_id == asset_id
    assert snapshot.active_investor_count == 3
    assert snapshot.bullish_count == 2
    assert snapshot.neutral_count == 1
    assert snapshot.consensus_direction == ConsensusDirection.BULLISH
    assert set(snapshot.source_event_ids) == event_ids


def test_reprocessing_same_event_is_fully_idempotent(
    db_session_factory: sessionmaker[Session],
) -> None:
    seed_asset(db_session_factory)
    investor = seed_investor(db_session_factory, quality_score=80)
    event_id = persist_raw_event(
        db_session_factory,
        investor=investor,
        content="腾讯AI商业化空间正在扩大，广告恢复可能推动盈利改善。",
        published_time=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
    )
    pipeline = build_pipeline(db_session_factory, MockOpinionExtractor(MOCK_VERSION))
    command = ProcessRawEventCommand(
        event_id=event_id,
        model_version=MOCK_VERSION,
        as_of=AS_OF,
    )

    first = asyncio.run(pipeline.process(command))
    second = asyncio.run(pipeline.process(command))

    assert first.opinion_processing_status == OpinionProcessingStatus.PROCESSED
    assert second.opinion_processing_status == OpinionProcessingStatus.ALREADY_PROCESSED
    assert second.opinion_ids == first.opinion_ids
    assert second.state_updates[0].changed is False
    assert second.state_updates[0].after.mention_count == 1
    assert (
        second.state_updates[0].after.last_change_time
        == first.state_updates[0].after.last_change_time
    )
    assert second.asset_intelligence_snapshots == first.asset_intelligence_snapshots

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RawEvent)) == 1
        assert session.scalar(select(func.count()).select_from(Opinion)) == 1
        assert session.scalar(select(func.count()).select_from(InvestorAssetState)) == 1


def test_non_investment_event_returns_no_opinion_without_downstream_state(
    db_session_factory: sessionmaker[Session],
) -> None:
    seed_asset(db_session_factory)
    investor = seed_investor(db_session_factory, quality_score=80)
    event_id = persist_raw_event(
        db_session_factory,
        investor=investor,
        content="今天天气不错，准备去散步。",
        published_time=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
    )

    result = asyncio.run(
        build_pipeline(db_session_factory, MockOpinionExtractor(MOCK_VERSION)).process(
            ProcessRawEventCommand(
                event_id=event_id,
                model_version=MOCK_VERSION,
                as_of=AS_OF,
            )
        )
    )

    assert result.opinion_processing_status == OpinionProcessingStatus.NO_OPINION
    assert result.opinion_ids == ()
    assert result.state_updates == ()
    assert result.affected_asset_ids == ()
    assert result.asset_intelligence_snapshots == ()
    assert result.warnings == ()


def test_unresolved_asset_does_not_block_resolved_asset_processing(
    db_session_factory: sessionmaker[Session],
) -> None:
    asset_id = seed_asset(db_session_factory)
    investor = seed_investor(db_session_factory, quality_score=80)
    event_id = persist_raw_event(
        db_session_factory,
        investor=investor,
        content="DIRECTION:BULLISH UNRESOLVED",
        published_time=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
    )

    result = asyncio.run(
        build_pipeline(db_session_factory, DirectionalFixtureExtractor()).process(
            ProcessRawEventCommand(
                event_id=event_id,
                model_version=FIXTURE_VERSION,
                as_of=AS_OF,
            )
        )
    )

    assert result.opinion_processing_status == OpinionProcessingStatus.PARTIALLY_RESOLVED
    assert len(result.unresolved_assets) == 1
    assert result.unresolved_assets[0].symbol == "UNKNOWN"
    assert len(result.opinion_ids) == 1
    assert len(result.state_updates) == 1
    assert result.affected_asset_ids == (asset_id,)
    assert result.asset_intelligence_snapshots[0].asset_id == asset_id
