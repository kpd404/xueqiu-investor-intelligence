import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai import OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import (
    AnalysisSpec,
    AssetOpinionExtraction,
    AssetReference,
    AssetResolutionStatus,
    CollectionRequest,
    OpinionDirection,
    OpinionExtractionResult,
    OpinionProcessingStatus,
)
from database.models import Asset, AssetAlias, Investor, Opinion
from database.repositories import AssetRepository, RawEventRepository
from database.unit_of_work import SqlAlchemyOpinionUnitOfWork
from pipeline import DataPipeline
from resolution import AssetResolver


def add_asset(session: Session, *, name: str, symbol: str, market: str) -> Asset:
    asset = Asset(name=name, symbol=symbol, market=market)
    session.add(asset)
    session.flush()
    return asset


def add_alias(
    session: Session,
    asset: Asset,
    *,
    alias: str,
    normalized_alias: str,
    market: str | None,
    alias_type: str = "NAME",
) -> None:
    session.add(
        AssetAlias(
            asset_id=asset.id,
            alias=alias,
            normalized_alias=normalized_alias,
            alias_type=alias_type,
            market=market,
        )
    )
    session.flush()


def resolver(session: Session) -> AssetResolver:
    return AssetResolver(AssetRepository(session))


def test_market_symbol_resolution_normalizes_embedded_market(db_session: Session) -> None:
    asset = add_asset(session=db_session, name="海螺水泥", symbol="600585", market="SH")

    result = resolver(db_session).resolve(
        AssetReference(name_hint="海螺水泥", symbol_hint="SH600585", market_hint="SH")
    )

    assert result.status is AssetResolutionStatus.RESOLVED
    assert result.asset_id == asset.id
    assert result.matched_by == "MARKET_SYMBOL"
    assert result.normalized_symbol == "600585"
    assert result.normalized_market == "SH"


def test_unique_name_alias_resolves(db_session: Session) -> None:
    asset = add_asset(session=db_session, name="Tencent Holdings", symbol="00700", market="HK")
    add_alias(db_session, asset, alias="腾讯", normalized_alias="腾讯", market="HK")

    result = resolver(db_session).resolve(AssetReference(name_hint="腾讯"))

    assert result.status is AssetResolutionStatus.RESOLVED
    assert result.asset_id == asset.id
    assert result.matched_by == "NAME_ALIAS"


def test_duplicate_name_alias_is_ambiguous_without_market(db_session: Session) -> None:
    first = add_asset(session=db_session, name="Alpha HK", symbol="A1", market="HK")
    second = add_asset(session=db_session, name="Alpha SH", symbol="A2", market="SH")
    add_alias(db_session, first, alias="腾讯", normalized_alias="腾讯", market="HK")
    add_alias(db_session, second, alias="腾讯", normalized_alias="腾讯", market="SH")

    result = resolver(db_session).resolve(AssetReference(name_hint="腾讯"))

    assert result.status is AssetResolutionStatus.AMBIGUOUS
    assert set(result.candidate_asset_ids) == {first.id, second.id}
    assert result.asset_id is None


def test_missing_identity_is_unresolved(db_session: Session) -> None:
    result = resolver(db_session).resolve(
        AssetReference(name_hint="不存在的公司", symbol_hint="999999", market_hint="SH")
    )

    assert result.status is AssetResolutionStatus.UNRESOLVED
    assert result.candidate_asset_ids == ()
    assert result.reason == "NO_MATCHING_ASSET"


def test_conflicting_market_wrappers_are_invalid(db_session: Session) -> None:
    result = resolver(db_session).resolve(AssetReference(symbol_hint="SH600585", market_hint="HK"))

    assert result.status is AssetResolutionStatus.INVALID
    assert result.reason == "CONFLICTING_MARKET_HINTS"


def test_symbol_alias_resolves_after_canonical_miss(db_session: Session) -> None:
    asset = add_asset(session=db_session, name="Alias Asset", symbol="CANONICAL", market="SH")
    add_alias(
        db_session,
        asset,
        alias="SH600585",
        normalized_alias="600585",
        market="SH",
        alias_type="SYMBOL",
    )

    result = resolver(db_session).resolve(AssetReference(symbol_hint="SH600585"))

    assert result.status is AssetResolutionStatus.RESOLVED
    assert result.asset_id == asset.id
    assert result.matched_by == "SYMBOL_ALIAS"


def test_market_hint_narrows_same_alias_across_markets(db_session: Session) -> None:
    sh_asset = add_asset(session=db_session, name="Alias SH", symbol="S1", market="SH")
    sz_asset = add_asset(session=db_session, name="Alias SZ", symbol="S2", market="SZ")
    add_alias(db_session, sh_asset, alias="同名", normalized_alias="同名", market="SH")
    add_alias(db_session, sz_asset, alias="同名", normalized_alias="同名", market="SZ")

    result = resolver(db_session).resolve(AssetReference(name_hint="同名", market_hint="SH"))

    assert result.status is AssetResolutionStatus.RESOLVED
    assert result.asset_id == sh_asset.id
    assert result.matched_by == "NAME_ALIAS_WITH_MARKET"


def test_same_alias_multiple_assets_without_market_is_ambiguous(db_session: Session) -> None:
    first = add_asset(session=db_session, name="One", symbol="O1", market="SH")
    second = add_asset(session=db_session, name="Two", symbol="O2", market="SH")
    add_alias(db_session, first, alias="同名", normalized_alias="同名", market=None)
    add_alias(db_session, second, alias="同名", normalized_alias="同名", market=None)

    result = resolver(db_session).resolve(AssetReference(name_hint="同名"))

    assert result.status is AssetResolutionStatus.AMBIGUOUS
    assert set(result.candidate_asset_ids) == {first.id, second.id}


