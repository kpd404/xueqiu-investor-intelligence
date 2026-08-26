import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai import OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import (
    AnalysisSpec,
    AssetOpinionExtraction,
    CollectionRequest,
    EventAnalysisStatus,
    EventType,
    OpinionDirection,
    OpinionExtractionResult,
    OpinionProcessingStatus,
    RawEventDTO,
    RawEventWriteResult,
    StateTransitionType,
)
from database.models import (
    Asset,
    EventAnalysis,
    Investor,
    InvestorAssetStateChange,
    Opinion,
    RawEvent,
)
from database.repositories import RawEventRepository
from database.unit_of_work import (
    SqlAlchemyIntelligenceUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
)
from intelligence import AssetIntelligenceService, StateUpdateService
from pipeline import DataPipeline

ANALYSIS_SPEC = AnalysisSpec(
    analysis_version="opinion-analysis-v1",
    model_version="mock-v1",
    prompt_version="mock-prompt-v1",
    schema_version="opinion-schema-v1",
)


class CountingNoOpinionExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, _event: object) -> OpinionExtractionResult:
        self.calls += 1
        return OpinionExtractionResult(investment_related=False, model_version="mock-v1")


class PartialExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, _event: object) -> OpinionExtractionResult:
        self.calls += 1
        return OpinionExtractionResult(
            investment_related=True,
            model_version="mock-v1",
            opinions=(
                AssetOpinionExtraction(
                    asset_name="Tencent",
                    symbol="00700",
                    market="HK",
                    direction=OpinionDirection.BULLISH,
                    strength=80,
                    confidence=0.9,
                ),
                AssetOpinionExtraction(
                    asset_name="Unknown Company",
                    symbol="UNKNOWN",
                    market="HK",
                    direction=OpinionDirection.BULLISH,
                    strength=70,
                    confidence=0.8,
                ),
            ),
        )


def seed_investor_asset(factory: sessionmaker[Session]) -> tuple[UUID, UUID, Investor]:
    with factory() as session:
        investor = Investor(
            name=f"Temporal Investor {uuid4()}",
            platform="manual",
            platform_user_id=f"temporal-{uuid4()}",
            quality_score=80,
        )
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.commit()
        return investor.id, asset.id, investor


def seed_raw_event(
    factory: sessionmaker[Session],
    investor: Investor,
    *,
    content: str,
    published_time: datetime,
) -> UUID:
    with factory() as session:
        adapter = ManualImportAdapter(
            content=content,
            published_time=published_time,
            url=f"https://example.test/temporal/{uuid4()}",
        )
        request = CollectionRequest(
            investor_id=investor.id,
            platform_user_id=investor.platform_user_id,
        )
        result = asyncio.run(
            DataPipeline(RawEventRepository(session), session).run(adapter, request)
        )
        return result.events[0].event_id


def build_opinion_service(
    factory: sessionmaker[Session], extractor: object
) -> OpinionProcessingService:
    return OpinionProcessingService(
        extractor,  # type: ignore[arg-type]
        lambda: SqlAlchemyOpinionUnitOfWork(factory),
    )


def add_legacy_opinion(
    factory: sessionmaker[Session],
    *,
    investor_id: UUID,
    asset_id: UUID,
    direction: OpinionDirection,
    published_time: datetime,
) -> tuple[UUID, UUID]:
    with factory() as session:
        event = RawEvent(
            investor_id=investor_id,
            event_type=EventType.POST,
            source="manual",
            url=f"https://example.test/legacy/{uuid4()}",
            published_time=published_time,
            content=f"legacy {direction.value}",
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
        )
        opinion = Opinion(
            event=event,
            investor_id=investor_id,
            asset_id=asset_id,
            direction=direction,
            strength=80,
            confidence=0.9,
            model_version="legacy-fixture-v1",
            generated_time=published_time + timedelta(hours=1),
        )
        session.add(opinion)
        session.commit()
        return opinion.id, event.id


def build_state_service(factory: sessionmaker[Session]) -> StateUpdateService:
    return StateUpdateService(lambda: SqlAlchemyStateUnitOfWork(factory))


