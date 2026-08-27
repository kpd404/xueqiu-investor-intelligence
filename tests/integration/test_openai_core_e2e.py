import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai import OpenAICompatibleOpinionExtractor, OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import (
    AnalysisSpec,
    AssetOpinionExtraction,
    CollectionRequest,
    LLMProviderConfig,
    OpinionDirection,
    OpinionExtractionResult,
    OpinionProcessingStatus,
    ProcessRawEventCommand,
)
from database.models import Asset, EventAnalysis, Investor, Opinion
from database.repositories import EventAnalysisRepository, RawEventRepository
from database.unit_of_work import (
    SqlAlchemyIntelligenceUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
)
from intelligence import AssetIntelligenceService, StateUpdateService
from pipeline import DataPipeline, IntelligencePipeline

CONFIG = LLMProviderConfig(
    provider_id="test-provider",
    base_url="https://gateway.example.test/v1",
    api_key="test-secret",
    model="arbitrary-model-a",
)


def output_payload(model_version: str = "ignored") -> dict[str, object]:
    return OpinionExtractionResult(
        investment_related=True,
        opinions=(
            AssetOpinionExtraction(
                asset_name="Tencent",
                symbol="00700",
                market="HK",
                direction=OpinionDirection.BULLISH,
                strength=80,
                confidence=0.9,
                thesis=("AI商业化空间扩大", "广告业务恢复"),
            ),
        ),
        model_version=model_version,
    ).model_dump(mode="json")


class FakeUsage:
    input_tokens = 20
    output_tokens = 12
    total_tokens = 32


class FakeContent:
    type = "output_text"

    def __init__(self, text: str) -> None:
        self.text = text


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [FakeContent(text)]


class FakeResponse:
    status = "completed"
    id = "resp_core_e2e"
    model = CONFIG.model
    usage = FakeUsage()

    def __init__(self, payload: dict[str, object]) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        self.output = [FakeMessage(text)]
        self.output_text = text


class FakeResponses:
    def __init__(self, payload: dict[str, object]) -> None:
        self.response = FakeResponse(payload)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def seed_raw_event(factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID]:
    with factory() as session:
        investor = Investor(
            name="Generic E2E Investor",
            platform="manual",
            platform_user_id=f"generic-e2e-{uuid4()}",
            quality_score=80,
        )
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.commit()

        raw_result = asyncio.run(
            DataPipeline(RawEventRepository(session), session).run(
                ManualImportAdapter(
                    content="腾讯AI商业化空间正在扩大，广告业务恢复也可能推动盈利改善。",
                    published_time=datetime(2026, 8, 27, 10, 0, tzinfo=UTC),
                    url=f"https://example.test/generic-e2e/{uuid4()}",
                ),
                CollectionRequest(
                    investor_id=investor.id,
                    platform_user_id=investor.platform_user_id,
                ),
            )
        )
        return investor.id, asset.id, raw_result.events[0].event_id


def analysis_spec(config: LLMProviderConfig) -> AnalysisSpec:
    return AnalysisSpec.for_provider(
        provider_id=config.provider_id,
        model_version=config.model,
        prompt_version="opinion-extraction-v1",
        schema_version="opinion-extraction-result-v2",
    )


def build_core_pipeline(
    factory: sessionmaker[Session],
    *,
    config: LLMProviderConfig = CONFIG,
    responses: FakeResponses | None = None,
) -> tuple[IntelligencePipeline, FakeResponses]:
    fake_responses = responses or FakeResponses(output_payload(config.model))
    extractor = OpenAICompatibleOpinionExtractor(
        config,
        client=FakeClient(fake_responses),
        prompt_text="test prompt",
    )

    def opinion_uow() -> SqlAlchemyOpinionUnitOfWork:
        return SqlAlchemyOpinionUnitOfWork(factory)

    def state_uow() -> SqlAlchemyStateUnitOfWork:
        return SqlAlchemyStateUnitOfWork(factory)

    def intelligence_uow() -> SqlAlchemyIntelligenceUnitOfWork:
        return SqlAlchemyIntelligenceUnitOfWork(factory)

    return (
        IntelligencePipeline(
            OpinionProcessingService(extractor, opinion_uow),
            StateUpdateService(state_uow),
            AssetIntelligenceService(intelligence_uow),
        ),
        fake_responses,
    )