def test_conflicting_name_and_strong_symbol_hints_are_not_silently_resolved(
    db_session: Session,
) -> None:
    symbol_asset = add_asset(session=db_session, name="Symbol Asset", symbol="600585", market="SH")
    name_asset = add_asset(session=db_session, name="Name Asset", symbol="N1", market="SH")
    add_alias(
        db_session, name_asset, alias="Name Asset", normalized_alias="NAME ASSET", market="SH"
    )

    result = resolver(db_session).resolve(
        AssetReference(name_hint="Name Asset", symbol_hint="SH600585", market_hint="SH")
    )

    assert result.status is AssetResolutionStatus.AMBIGUOUS
    assert set(result.candidate_asset_ids) == {symbol_asset.id, name_asset.id}
    assert result.reason == "CONFLICTING_IDENTITY_HINTS"


class StrongSymbolExtractor:
    async def extract(self, _event: object) -> OpinionExtractionResult:
        return OpinionExtractionResult(
            investment_related=True,
            model_version="resolver-test-model",
            opinions=(
                AssetOpinionExtraction(
                    asset_name="Canonical SH Asset",
                    symbol="SH600585",
                    market="SH",
                    direction=OpinionDirection.BULLISH,
                    strength=80,
                    confidence=0.9,
                    thesis=("确定性匹配",),
                ),
            ),
        )


class AmbiguousExtractor:
    async def extract(self, _event: object) -> OpinionExtractionResult:
        return OpinionExtractionResult(
            investment_related=True,
            model_version="resolver-test-model",
            opinions=(
                AssetOpinionExtraction(
                    asset_name="同名资产",
                    symbol=None,
                    market=None,
                    direction=OpinionDirection.BEARISH,
                    strength=45,
                    confidence=0.7,
                    thesis=("竞争压力",),
                    catalysts=("降价",),
                    risks=("利润率",),
                    time_horizon="SHORT_TERM",
                ),
            ),
        )


def seed_event(
    factory: sessionmaker[Session],
    *,
    content: str,
) -> tuple[UUID, UUID]:
    with factory() as session:
        investor = Investor(
            name="Resolver Investor", platform="manual", platform_user_id="resolver"
        )
        session.add(investor)
        session.commit()
        result = asyncio.run(
            DataPipeline(RawEventRepository(session), session).run(
                ManualImportAdapter(
                    content=content,
                    published_time=datetime(2026, 8, 31, 8, 0, tzinfo=UTC),
                    url="https://example.test/resolver-event",
                ),
                CollectionRequest(
                    investor_id=investor.id,
                    platform_user_id=investor.platform_user_id,
                ),
            )
        )
        return investor.id, result.events[0].event_id


def test_resolved_reference_flows_to_opinion(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        asset = add_asset(session=session, name="Canonical SH Asset", symbol="600585", market="SH")
        session.commit()
    _, event_id = seed_event(db_session_factory, content="讨论一个确定的上海证券资产。")
    spec = AnalysisSpec(
        analysis_version="resolver-test-analysis",
        model_version="resolver-test-model",
        prompt_version="resolver-test-prompt",
        schema_version="resolver-test-schema",
    )
    service = OpinionProcessingService(
        extractor=StrongSymbolExtractor(),
        unit_of_work_factory=lambda: SqlAlchemyOpinionUnitOfWork(db_session_factory),
    )

    result = asyncio.run(service.process(event_id, analysis_spec=spec))

    assert result.status is OpinionProcessingStatus.PROCESSED
    assert len(result.opinion_ids) == 1
    with db_session_factory() as session:
        opinion = session.get(Opinion, result.opinion_ids[0])
        assert opinion is not None
        assert opinion.asset_id == asset.id


def test_ambiguous_reference_preserves_semantics_and_candidates(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        first = add_asset(session=session, name="Ambiguous One", symbol="A1", market="HK")
        second = add_asset(session=session, name="Ambiguous Two", symbol="A2", market="HK")
        add_alias(session, first, alias="同名资产", normalized_alias="同名资产", market=None)
        add_alias(session, second, alias="同名资产", normalized_alias="同名资产", market=None)
        session.commit()
    _, event_id = seed_event(db_session_factory, content="讨论同名资产。")
    spec = AnalysisSpec(
        analysis_version="resolver-ambiguous-analysis",
        model_version="resolver-test-model",
        prompt_version="resolver-test-prompt",
        schema_version="resolver-test-schema",
    )
    service = OpinionProcessingService(
        extractor=AmbiguousExtractor(),
        unit_of_work_factory=lambda: SqlAlchemyOpinionUnitOfWork(db_session_factory),
    )

    result = asyncio.run(service.process(event_id, analysis_spec=spec))

    assert result.status is OpinionProcessingStatus.PARTIALLY_RESOLVED
    assert result.opinion_ids == ()
    assert len(result.unresolved_assets) == 1
    unresolved = result.unresolved_assets[0]
    assert set(unresolved.candidate_asset_ids) == {first.id, second.id}
    assert unresolved.direction is OpinionDirection.BEARISH
    assert unresolved.strength == 45
    assert unresolved.confidence == 0.7
    assert unresolved.thesis == ("竞争压力",)
    assert unresolved.catalysts == ("降价",)
    assert unresolved.risks == ("利润率",)
    assert unresolved.time_horizon == "SHORT_TERM"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0
