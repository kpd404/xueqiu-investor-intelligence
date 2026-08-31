from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    AnalysisSpec,
    AssetRecoveryStatus,
    EventAnalysisStatus,
    OpinionDirection,
    UnresolvedAsset,
)
from database.models import (
    Asset,
    AssetAlias,
    EventAnalysis,
    Investor,
    InvestorAssetState,
    Opinion,
    RawEvent,
)
from database.unit_of_work import SqlAlchemyOpinionUnitOfWork
from resolution import AssetRecoveryService

RECOVERY_SPEC = AnalysisSpec(
    analysis_version="recovery-test-analysis",
    model_version="recovery-test-model",
    prompt_version="recovery-test-prompt",
    schema_version="recovery-test-schema",
)


def unresolved(
    name: str,
    *,
    direction: OpinionDirection | None = OpinionDirection.BULLISH,
) -> UnresolvedAsset:
    return UnresolvedAsset(
        asset_name=name,
        direction=direction,
        strength=72 if direction is not None else None,
        confidence=0.84 if direction is not None else None,
        thesis=("经营改善",),
        catalysts=("需求回升",),
        risks=("竞争压力",),
        time_horizon="LONG_TERM",
    )


def seed_analysis(
    factory: sessionmaker[Session],
    assets: tuple[tuple[str, str, str], ...],
    unresolved_assets: tuple[UnresolvedAsset, ...],
    *,
    aliases: tuple[tuple[int, str], ...] = (),
) -> tuple[UUID, UUID, datetime, str]:
    generated_time = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
    content = f"recovery event {uuid4()}"
    with factory() as session:
        investor = Investor(
            name="Recovery Investor",
            platform="manual",
            platform_user_id=f"recovery-{uuid4()}",
        )
        session.add(investor)
        session.flush()

        asset_entities = [
            Asset(name=name, symbol=symbol, market=market) for name, symbol, market in assets
        ]
        session.add_all(asset_entities)
        session.flush()
        for index, alias in aliases:
            session.add(
                AssetAlias(
                    asset_id=asset_entities[index].id,
                    alias=alias,
                    normalized_alias=alias,
                    alias_type="NAME",
                    market=None,
                )
            )

        raw_event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="manual",
            url=f"https://example.test/recovery/{uuid4()}",
            published_time=generated_time,
            content=content,
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
            collected_time=generated_time,
        )
        session.add(raw_event)
        session.flush()
        analysis = EventAnalysis(
            event_id=raw_event.id,
            analysis_version=RECOVERY_SPEC.analysis_version,
            model_version=RECOVERY_SPEC.model_version,
            prompt_version=RECOVERY_SPEC.prompt_version,
            schema_version=RECOVERY_SPEC.schema_version,
            status=EventAnalysisStatus.PARTIALLY_RESOLVED,
            investment_related=True,
            generated_time=generated_time,
            calculated_at=generated_time,
            confidence=0.84,
            structured_output={
                "analysis_spec": RECOVERY_SPEC.model_dump(mode="json"),
                "investment_related": True,
                "opinions": [],
                "unresolved_assets": [item.model_dump(mode="json") for item in unresolved_assets],
            },
            provider_metadata={"provider": "test-provider", "provider_response_id": "response-1"},
        )
        session.add(analysis)
        session.commit()
        return analysis.id, raw_event.id, generated_time, content


def service(factory: sessionmaker[Session]) -> AssetRecoveryService:
    return AssetRecoveryService(lambda: SqlAlchemyOpinionUnitOfWork(factory))


