import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from ai import MockOpinionExtractor, OpinionProcessingService
from collectors import ManualImportAdapter
from contracts import (
    AnalysisSpec,
    CollectionCoverageStatus,
    CollectionRequest,
    CollectionRunCreate,
    EffectiveAnalysisPolicy,
    ProcessRawEventCommand,
)
from contracts.collection_provenance import utc_now
from database.models import Asset, Investor, Opinion
from database.repositories import (
    CollectionObservationRepository,
    CollectionRunRepository,
    RawEventRepository,
)
from database.session import SessionFactory
from database.unit_of_work import (
    SqlAlchemyIntelligenceUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
)
from intelligence import AssetIntelligenceService, StateUpdateService
from pipeline import DataPipeline, IntelligencePipeline

MODEL_VERSION = "mock-opinion-v1"


def build_intelligence_pipeline() -> IntelligencePipeline:
    effective_policy = EffectiveAnalysisPolicy(
        active_spec=AnalysisSpec.from_model_version(MODEL_VERSION)
    )

    def opinion_unit_of_work() -> SqlAlchemyOpinionUnitOfWork:
        return SqlAlchemyOpinionUnitOfWork(SessionFactory)

    def state_unit_of_work() -> SqlAlchemyStateUnitOfWork:
        return SqlAlchemyStateUnitOfWork(SessionFactory)

    def intelligence_unit_of_work() -> SqlAlchemyIntelligenceUnitOfWork:
        return SqlAlchemyIntelligenceUnitOfWork(SessionFactory)

    return IntelligencePipeline(
        OpinionProcessingService(MockOpinionExtractor(MODEL_VERSION), opinion_unit_of_work),
        StateUpdateService(state_unit_of_work, effective_policy),
        AssetIntelligenceService(intelligence_unit_of_work, effective_policy),
    )


async def run_demo() -> None:
    now = datetime.now(UTC)
    with SessionFactory() as session:
        asset = session.scalar(select(Asset).where(Asset.market == "HK", Asset.symbol == "00700"))
        if asset is None:
            asset = Asset(name="Tencent", symbol="00700", market="HK")
            session.add(asset)

        unique_id = uuid4()
        investor = Investor(
            name="Core Pipeline Demo Investor",
            platform="manual",
            platform_user_id=f"core-demo-{unique_id}",
            quality_score=80,
        )
        session.add(investor)
        session.commit()

        adapter = ManualImportAdapter(
            content="腾讯AI商业化空间正在扩大，广告恢复可能推动盈利改善。",
            published_time=now,
            url=f"https://example.test/core-demo/{unique_id}",
        )
        request = CollectionRequest(
            investor_id=investor.id,
            platform_user_id=investor.platform_user_id,
            limit=1,
        )
        run = CollectionRunRepository(session).create_run(
            CollectionRunCreate(
                source=adapter.source,
                adapter_name=adapter.adapter_name,
                collection_mode=adapter.collection_mode,
                transport=adapter.transport,
                started_at=now,
                coverage_status=CollectionCoverageStatus.UNKNOWN,
                requested_window_start=adapter.published_time,
                requested_window_end=adapter.published_time,
                scope_type="MANUAL_IMPORT",
                scope_key=investor.platform_user_id,
                parameters_json={"entrypoint": "pipeline.demo"},
            )
        )
        session.commit()
        try:
            raw_result = await DataPipeline(
                RawEventRepository(session),
                session,
                collection_observation_repository=CollectionObservationRepository(session),
                collection_run_id=run.id,
                source_page=adapter.url,
            ).run(adapter, request)
            CollectionRunRepository(session).finish_run(
                run.id,
                ended_at=utc_now(),
                stop_reason="REQUEST_COMPLETED",
                summary_json={
                    "inserted_raw_events": raw_result.inserted,
                    "reused_raw_events": raw_result.duplicates,
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            CollectionRunRepository(session).fail_run(
                run.id,
                ended_at=utc_now(),
                stop_reason="FAILED",
            )
            session.commit()
            raise
        event_id = raw_result.events[0].event_id

    result = await build_intelligence_pipeline().process(
        ProcessRawEventCommand(
            event_id=event_id,
            model_version=MODEL_VERSION,
            as_of=now,
        )
    )

    print(f"RawEvent created: {result.event_id}")
    with SessionFactory() as session:
        for opinion_id in result.opinion_ids:
            opinion = session.get(Opinion, opinion_id)
            if opinion is not None:
                asset = session.get(Asset, opinion.asset_id)
                print(
                    "Opinion: "
                    f"{asset.name if asset else opinion.asset_id} "
                    f"{opinion.direction.value} strength={opinion.strength:g}"
                )

    for update in result.state_updates:
        print(
            "InvestorAssetState: "
            f"{update.after.attention_level.value} {update.after.direction.value}"
        )
    for snapshot in result.asset_intelligence_snapshots:
        print(
            "Asset Intelligence: "
            f"active_investors={snapshot.active_investor_count} "
            f"consensus={snapshot.consensus_direction.value}"
        )
    if result.unresolved_assets:
        print(f"Unresolved assets: {len(result.unresolved_assets)}")


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