def test_generic_provider_runs_through_event_analysis_to_intelligence(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, event_id = seed_raw_event(db_session_factory)

    pipeline, responses = build_core_pipeline(db_session_factory)
    result = asyncio.run(
        pipeline.process(
            ProcessRawEventCommand(
                event_id=event_id,
                analysis_spec=analysis_spec(CONFIG),
                as_of=datetime(2026, 8, 28, tzinfo=UTC),
            )
        )
    )

    assert result.opinion_processing_status == OpinionProcessingStatus.PROCESSED
    assert len(result.opinion_ids) == 1
    assert result.affected_asset_ids == (asset_id,)
    assert len(result.state_updates) == 1
    assert len(result.asset_intelligence_snapshots) == 1
    assert result.asset_intelligence_snapshots[0].source_event_ids == (event_id,)
    assert responses.calls[0]["model"] == CONFIG.model

    with db_session_factory() as session:
        opinion = session.get(Opinion, result.opinion_ids[0])
        assert opinion is not None
        analysis = session.get(EventAnalysis, opinion.analysis_id)
        assert analysis is not None
        assert analysis.event_id == event_id
        assert analysis.analysis_version == analysis_spec(CONFIG).analysis_version
        assert analysis.provider_metadata == {
            "provider": "test-provider",
            "base_url": "https://gateway.example.test/v1",
            "provider_response_id": "resp_core_e2e",
            "model": "arbitrary-model-a",
            "input_tokens": 20,
            "output_tokens": 12,
            "total_tokens": 32,
        }
        assert analysis.structured_output["analysis_spec"]["provider_id"] == "test-provider"
        view = EventAnalysisRepository(session).get_by_identity(
            event_id, analysis_spec(CONFIG).analysis_version
        )
        assert view is not None and view.spec.provider_id == "test-provider"
        assert opinion.analysis_id == analysis.id
        assert opinion.event_id == event_id
        assert opinion.investor_id == investor_id


def test_same_provider_model_is_idempotent_and_does_not_recall_provider(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, event_id = seed_raw_event(db_session_factory)
    responses = FakeResponses(output_payload(CONFIG.model))
    pipeline, _ = build_core_pipeline(db_session_factory, responses=responses)
    command = ProcessRawEventCommand(
        event_id=event_id,
        analysis_spec=analysis_spec(CONFIG),
        as_of=datetime(2026, 8, 28, tzinfo=UTC),
    )

    first = asyncio.run(pipeline.process(command))
    second = asyncio.run(pipeline.process(command))

    assert first.opinion_ids == second.opinion_ids
    assert second.opinion_processing_status == OpinionProcessingStatus.ALREADY_PROCESSED
    assert len(responses.calls) == 1
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(EventAnalysis)) == 1
        assert session.scalar(select(func.count()).select_from(Opinion)) == 1


def test_different_provider_ids_can_coexist_for_one_raw_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, event_id = seed_raw_event(db_session_factory)
    provider_a = CONFIG
    provider_b = CONFIG.model_copy(update={"provider_id": "another-provider"})

    for provider_config in (provider_a, provider_b):
        responses = FakeResponses(output_payload(provider_config.model))
        extractor = OpenAICompatibleOpinionExtractor(
            provider_config,
            client=FakeClient(responses),
            prompt_text="test prompt",
        )
        service = OpinionProcessingService(
            extractor,
            lambda: SqlAlchemyOpinionUnitOfWork(db_session_factory),
        )
        result = asyncio.run(
            service.process(event_id, analysis_spec=analysis_spec(provider_config))
        )
        assert result.status == OpinionProcessingStatus.PROCESSED

    with db_session_factory() as session:
        analyses = list(
            session.scalars(select(EventAnalysis).where(EventAnalysis.event_id == event_id))
        )
        opinions = list(session.scalars(select(Opinion).where(Opinion.event_id == event_id)))
        assert len(analyses) == 2
        assert len(opinions) == 2
        assert {analysis.provider_metadata["provider"] for analysis in analyses} == {
            "test-provider",
            "another-provider",
        }
        assert len({analysis.analysis_version for analysis in analyses}) == 2
