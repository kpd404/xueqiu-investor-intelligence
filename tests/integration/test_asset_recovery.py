from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    AnalysisSpec,
    AssetOpinionExtraction,
    AssetRecoveryStatus,
    AssetResolutionStatus,
    EventAnalysisStatus,
    OpinionDirection,
    UnresolvedAsset,
)
from database.models import (
    Asset,
    AssetAlias,
    AttentionOccurrence,
    EventAnalysis,
    IntelligenceEvent,
    Investor,
    InvestorAssetState,
    Opinion,
    RawEvent,
    Signal,
    ThesisChange,
)
from database.unit_of_work import SqlAlchemyOpinionUnitOfWork
from resolution import AssetRecoveryService
from scripts import recover_production_analysis

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


def extracted(
    name: str,
    *,
    direction: OpinionDirection = OpinionDirection.BULLISH,
    symbol: str | None = None,
    market: str | None = None,
) -> AssetOpinionExtraction:
    return AssetOpinionExtraction(
        asset_name=name,
        symbol=symbol,
        market=market,
        direction=direction,
        strength=72,
        confidence=0.84,
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
    opinion_entries: tuple[AssetOpinionExtraction, ...] = (),
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
                "opinions": [item.model_dump(mode="json") for item in opinion_entries],
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
        opinion_entries=(extracted("腾讯"),),
    )

    with db_session_factory() as session:
        analysis_before = session.get(EventAnalysis, analysis_id)
        assert analysis_before is not None
        structured_before = analysis_before.structured_output
        calculated_before = analysis_before.calculated_at

    result = service(db_session_factory).recover(analysis_id=analysis_id)

    assert result.status is AssetRecoveryStatus.RECOVERED
    assert result.created_count == 1
    assert result.reused_count == 0
    assert len(result.opinion_ids) == 1
    assert result.unresolved_assets == ()
    assert result.analysis_status_before is EventAnalysisStatus.PARTIALLY_RESOLVED
    assert result.analysis_status_after is EventAnalysisStatus.PARTIALLY_RESOLVED
    assert result.projection.materializable_opinion_count == 1
    assert result.projection.extracted_opinion_count == 1
    assert result.projection.direct_unresolved_hint_count == 0
    assert len(result.projection.entries) == 1
    assert result.projection.entries[0].outcome is AssetResolutionStatus.RESOLVED

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
        assert analysis.status is EventAnalysisStatus.PARTIALLY_RESOLVED
        assert analysis.analysis_version == RECOVERY_SPEC.analysis_version
        assert analysis.model_version == RECOVERY_SPEC.model_version
        assert analysis.prompt_version == RECOVERY_SPEC.prompt_version
        assert analysis.schema_version == RECOVERY_SPEC.schema_version
        assert analysis.generated_time.replace(tzinfo=UTC) == generated_time
        assert analysis.calculated_at == calculated_before
        assert analysis.structured_output == structured_before
        assert analysis.provider_metadata == {
            "provider": "test-provider",
            "provider_response_id": "response-1",
        }
        assert analysis.structured_output["analysis_spec"] == RECOVERY_SPEC.model_dump(mode="json")
        assert "resolution_recovery" not in analysis.structured_output
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
        opinion_entries=(extracted("腾讯"),),
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