def test_recovery_resolves_opinion_without_extractor_and_preserves_provenance(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, event_id, generated_time, content = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"),),
        (unresolved("腾讯"),),
        aliases=((0, "腾讯"),),
    )

    result = service(db_session_factory).recover(analysis_id=analysis_id)

    assert result.status is AssetRecoveryStatus.RECOVERED
    assert result.created_count == 1
    assert result.reused_count == 0
    assert len(result.opinion_ids) == 1
    assert result.unresolved_assets == ()
    assert result.analysis_status_before is EventAnalysisStatus.PARTIALLY_RESOLVED
    assert result.analysis_status_after is EventAnalysisStatus.SUCCESS

    with db_session_factory() as session:
        opinion = session.get(Opinion, result.opinion_ids[0])
        analysis = session.get(EventAnalysis, analysis_id)
        raw_event = session.get(RawEvent, event_id)
        assert opinion is not None
        assert opinion.event_id == event_id
        assert opinion.analysis_id == analysis_id
        assert opinion.direction is OpinionDirection.BULLISH
        assert opinion.strength == 72
        assert opinion.confidence == 0.84
        assert opinion.thesis == ["经营改善"]
        assert opinion.catalysts == ["需求回升"]
        assert opinion.risks == ["竞争压力"]
        assert opinion.time_horizon == "LONG_TERM"
        assert analysis is not None
        assert analysis.status is EventAnalysisStatus.SUCCESS
        assert analysis.generated_time.replace(tzinfo=UTC) == generated_time
        assert analysis.provider_metadata == {
            "provider": "test-provider",
            "provider_response_id": "response-1",
        }
        assert analysis.structured_output["analysis_spec"] == RECOVERY_SPEC.model_dump(mode="json")
        recovery = analysis.structured_output["resolution_recovery"]
        assert recovery["original_unresolved_assets"][0]["asset_name"] == "腾讯"
        assert recovery["remaining_unresolved_assets"] == []
        assert raw_event is not None
        assert raw_event.content == content
        assert session.scalar(select(func.count()).select_from(InvestorAssetState)) == 0


def test_recovery_is_idempotent_and_reuses_existing_opinion(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"),),
        (unresolved("腾讯"),),
        aliases=((0, "腾讯"),),
    )
    recovery = service(db_session_factory)

    first = recovery.recover(analysis_id=analysis_id)
    second = recovery.recover(analysis_id=analysis_id)

    assert first.status is AssetRecoveryStatus.RECOVERED
    assert second.status is AssetRecoveryStatus.ALREADY_RECOVERED
    assert second.created_count == 0
    assert second.reused_count == 1
    assert second.opinion_ids == first.opinion_ids
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opinion)) == 1


def test_recovery_can_select_analysis_by_event_and_version(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _, _ = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"),),
        (unresolved("腾讯"),),
        aliases=((0, "腾讯"),),
    )

    result = service(db_session_factory).recover(
        event_id=event_id,
        analysis_version=RECOVERY_SPEC.analysis_version,
    )

    assert result.status is AssetRecoveryStatus.RECOVERED


def test_unresolved_asset_remains_unresolved_without_creating_asset(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (),
        (unresolved("不存在的资产"),),
    )

    result = service(db_session_factory).recover(analysis_id=analysis_id)

    assert result.status is AssetRecoveryStatus.UNRESOLVED
    assert result.created_count == 0
    assert result.opinion_ids == ()
    assert result.unresolved_assets[0].reason == "NO_MATCHING_ASSET"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0
        analysis = session.get(EventAnalysis, analysis_id)
        assert analysis is not None
        assert analysis.status is EventAnalysisStatus.PARTIALLY_RESOLVED


def test_ambiguous_asset_remains_unresolved_with_candidates(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (("First", "F1", "HK"), ("Second", "F2", "HK")),
        (unresolved("同名资产"),),
        aliases=((0, "同名资产"), (1, "同名资产")),
    )

    result = service(db_session_factory).recover(analysis_id=analysis_id)

    assert result.status is AssetRecoveryStatus.UNRESOLVED
    assert len(result.unresolved_assets) == 1
    assert result.unresolved_assets[0].reason == "MULTIPLE_NAME_ALIAS_MATCHES"
    assert len(result.unresolved_assets[0].candidate_asset_ids) == 2
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_resolved_identity_without_semantics_is_not_persisted(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"),),
        (unresolved("腾讯", direction=None),),
        aliases=((0, "腾讯"),),
    )

    result = service(db_session_factory).recover(analysis_id=analysis_id)

    assert result.status is AssetRecoveryStatus.UNRESOLVED
    assert result.unresolved_assets[0].reason == "MISSING_OPINION_SEMANTICS"
    assert result.opinion_ids == ()