def test_no_opinion_is_persisted_and_extractor_is_not_called_again(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, _, investor = seed_investor_asset(db_session_factory)
    event_id = seed_raw_event(
        db_session_factory,
        investor,
        content="No investment view here.",
        published_time=datetime(2026, 8, 1, tzinfo=UTC),
    )
    extractor = CountingNoOpinionExtractor()
    service = build_opinion_service(db_session_factory, extractor)

    first = asyncio.run(service.process(event_id, analysis_spec=ANALYSIS_SPEC))
    second = asyncio.run(service.process(event_id, analysis_spec=ANALYSIS_SPEC))

    assert first.status == second.status == OpinionProcessingStatus.NO_OPINION
    assert extractor.calls == 1
    assert first.analysis_id == second.analysis_id
    with db_session_factory() as session:
        analysis = session.get(EventAnalysis, first.analysis_id)
        assert analysis is not None
        assert analysis.status == EventAnalysisStatus.NO_OPINION
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_successful_opinion_is_linked_to_event_analysis(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, asset_id, investor = seed_investor_asset(db_session_factory)
    event_id = seed_raw_event(
        db_session_factory,
        investor,
        content="Tencent opinion.",
        published_time=datetime(2026, 8, 2, tzinfo=UTC),
    )
    result = asyncio.run(
        build_opinion_service(
            db_session_factory,
            PartialExtractor(),
        ).process(event_id, analysis_spec=ANALYSIS_SPEC)
    )

    # The partial fixture has one resolvable Tencent opinion.
    with db_session_factory() as session:
        opinion = session.get(Opinion, result.opinion_ids[0])
        analysis = session.get(EventAnalysis, result.analysis_id)
        assert opinion is not None and opinion.asset_id == asset_id
        assert opinion.analysis_id == analysis.id == result.analysis_id


def test_partial_analysis_is_persisted_and_replayed_without_extractor_call(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, investor = seed_investor_asset(db_session_factory)
    event_id = seed_raw_event(
        db_session_factory,
        investor,
        content="Tencent and unknown company.",
        published_time=datetime(2026, 8, 3, tzinfo=UTC),
    )
    extractor = PartialExtractor()
    service = build_opinion_service(db_session_factory, extractor)

    first = asyncio.run(service.process(event_id, analysis_spec=ANALYSIS_SPEC))
    second = asyncio.run(service.process(event_id, analysis_spec=ANALYSIS_SPEC))

    assert first.status == second.status == OpinionProcessingStatus.PARTIALLY_RESOLVED
    assert len(first.unresolved_assets) == 1
    assert extractor.calls == 1
    with db_session_factory() as session:
        analysis = session.get(EventAnalysis, first.analysis_id)
        assert analysis is not None
        assert analysis.status == EventAnalysisStatus.PARTIALLY_RESOLVED
        assert analysis.structured_output["unresolved_assets"]


def test_state_change_ledger_records_reversal_and_is_idempotent(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, _ = seed_investor_asset(db_session_factory)
    bearish_id, _ = add_legacy_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BEARISH,
        published_time=datetime(2026, 8, 10, tzinfo=UTC),
    )
    service = build_state_service(db_session_factory)
    service.update(bearish_id)
    bullish_id, _ = add_legacy_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 11, tzinfo=UTC),
    )
    reversal = service.update(bullish_id)
    retry = service.update(bullish_id)

    assert reversal.material_change is True
    assert reversal.transition == StateTransitionType.OPINION_REVERSAL
    assert retry.material_change is False
    with db_session_factory() as session:
        rows = list(session.scalars(select(InvestorAssetStateChange)))
        assert len(rows) == 2
        reversal_rows = [
            row for row in rows if row.transition_type == StateTransitionType.OPINION_REVERSAL
        ]
        assert len(reversal_rows) == 1
        assert reversal_rows[0].triggering_opinion_id == bullish_id
        assert reversal_rows[0].source_event_ids
        assert reversal_rows[0].before["direction"] == OpinionDirection.BEARISH.value
        assert reversal_rows[0].after["direction"] == OpinionDirection.BULLISH.value


def test_activity_update_is_not_material_change(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, _ = seed_investor_asset(db_session_factory)
    first_id, _ = add_legacy_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 12, tzinfo=UTC),
    )
    service = build_state_service(db_session_factory)
    first = service.update(first_id)
    second_id, _ = add_legacy_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 13, tzinfo=UTC),
    )
    second = service.update(second_id)

    assert first.material_change is True
    assert second.projection_changed is True
    assert second.material_change is False
    assert second.after.last_activity_time == datetime(2026, 8, 13, tzinfo=UTC)
    assert second.after.last_material_change_time == datetime(2026, 8, 12, tzinfo=UTC)
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InvestorAssetStateChange)) == 1


def test_historical_as_of_replays_opinions_instead_of_current_state(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, _ = seed_investor_asset(db_session_factory)
    bullish_id, _ = add_legacy_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BULLISH,
        published_time=datetime(2026, 8, 1, tzinfo=UTC),
    )
    bearish_id, _ = add_legacy_opinion(
        db_session_factory,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=OpinionDirection.BEARISH,
        published_time=datetime(2026, 8, 20, tzinfo=UTC),
    )
    state_service = build_state_service(db_session_factory)
    state_service.update(bullish_id)
    state_service.update(bearish_id)

    intelligence = AssetIntelligenceService(
        lambda: SqlAlchemyIntelligenceUnitOfWork(db_session_factory)
    )
    snapshot = intelligence.build(asset_id, datetime(2026, 8, 10, tzinfo=UTC))

    assert snapshot.investor_states[0].direction == OpinionDirection.BULLISH
    assert snapshot.source_event_ids


class _FakeTransaction:
    def __init__(self) -> None:
        self.in_transaction = False
        self.commit_count = 0

    def commit(self) -> None:
        self.in_transaction = False
        self.commit_count += 1

    def rollback(self) -> None:
        self.in_transaction = False


class _FakeRawEventRepository:
    def __init__(self, transaction: _FakeTransaction) -> None:
        self.transaction = transaction
        self.index = 0

    def add_if_absent(self, dto: RawEventDTO) -> RawEventWriteResult:
        self.transaction.in_transaction = True
        self.index += 1
        return RawEventWriteResult(event_id=uuid4(), hash=dto.hash, created=True)


class _StreamingAdapter:
    source = "manual"

    def __init__(self, transaction: _FakeTransaction) -> None:
        self.transaction = transaction

    async def collect(self, request: CollectionRequest) -> AsyncIterator[RawEventDTO]:
        for index in range(2):
            yield RawEventDTO.build(
                investor_id=request.investor_id,
                event_type=EventType.POST,
                source=self.source,
                url=f"https://example.test/stream/{index}",
                published_time=datetime(2026, 8, 25, index, tzinfo=UTC),
                content=f"event {index}",
            )
            if index == 0:
                assert self.transaction.in_transaction is False


def test_data_pipeline_commits_before_waiting_for_next_dto() -> None:
    transaction = _FakeTransaction()
    pipeline = DataPipeline(_FakeRawEventRepository(transaction), transaction)
    request = CollectionRequest(investor_id=uuid4(), platform_user_id="stream-test")

    result = asyncio.run(pipeline.run(_StreamingAdapter(transaction), request))

    assert result.total == 2
    assert transaction.commit_count == 2
