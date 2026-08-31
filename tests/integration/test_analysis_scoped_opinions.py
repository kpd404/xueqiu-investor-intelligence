import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai import MockOpinionExtractor, OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import (
    AnalysisSpec,
    CollectionRequest,
    EventAnalysisStatus,
    OpinionDirection,
    OpinionExtractionResult,
    OpinionProcessingStatus,
    UnresolvedAsset,
)
from database.models import Asset, AssetAlias, EventAnalysis, Investor, Opinion, RawEvent
from database.repositories import RawEventRepository
from database.unit_of_work import SqlAlchemyOpinionUnitOfWork
from pipeline import DataPipeline
from resolution import AssetRecoveryService

MODEL_VERSION = "analysis-scoped-test-model"


def analysis_spec(provider_id: str) -> AnalysisSpec:
    return AnalysisSpec.for_provider(
        provider_id=provider_id,
        model_version=MODEL_VERSION,
        prompt_version="analysis-scoped-test-prompt",
        schema_version="analysis-scoped-test-schema",
    )


def seed_event(factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID]:
    with factory() as session:
        investor = Investor(
            name="Analysis Scoped Investor",
            platform="manual",
            platform_user_id=f"analysis-scoped-{uuid4()}",
        )
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.commit()
        result = asyncio.run(
            DataPipeline(RawEventRepository(session), session).run(
                ManualImportAdapter(
                    content="腾讯AI商业化空间正在扩大，广告恢复也可能推动盈利改善。",
                    published_time=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
                    url=f"https://example.test/analysis-scoped/{uuid4()}",
                ),
                CollectionRequest(
                    investor_id=investor.id,
                    platform_user_id=investor.platform_user_id,
                ),
            )
        )
        return investor.id, asset.id, result.events[0].event_id


class NeverCalledExtractor:
    async def extract(self, _event: object) -> OpinionExtractionResult:
        raise AssertionError("existing EventAnalysis must not call the extractor")


def process_with_mock(factory: sessionmaker[Session], event_id: UUID, spec: AnalysisSpec) -> object:
    service = OpinionProcessingService(
        MockOpinionExtractor(model_version=MODEL_VERSION),
        lambda: SqlAlchemyOpinionUnitOfWork(factory),
    )
    return asyncio.run(service.process(event_id, analysis_spec=spec))


def reread_with_never_called(
    factory: sessionmaker[Session], event_id: UUID, spec: AnalysisSpec
) -> object:
    service = OpinionProcessingService(
        NeverCalledExtractor(),
        lambda: SqlAlchemyOpinionUnitOfWork(factory),
    )
    return asyncio.run(service.process(event_id, analysis_spec=spec))


def test_existing_analysis_result_is_scoped_to_analysis_id(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, event_id = seed_event(db_session_factory)
    spec_a = analysis_spec("provider-a")
    spec_b = analysis_spec("provider-b")

    result_a = process_with_mock(db_session_factory, event_id, spec_a)
    result_b = process_with_mock(db_session_factory, event_id, spec_b)

    with db_session_factory() as session:
        session.add(
            Opinion(
                event_id=event_id,
                analysis_id=None,
                investor_id=investor_id,
                asset_id=asset_id,
                direction=OpinionDirection.NEUTRAL,
                strength=50,
                confidence=0.5,
                thesis=[],
                catalysts=[],
                risks=[],
                model_version="legacy-model",
                generated_time=datetime(2026, 8, 31, 8, 1, tzinfo=UTC),
            )
        )
        session.commit()

    reread_a = reread_with_never_called(db_session_factory, event_id, spec_a)
    reread_b = reread_with_never_called(db_session_factory, event_id, spec_b)

    assert reread_a.status is OpinionProcessingStatus.ALREADY_PROCESSED
    assert reread_b.status is OpinionProcessingStatus.ALREADY_PROCESSED
    assert reread_a.opinion_ids == result_a.opinion_ids
    assert reread_b.opinion_ids == result_b.opinion_ids
    assert set(reread_a.opinion_ids).isdisjoint(reread_b.opinion_ids)
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opinion)) == 3


def test_recovered_analysis_result_excludes_other_analysis_opinion(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        investor = Investor(
            name="Recovery Scoped Investor",
            platform="manual",
            platform_user_id=f"recovery-scoped-{uuid4()}",
        )
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.flush()
        session.add(
            AssetAlias(
                asset_id=asset.id,
                alias="腾讯",
                normalized_alias="腾讯",
                alias_type="NAME",
                market=None,
            )
        )
        raw_event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="manual",
            url=f"https://example.test/recovery-scoped/{uuid4()}",
            published_time=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
            content="腾讯投资观点",
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
            collected_time=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
        )
        session.add(raw_event)
        session.flush()
        spec_recovery = analysis_spec("recovery-provider")
        analysis = EventAnalysis(
            event_id=raw_event.id,
            analysis_version=spec_recovery.analysis_version,
            model_version=spec_recovery.model_version,
            prompt_version=spec_recovery.prompt_version,
            schema_version=spec_recovery.schema_version,
            status=EventAnalysisStatus.PARTIALLY_RESOLVED,
            investment_related=True,
            generated_time=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
            calculated_at=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
            confidence=0.8,
            structured_output={
                "analysis_spec": spec_recovery.model_dump(mode="json"),
                "investment_related": True,
                "opinions": [],
                "unresolved_assets": [
                    UnresolvedAsset(
                        asset_name="腾讯",
                        direction=OpinionDirection.BULLISH,
                        strength=70,
                        confidence=0.8,
                        thesis=("商业化",),
                    ).model_dump(mode="json")
                ],
            },
            provider_metadata={"provider": "recovery-provider"},
        )
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id
        event_id = raw_event.id
        asset_id = asset.id

    recovered = AssetRecoveryService(
        lambda: SqlAlchemyOpinionUnitOfWork(db_session_factory)
    ).recover(analysis_id=analysis_id)

    with db_session_factory() as session:
        other_spec = analysis_spec("other-provider")
        other_analysis = EventAnalysis(
            event_id=event_id,
            analysis_version=other_spec.analysis_version,
            model_version=other_spec.model_version,
            prompt_version=other_spec.prompt_version,
            schema_version=other_spec.schema_version,
            status=EventAnalysisStatus.SUCCESS,
            investment_related=True,
            generated_time=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
            calculated_at=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
            confidence=0.8,
            structured_output={
                "analysis_spec": other_spec.model_dump(mode="json"),
                "investment_related": True,
                "opinions": [],
                "unresolved_assets": [],
            },
            provider_metadata={"provider": "other-provider"},
        )
        session.add(other_analysis)
        session.flush()
        session.add(
            Opinion(
                event_id=event_id,
                analysis_id=other_analysis.id,
                investor_id=session.get(RawEvent, event_id).investor_id,
                asset_id=asset_id,
                direction=OpinionDirection.BEARISH,
                strength=30,
                confidence=0.7,
                thesis=["other analysis"],
                catalysts=[],
                risks=[],
                model_version=other_spec.model_version,
                generated_time=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
            )
        )
        session.commit()

    reread = reread_with_never_called(db_session_factory, event_id, spec_recovery)

    assert recovered.opinion_ids
    assert reread.status is OpinionProcessingStatus.ALREADY_PROCESSED
    assert reread.opinion_ids == recovered.opinion_ids