def test_resolution_only_boundary_materializes_cn_listings_without_llm_or_downstream(
    db_session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (
            ("中际旭创", "300308", "SZ"),
            ("华能国际", "600011", "SH"),
        ),
        (),
        opinion_entries=(
            extracted("中际旭创", symbol="300308", market="CN"),
            extracted("华能国际", symbol="SH600011", market="CN"),
        ),
    )
    with db_session_factory() as session:
        analysis_before = session.get(EventAnalysis, analysis_id)
        assert analysis_before is not None
        output_before = analysis_before.structured_output
        calculated_before = analysis_before.calculated_at

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("LLM or full-refresh service construction is not allowed")

    monkeypatch.setattr(recover_production_analysis, "_build_services", fail_if_called)
    monkeypatch.setattr(
        recover_production_analysis.OpenAIOpinionExtractor,
        "from_settings",
        fail_if_called,
    )
    monkeypatch.setattr(
        recover_production_analysis.OpenAICompatibleThesisComparator,
        "from_settings",
        fail_if_called,
    )

    kwargs = {
        "analysis_ids": (analysis_id,),
        "allowed_market_symbols": (("SZ", "300308"), ("SH", "600011")),
        "unit_of_work_factory": lambda: SqlAlchemyOpinionUnitOfWork(db_session_factory),
    }
    first = recover_production_analysis.run_resolution_materialization(**kwargs)
    second = recover_production_analysis.run_resolution_materialization(**kwargs)

    assert first["created"] == 2
    assert first["reused"] == 0
    assert first["llm_calls"] == {"analysis": 0, "thesis": 0, "other": 0}
    assert first["downstream_stages_run"] == []
    assert second["created"] == 0
    assert second["reused"] == 2
    assert second["llm_calls"] == {"analysis": 0, "thesis": 0, "other": 0}
    assert second["downstream_stages_run"] == []

    with db_session_factory() as session:
        analysis_after = session.get(EventAnalysis, analysis_id)
        assert analysis_after is not None
        assert analysis_after.structured_output == output_before
        assert analysis_after.calculated_at == calculated_before
        assert session.scalar(select(func.count()).select_from(Opinion)) == 2
        assert session.scalar(select(func.count()).select_from(AttentionOccurrence)) == 0
        assert session.scalar(select(func.count()).select_from(ThesisChange)) == 0
        assert session.scalar(select(func.count()).select_from(Signal)) == 0
        assert session.scalar(select(func.count()).select_from(IntelligenceEvent)) == 0


def test_recovery_can_select_analysis_by_event_and_version(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _, _ = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"),),
        (unresolved("腾讯"),),
        aliases=((0, "腾讯"),),
        opinion_entries=(extracted("腾讯"),),
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
        (),
        opinion_entries=(extracted("不存在的资产"),),
    )

    result = service(db_session_factory).recover(analysis_id=analysis_id)

    assert result.status is AssetRecoveryStatus.UNRESOLVED
    assert result.created_count == 0
    assert result.opinion_ids == ()
    assert result.unresolved_assets[0].reason == "NO_MATCHING_ASSET"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_dry_run_projects_without_materializing_or_mutating_analysis(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, generated_time, _ = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"),),
        (),
        opinion_entries=(extracted("腾讯", symbol="00700", market="HK"),),
    )
    with db_session_factory() as session:
        session.add(
            AssetAlias(
                asset_id=session.scalar(select(Asset.id)),
                alias="腾讯",
                normalized_alias="腾讯",
                alias_type="NAME",
                market="HK",
            )
        )
        session.commit()

    with db_session_factory() as session:
        before = session.get(EventAnalysis, analysis_id)
        assert before is not None
        before_status = before.status
        before_output = before.structured_output
        before_calculated_at = before.calculated_at

    result = service(db_session_factory).recover(analysis_id=analysis_id, dry_run=True)

    assert result.dry_run
    assert result.created_count == 0
    assert result.projection.materializable_opinion_count == 1
    assert result.calculated_at == generated_time
    with db_session_factory() as session:
        after = session.get(EventAnalysis, analysis_id)
        assert after is not None
        assert after.status is before_status
        assert after.structured_output == before_output
        assert after.calculated_at == before_calculated_at
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_allowlist_materializes_only_explicit_listing(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"), ("Other", "600000", "SH")),
        (),
        opinion_entries=(
            extracted("腾讯", symbol="00700", market="HK"),
            extracted("Other", symbol="600000", market="SH"),
        ),
    )
    result = service(db_session_factory).recover(
        analysis_id=analysis_id,
        allowed_market_symbols={("HK", "00700")},
    )

    assert result.created_count == 1
    assert result.projection.materializable_opinion_count == 1
    assert result.projection.entries[0].materializable
    assert result.projection.entries[1].outcome is AssetResolutionStatus.RESOLVED
    assert result.projection.entries[1].materialization_blocked_reason == "NOT_ALLOWLISTED"
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opinion)) == 1


