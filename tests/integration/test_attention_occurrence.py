from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    AnalysisSpec,
    AttentionEvidenceType,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    OpinionDirection,
)
from database.models import (
    Asset,
    AssetAlias,
    AttentionOccurrence,
    EventAnalysis,
    Investor,
    Opinion,
    RawEvent,
)
from database.repositories import AttentionOccurrenceRepository
from database.unit_of_work import SqlAlchemyAttentionUnitOfWork
from intelligence import AttentionOccurrenceService

ACTIVE_SPEC = AnalysisSpec.from_model_version("attention-active-v1")
OLD_SPEC = AnalysisSpec.from_model_version("attention-old-v1")
POLICY = EffectiveAnalysisPolicy(active_spec=ACTIVE_SPEC)


def add_analysis_opinion(
    session: Session,
    *,
    event: RawEvent,
    asset: Asset,
    spec: AnalysisSpec,
    status: EventAnalysisStatus = EventAnalysisStatus.SUCCESS,
) -> Opinion:
    analysis = EventAnalysis(
        event_id=event.id,
        analysis_version=spec.analysis_version,
        model_version=spec.model_version,
        prompt_version=spec.prompt_version,
        schema_version=spec.schema_version,
        status=status,
        investment_related=True,
        generated_time=event.published_time,
        calculated_at=event.published_time,
        confidence=0.8,
        structured_output={"analysis_spec": spec.model_dump(mode="json")},
        provider_metadata={},
    )
    session.add(analysis)
    session.flush()
    opinion = Opinion(
        event_id=event.id,
        analysis_id=analysis.id,
        investor_id=event.investor_id,
        asset_id=asset.id,
        direction=OpinionDirection.BULLISH,
        strength=70,
        confidence=0.8,
        thesis=["增长"],
        catalysts=[],
        risks=[],
        generated_time=event.published_time,
        model_version=spec.model_version,
    )
    session.add(opinion)
    session.flush()
    return opinion


def service(factory: sessionmaker[Session]) -> AttentionOccurrenceService:
    return AttentionOccurrenceService(
        lambda: SqlAlchemyAttentionUnitOfWork(factory),
        POLICY,
    )


def test_one_event_with_three_evidence_types_is_one_occurrence(
    db_session_factory: sessionmaker[Session],
) -> None:
    published_time = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    with db_session_factory() as session:
        investor = Investor(name="Investor", platform="xueqiu", platform_user_id="one")
        asset = Asset(name="比音勒芬", symbol="002832", market="SZ")
        session.add_all([investor, asset])
        session.flush()
        session.add_all(
            [
                AssetAlias(
                    asset_id=asset.id,
                    alias="比音勒芬",
                    normalized_alias="比音勒芬",
                    alias_type="NAME",
                    market="SZ",
                ),
                AssetAlias(
                    asset_id=asset.id,
                    alias="SZ002832",
                    normalized_alias="002832",
                    alias_type="SYMBOL",
                    market="SZ",
                ),
            ]
        )
        event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="xueqiu",
            url="https://example.test/attention/one",
            published_time=published_time,
            content="比音勒芬值得持续关注。//@原作者:比音勒芬原文",
            raw_data={
                "post_kind": "REPOST",
                "retweet_status_id": "nested-1",
                "retweeted_status": {
                    "id": "nested-1",
                    "symbol_id": "SZ002832",
                    "text": "原作者看多，但不能继承方向",
                },
            },
            hash=uuid4().hex + uuid4().hex,
            collected_time=published_time,
        )
        session.add(event)
        session.flush()
        opinion = add_analysis_opinion(
            session,
            event=event,
            asset=asset,
            spec=ACTIVE_SPEC,
        )
        session.commit()
        event_id = event.id
        asset_id = asset.id
        opinion_id = opinion.id

    first = service(db_session_factory).rebuild_event(event_id)
    second = service(db_session_factory).rebuild_event(event_id)

    assert first.created_count == 1
    assert second.created_count == 0
    assert second.updated_count == 1
    assert first.occurrence_ids == second.occurrence_ids
    with db_session_factory() as session:
        rows = AttentionOccurrenceRepository(session).list_by_event(
            event_id, "attention-occurrence-v1"
        )
        assert len(rows) == 1
        occurrence = rows[0]
        assert occurrence.asset_id == asset_id
        assert occurrence.published_time == published_time
        assert occurrence.opinion_id == opinion_id
        assert set(occurrence.evidence_types) == {
            AttentionEvidenceType.OPINION,
            AttentionEvidenceType.EXPLICIT_MENTION,
            AttentionEvidenceType.REPOST,
        }
        repost = next(
            item
            for item in occurrence.evidence
            if item.evidence_type is AttentionEvidenceType.REPOST
        )
        assert "direction" not in repost.details
        assert session.scalar(select(func.count()).select_from(AttentionOccurrence)) == 1


