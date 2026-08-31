import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai import MockOpinionExtractor, OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import (
    AssetOpinionExtraction,
    CollectionRequest,
    OpinionDirection,
    OpinionExtractionResult,
    OpinionProcessingStatus,
    UnresolvedAssetHint,
)
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


class AmbiguousAssetExtractor:
    async def extract(self, _event: object) -> OpinionExtractionResult:
        return OpinionExtractionResult(
            investment_related=True,
            model_version=MODEL_VERSION,
            unresolved_assets=(
                UnresolvedAssetHint(asset_name="这家AI应用公司", reason="AMBIGUOUS_ASSET"),
            ),
        )


class NameOnlyOpinionExtractor:
    async def extract(self, _event: object) -> OpinionExtractionResult:
        return OpinionExtractionResult(
            investment_related=True,
            model_version=MODEL_VERSION,
            opinions=(
                AssetOpinionExtraction(
                    asset_name="一家未命名 AI 公司",
                    symbol=None,
                    market=None,
                    direction=OpinionDirection.BULLISH,
                    strength=65,
                    confidence=0.6,
                    thesis=("商业化速度",),
                ),
            ),
        )


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
    assert result.unresolved_assets[0].direction == OpinionDirection.BULLISH
    assert result.unresolved_assets[0].strength == 80
    assert result.unresolved_assets[0].confidence == 0.9
    assert result.unresolved_assets[0].thesis == ("AI商业化", "广告恢复")
    assert result.unresolved_assets[0].catalysts == ("广告恢复",)

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_ambiguous_asset_hint_is_retained_without_creating_asset(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _ = seed_raw_event(
        db_session_factory,
        content="这家AI应用公司的商业化速度比我预期快很多。",
        create_asset=False,
    )
    service = OpinionProcessingService(
        extractor=AmbiguousAssetExtractor(),
        unit_of_work_factory=lambda: SqlAlchemyOpinionUnitOfWork(db_session_factory),
    )

    result = asyncio.run(service.process(event_id, MODEL_VERSION))

    assert result.status == OpinionProcessingStatus.PARTIALLY_RESOLVED
    assert result.opinion_ids == ()
    assert len(result.unresolved_assets) == 1
    assert result.unresolved_assets[0].asset_name == "这家AI应用公司"
    assert result.unresolved_assets[0].symbol is None
    assert result.unresolved_assets[0].market is None

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_name_only_opinion_preserves_semantics_without_asset_lookup(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _ = seed_raw_event(
        db_session_factory,
        content="这家AI应用公司的商业化速度比我预期快很多。",
        create_asset=False,
    )
    service = OpinionProcessingService(
        extractor=NameOnlyOpinionExtractor(),
        unit_of_work_factory=lambda: SqlAlchemyOpinionUnitOfWork(db_session_factory),
    )

    result = asyncio.run(service.process(event_id, MODEL_VERSION))

    assert result.status == OpinionProcessingStatus.PARTIALLY_RESOLVED
    assert result.opinion_ids == ()
    assert len(result.unresolved_assets) == 1
    unresolved = result.unresolved_assets[0]
    assert unresolved.direction == OpinionDirection.BULLISH
    assert unresolved.strength == 65
    assert unresolved.confidence == 0.6
    assert unresolved.thesis == ("商业化速度",)


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