def test_delta_scope_plans_only_requested_events(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, event_id, _, _ = seed_analysis(
        db_session_factory,
        (("Tencent Holdings", "00700", "HK"),),
        (),
        opinion_entries=(extracted("腾讯", symbol="00700", market="HK"),),
    )
    plans = service(db_session_factory).plan_many(
        event_ids=(event_id,),
        analysis_version=RECOVERY_SPEC.analysis_version,
    )

    assert len(plans) == 1
    assert plans[0].event_id == event_id
    assert plans[0].projection.materializable_opinion_count == 1


def test_cross_listing_name_only_resolution_stays_ambiguous(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (("CNOOC HK", "00883", "HK"), ("CNOOC SH", "600938", "SH")),
        (),
        aliases=((0, "中国海洋石油"), (1, "中国海洋石油")),
        opinion_entries=(extracted("中国海洋石油"),),
    )
    result = service(db_session_factory).recover(analysis_id=analysis_id)

    assert result.created_count == 0
    assert result.projection.entries[0].outcome is AssetResolutionStatus.AMBIGUOUS
    assert result.projection.materializable_opinion_count == 0
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0


def test_synthetic_six_listing_projection_materializes_seven_delta_mentions(
    db_session_factory: sessionmaker[Session],
) -> None:
    listings = (
        ("焦作万方", "000612", "SZ"),
        ("万国黄金集团", "03939", "HK"),
        ("中国海洋石油", "00883", "HK"),
        ("九毛九", "09922", "HK"),
        ("会稽山", "601579", "SH"),
        ("康方生物", "09926", "HK"),
    )
    targets = (
        ("焦作万方", "SZ", "000612"),
        ("焦作万方", "SZ", "000612"),
        ("万国黄金集团", "HK", "03939"),
        ("中国海洋石油", "HK", "00883"),
        ("九毛九", "HK", "09922"),
        ("会稽山", "SH", "601579"),
        ("康方生物", "HK", "09926"),
    )
    event_ids: list[UUID] = []
    analysis_ids: list[UUID] = []
    for index, (name, market, symbol) in enumerate(targets):
        analysis_id, event_id, _, _ = seed_analysis(
            db_session_factory,
            listings if index == 0 else (),
            (),
            opinion_entries=(extracted(name, market=market, symbol=symbol),),
        )
        analysis_ids.append(analysis_id)
        event_ids.append(event_id)

    materializer = service(db_session_factory)
    allowlist = {(market, symbol) for _, market, symbol in targets}
    first = materializer.materialize_many(
        event_ids=tuple(event_ids),
        analysis_version=RECOVERY_SPEC.analysis_version,
        allowed_market_symbols=allowlist,
    )
    second = materializer.materialize_many(
        analysis_ids=tuple(analysis_ids),
        allowed_market_symbols=allowlist,
    )

    assert len(first) == 7
    assert [item.created_count for item in first] == [1] * 7
    assert [item.projection.currently_resolved_count for item in first] == [1] * 7
    assert [item.created_count for item in second] == [0] * 7
    assert [item.reused_count for item in second] == [1] * 7
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 6
        assert session.scalar(select(func.count()).select_from(Opinion)) == 7
        analyses = list(
            session.scalars(select(EventAnalysis).where(EventAnalysis.id.in_(analysis_ids)))
        )
        assert len(analyses) == 7
        assert all(item.status is EventAnalysisStatus.PARTIALLY_RESOLVED for item in analyses)
        analysis = session.get(EventAnalysis, analysis_id)
        assert analysis is not None
        assert analysis.status is EventAnalysisStatus.PARTIALLY_RESOLVED


def test_ambiguous_asset_remains_unresolved_with_candidates(
    db_session_factory: sessionmaker[Session],
) -> None:
    analysis_id, _, _, _ = seed_analysis(
        db_session_factory,
        (("First", "F1", "HK"), ("Second", "F2", "HK")),
        (),
        aliases=((0, "同名资产"), (1, "同名资产")),
        opinion_entries=(extracted("同名资产"),),
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

    assert result.status is AssetRecoveryStatus.NO_UNRESOLVED
    assert result.projection.extracted_opinion_count == 0
    assert result.projection.direct_unresolved_hint_count == 1
    assert result.projection.entries[0].outcome is AssetResolutionStatus.RESOLVED
    assert not result.projection.entries[0].materializable
    assert result.opinion_ids == ()
    with db_session_factory() as session:
        analysis = session.get(EventAnalysis, analysis_id)
        assert analysis is not None
        assert analysis.status is EventAnalysisStatus.PARTIALLY_RESOLVED
        assert session.scalar(select(func.count()).select_from(Opinion)) == 0
