import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai import MockOpinionExtractor, OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import CollectionRequest, OpinionDirection, OpinionProcessingStatus
from database.models import Asset, Investor, Opinion, RawEvent
from database.repositories import OpinionRepository, RawEventRepository
from database.unit_of_work import SqlAlchemyOpinionUnitOfWork
from pipeline import DataPipeline

MODEL_VERSION = "mock-opinion-v1"
TENCENT_FIXTURE = "腾讯AI商业化空间正在扩大，广告恢复也可能推动盈利改善。"


def seed_raw_event(
    factory: sessionmaker[Session],
    *,
    content: str,
    create_asset: bool,
) -> tuple[UUID, UUID, UUID | None]:
    with factory() as session:
        investor = Investor(
            name="Opinion Test Investor",
            platform="manual",
            platform_user_id="opinion-test-investor",
        )
        session.add(investor)
        session.flush()

        asset_id: UUID | None = None
        if create_asset:
            asset = Asset(name="Tencent", symbol="00700", market="HK")
            session.add(asset)
            session.flush()
            asset_id = asset.id
        session.commit()

        adapter = ManualImportAdapter(
            content=content,
            published_time=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            url="https://example.test/manual/opinion-event",
        )
        request = CollectionRequest(
            investor_id=investor.id,
            platform_user_id=investor.platform_user_id,
        )
        raw_pipeline = DataPipeline(RawEventRepository(session), session)
        raw_result = asyncio.run(raw_pipeline.run(adapter, request))
        return investor.id, raw_result.events[0].event_id, asset_id


def build_service(
    factory: sessionmaker[Session],
) -> OpinionProcessingService:
    def unit_of_work_factory() -> SqlAlchemyOpinionUnitOfWork:
        return SqlAlchemyOpinionUnitOfWork(factory)

    return OpinionProcessingService(
        extractor=MockOpinionExtractor(model_version=MODEL_VERSION),
        unit_of_work_factory=unit_of_work_factory,
    )


def test_raw_event_to_mock_extractor_produces_opinion(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, asset_id = seed_raw_event(
        db_session_factory,
        content=TENCENT_FIXTURE,
        create_asset=True,
    )

    result = asyncio.run(build_service(db_session_factory).process(event_id, MODEL_VERSION))

    assert result.status == OpinionProcessingStatus.PROCESSED
    assert len(result.opinion_ids) == 1
    assert result.unresolved_assets == ()

    with db_session_factory() as session:
        opinion = session.get(Opinion, result.opinion_ids[0])
        assert opinion is not None
        assert opinion.asset_id == asset_id
        assert opinion.direction == OpinionDirection.BULLISH
        assert opinion.strength == 80
        assert opinion.confidence == 0.9
        assert opinion.thesis == ["AI商业化", "广告恢复"]


def test_reprocessing_same_event_and_model_is_idempotent(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _ = seed_raw_event(
        db_session_factory,
        content=TENCENT_FIXTURE,
        create_asset=True,
    )
    service = build_service(db_session_factory)

    first = asyncio.run(service.process(event_id, MODEL_VERSION))
    second = asyncio.run(service.process(event_id, MODEL_VERSION))

    assert first.status == OpinionProcessingStatus.PROCESSED
    assert second.status == OpinionProcessingStatus.ALREADY_PROCESSED
    assert second.opinion_ids == first.opinion_ids

    with db_session_factory() as session:
        opinion_count = session.scalar(select(func.count()).select_from(Opinion))
        assert opinion_count == 1
        opinion = session.get(Opinion, first.opinion_ids[0])
        assert opinion is not None
        assert OpinionRepository(session).exists(event_id, opinion.asset_id, MODEL_VERSION)


def test_unresolved_asset_is_reported_and_not_created(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _ = seed_raw_event(
        db_session_factory,
        content=TENCENT_FIXTURE,
        create_asset=False,
    )

    result = asyncio.run(build_service(db_session_factory).process(event_id, MODEL_VERSION))

    assert result.status == OpinionProcessingStatus.PARTIALLY_RESOLVED
    assert result.opinion_ids == ()
    assert len(result.unresolved_assets) == 1
    assert result.unresolved_assets[0].symbol == "00700"
    assert result.unresolved_assets[0].market == "HK"

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_non_investment_content_returns_no_opinion(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _ = seed_raw_event(
        db_session_factory,
        content="今天天气很好，准备出门散步。",
        create_asset=False,
    )

    result = asyncio.run(build_service(db_session_factory).process(event_id, MODEL_VERSION))

    assert result.status == OpinionProcessingStatus.NO_OPINION
    assert result.opinion_ids == ()
    assert result.unresolved_assets == ()

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_persisted_identity_is_derived_from_raw_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, event_id, _ = seed_raw_event(
        db_session_factory,
        content=TENCENT_FIXTURE,
        create_asset=True,
    )

    result = asyncio.run(build_service(db_session_factory).process(event_id, MODEL_VERSION))

    with db_session_factory() as session:
        raw_event = session.get(RawEvent, event_id)
        opinion = session.get(Opinion, result.opinion_ids[0])
        assert raw_event is not None
        assert opinion is not None
        assert opinion.event_id == raw_event.id == event_id
        assert opinion.investor_id == raw_event.investor_id == investor_id