def test_inactive_analysis_does_not_add_opinion_evidence_or_fallback(
    db_session_factory: sessionmaker[Session],
) -> None:
    published_time = datetime(2026, 8, 2, tzinfo=UTC)
    with db_session_factory() as session:
        investor = Investor(name="Investor", platform="manual", platform_user_id="two")
        asset = Asset(name="Tencent", symbol="00700", market="HK")
        session.add_all([investor, asset])
        session.flush()
        event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="manual",
            url="https://example.test/attention/two",
            published_time=published_time,
            content="Tencent is mentioned.",
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
            collected_time=published_time,
        )
        session.add(event)
        session.flush()
        add_analysis_opinion(session, event=event, asset=asset, spec=OLD_SPEC)
        add_analysis_opinion(
            session,
            event=event,
            asset=asset,
            spec=ACTIVE_SPEC,
            status=EventAnalysisStatus.FAILED,
        )
        session.commit()
        event_id = event.id

    service(db_session_factory).rebuild_event(event_id)

    with db_session_factory() as session:
        occurrence = AttentionOccurrenceRepository(session).list_by_event(
            event_id, "attention-occurrence-v1"
        )[0]
        assert occurrence.evidence_types == (AttentionEvidenceType.EXPLICIT_MENTION,)
        assert occurrence.analysis_id is None
        assert occurrence.opinion_id is None


def test_repost_without_top_level_mention_is_repost_only(
    db_session_factory: sessionmaker[Session],
) -> None:
    published_time = datetime(2026, 8, 3, tzinfo=UTC)
    with db_session_factory() as session:
        investor = Investor(name="Investor", platform="xueqiu", platform_user_id="three")
        asset = Asset(name="山西焦煤", symbol="000983", market="SZ")
        session.add_all([investor, asset])
        session.flush()
        event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="xueqiu",
            url="https://example.test/attention/three",
            published_time=published_time,
            content="转发。",
            raw_data={
                "post_kind": "REPOST",
                "retweet_status_id": "nested-2",
                "retweeted_status": {
                    "id": "nested-2",
                    "target": "/S/SZ000983/nested-2",
                    "text": "山西焦煤看多内容不得作为当前作者观点",
                },
            },
            hash=uuid4().hex + uuid4().hex,
            collected_time=published_time,
        )
        session.add(event)
        session.commit()
        event_id = event.id

    service(db_session_factory).rebuild_event(event_id)

    with db_session_factory() as session:
        occurrence = AttentionOccurrenceRepository(session).list_by_event(
            event_id, "attention-occurrence-v1"
        )[0]
        assert occurrence.evidence_types == (AttentionEvidenceType.REPOST,)
        assert occurrence.analysis_id is None
        assert occurrence.opinion_id is None


def test_nested_repost_text_does_not_create_explicit_mention(
    db_session_factory: sessionmaker[Session],
) -> None:
    published_time = datetime(2026, 8, 4, tzinfo=UTC)
    with db_session_factory() as session:
        investor = Investor(name="Investor", platform="xueqiu", platform_user_id="four")
        asset = Asset(name="山西焦煤", symbol="000983", market="SZ")
        session.add_all([investor, asset])
        session.flush()
        session.add(
            AssetAlias(
                asset_id=asset.id,
                alias="山西焦煤",
                normalized_alias="山西焦煤",
                alias_type="NAME",
                market=None,
            )
        )
        event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="xueqiu",
            url="https://example.test/attention/four",
            published_time=published_time,
            content="转发观点。//@原作者:山西焦煤值得关注",
            raw_data={
                "post_kind": "REPOST",
                "retweet_status_id": "nested-3",
                "retweeted_status": {
                    "id": "nested-3",
                    "symbol_id": "SZ000983",
                    "text": "山西焦煤看多内容",
                },
            },
            hash=uuid4().hex + uuid4().hex,
            collected_time=published_time,
        )
        session.add(event)
        session.commit()
        event_id = event.id

    service(db_session_factory).rebuild_event(event_id)

    with db_session_factory() as session:
        occurrence = AttentionOccurrenceRepository(session).list_by_event(
            event_id, "attention-occurrence-v1"
        )[0]
        assert occurrence.evidence_types == (AttentionEvidenceType.REPOST,)
