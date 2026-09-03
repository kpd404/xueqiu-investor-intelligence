import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    AnalysisSpec,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    OpinionDirection,
    ThesisChangeType,
    ThesisComparisonResult,
    ThesisComparisonSpec,
)
from database.models import Asset, EventAnalysis, Investor, Opinion, RawEvent, ThesisChange
from database.repositories import ThesisChangeRepository
from database.unit_of_work import SqlAlchemyThesisChangeUnitOfWork
from intelligence import ThesisChangeService, ThesisOpinionNotFoundError

ACTIVE_SPEC = AnalysisSpec.from_model_version("thesis-active-v1")
OLD_SPEC = AnalysisSpec.from_model_version("thesis-old-v1")
POLICY = EffectiveAnalysisPolicy(active_spec=ACTIVE_SPEC)
COMPARISON_SPEC = ThesisComparisonSpec.from_analysis_spec(
    AnalysisSpec.for_provider(
        provider_id="test-provider",
        model_version="test-model",
        prompt_version="thesis-comparison-v1",
        schema_version="thesis-comparison-result-v1",
        analysis_policy_version="thesis-comparison-policy-v1",
    )
)


class RecordingComparator:
    comparison_spec = COMPARISON_SPEC

    def __init__(self, result: ThesisComparisonResult) -> None:
        self.result = result
        self.calls = []

    async def compare(self, input_data: object) -> ThesisComparisonResult:
        self.calls.append(input_data)
        return self.result


def _seed_pair(
    factory: sessionmaker[Session],
    *,
    count: int = 2,
    active_spec: AnalysisSpec = ACTIVE_SPEC,
    include_old: bool = False,
    repost: bool = False,
) -> tuple[UUID, UUID, list[UUID]]:
    with factory() as session:
        investor = Investor(
            name="Thesis Investor",
            platform="manual",
            platform_user_id=f"thesis-{uuid4()}",
        )
        asset = Asset(name="Thesis Asset", market="SH", symbol="THESIS")
        session.add_all([investor, asset])
        session.flush()
        opinion_ids: list[UUID] = []
        for index in range(count):
            content = f"Author thesis {index}"
            raw_data = {}
            if repost:
                content += "//@quoted speaker: nested thesis"
                raw_data = {
                    "post_kind": "REPOST",
                    "retweeted_status": {"id": f"nested-{index}", "text": "nested thesis"},
                }
            event = RawEvent(
                investor_id=investor.id,
                event_type="POST",
                source="manual",
                url=f"https://example.test/thesis/{uuid4()}",
                published_time=datetime(2026, 9, 1, tzinfo=UTC) + timedelta(days=index),
                content=content,
                raw_data=raw_data,
                hash=uuid4().hex + uuid4().hex,
                collected_time=datetime(2026, 9, 1, tzinfo=UTC) + timedelta(days=index),
            )
            session.add(event)
            session.flush()
            analysis = EventAnalysis(
                event_id=event.id,
                analysis_version=active_spec.analysis_version,
                model_version=active_spec.model_version,
                prompt_version=active_spec.prompt_version,
                schema_version=active_spec.schema_version,
                status=EventAnalysisStatus.SUCCESS,
                investment_related=True,
                generated_time=event.published_time + timedelta(hours=1),
                calculated_at=event.published_time + timedelta(hours=1),
                confidence=0.8,
                structured_output={"analysis_spec": active_spec.model_dump(mode="json")},
                provider_metadata={},
            )
            session.add(analysis)
            session.flush()
            opinion = Opinion(
                event_id=event.id,
                analysis_id=analysis.id,
                investor_id=investor.id,
                asset_id=asset.id,
                direction=(OpinionDirection.BULLISH if index == 0 else OpinionDirection.BEARISH),
                strength=60 + index,
                confidence=0.8,
                thesis=[f"core rationale {index}"],
                catalysts=[],
                risks=[],
                time_horizon=None,
                generated_time=analysis.generated_time,
                model_version=active_spec.model_version,
            )
            session.add(opinion)
            session.flush()
            opinion_ids.append(opinion.id)
        if include_old:
            old_event = RawEvent(
                investor_id=investor.id,
                event_type="POST",
                source="manual",
                url=f"https://example.test/thesis/old/{uuid4()}",
                published_time=datetime(2026, 8, 1, tzinfo=UTC),
                content="old author thesis",
                raw_data={},
                hash=uuid4().hex + uuid4().hex,
                collected_time=datetime(2026, 8, 1, tzinfo=UTC),
            )
            session.add(old_event)
            session.flush()
            old_analysis = EventAnalysis(
                event_id=old_event.id,
                analysis_version=OLD_SPEC.analysis_version,
                model_version=OLD_SPEC.model_version,
                prompt_version=OLD_SPEC.prompt_version,
                schema_version=OLD_SPEC.schema_version,
                status=EventAnalysisStatus.SUCCESS,
                investment_related=True,
                generated_time=old_event.published_time,
                calculated_at=old_event.published_time,
                confidence=0.8,
                structured_output={"analysis_spec": OLD_SPEC.model_dump(mode="json")},
                provider_metadata={},
            )
            session.add(old_analysis)
            session.flush()
            session.add(
                Opinion(
                    event_id=old_event.id,
                    analysis_id=old_analysis.id,
                    investor_id=investor.id,
                    asset_id=asset.id,
                    direction=OpinionDirection.BULLISH,
                    strength=70,
                    confidence=0.8,
                    thesis=["old rationale"],
                    catalysts=[],
                    risks=[],
                    generated_time=old_event.published_time,
                    model_version=OLD_SPEC.model_version,
                )
            )
        session.commit()
        return investor.id, asset.id, opinion_ids


def _service(
    factory: sessionmaker[Session],
    comparator: RecordingComparator,
    policy: EffectiveAnalysisPolicy = POLICY,
) -> ThesisChangeService:
    return ThesisChangeService(
        lambda: SqlAlchemyThesisChangeUnitOfWork(factory),
        policy,
        comparator,
    )


def _result(change_type: ThesisChangeType) -> ThesisComparisonResult:
    return ThesisComparisonResult(
        change_type=change_type,
        confidence=0.75,
        summary=f"fixture {change_type.value}",
        evidence=("fixture evidence",),
    )


def test_first_opinion_is_new_thesis_without_comparator_call(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory, count=1)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_CHANGED))

    result = asyncio.run(_service(db_session_factory, comparator).process(opinion_ids[0]))

    assert result.change_type is ThesisChangeType.NEW_THESIS
    assert result.previous_opinion_id is None
    assert result.created is True
    assert comparator.calls == []
    with db_session_factory() as session:
        artifact = session.get(ThesisChange, result.thesis_change_id)
        assert artifact is not None
        assert artifact.previous_event_id is None
        assert artifact.effective_time.replace(tzinfo=UTC) == datetime(2026, 9, 1, tzinfo=UTC)
        assert '"previous_opinion_id":"NONE"' in artifact.input_identity


@pytest.mark.parametrize(
    "change_type",
    [
        ThesisChangeType.THESIS_UNCHANGED,
        ThesisChangeType.THESIS_REINFORCED,
        ThesisChangeType.THESIS_EXTENDED,
        ThesisChangeType.THESIS_CHANGED,
        ThesisChangeType.INSUFFICIENT_EVIDENCE,
    ],
)
def test_comparator_result_is_persisted_without_direction_shortcuts(
    db_session_factory: sessionmaker[Session],
    change_type: ThesisChangeType,
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory)
    comparator = RecordingComparator(_result(change_type))
    service = _service(db_session_factory, comparator)

    first = asyncio.run(service.process(opinion_ids[0]))
    second = asyncio.run(service.process(opinion_ids[1]))

    assert first.change_type is ThesisChangeType.NEW_THESIS
    assert second.change_type is change_type
    assert second.previous_opinion_id == opinion_ids[0]
    assert len(comparator.calls) == 1
    comparison_input = comparator.calls[0]
    assert comparison_input.previous.opinion_id == opinion_ids[0]
    assert comparison_input.current.opinion_id == opinion_ids[1]
    assert comparison_input.previous.current_author_text == "Author thesis 0"
    assert comparison_input.current.current_author_text == "Author thesis 1"


def test_persistence_is_idempotent_for_same_pair_and_comparison_version(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_REINFORCED))
    service = _service(db_session_factory, comparator)

    asyncio.run(service.process(opinion_ids[0]))
    first = asyncio.run(service.process(opinion_ids[1]))
    second = asyncio.run(service.process(opinion_ids[1]))

    assert first.thesis_change_id == second.thesis_change_id
    assert first.created is True
    assert second.created is False
    assert len(comparator.calls) == 1
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ThesisChange)) == 2


def test_comparison_input_excludes_nested_repost_text(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory, repost=True)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_REINFORCED))
    service = _service(db_session_factory, comparator)

    asyncio.run(service.process(opinion_ids[0]))
    asyncio.run(service.process(opinion_ids[1]))

    comparison_input = comparator.calls[0]
    assert comparison_input.previous.current_author_text == "Author thesis 0"
    assert comparison_input.current.current_author_text == "Author thesis 1"
    assert "nested thesis" not in comparison_input.current.current_author_text


def test_inactive_opinion_is_excluded_from_predecessor_timeline(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory, count=1, include_old=True)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_CHANGED))
    with db_session_factory() as session:
        old_opinion = session.scalar(
            select(Opinion)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .where(EventAnalysis.analysis_version == OLD_SPEC.analysis_version)
        )
        assert old_opinion is not None
        old_opinion_id = old_opinion.id

    result = asyncio.run(_service(db_session_factory, comparator).process(opinion_ids[0]))

    assert result.change_type is ThesisChangeType.NEW_THESIS
    assert result.previous_opinion_id is None
    with pytest.raises(ThesisOpinionNotFoundError):
        asyncio.run(_service(db_session_factory, comparator).process(old_opinion_id))


def test_as_of_excludes_future_opinions_and_uses_immediate_predecessor(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory, count=3)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_UNCHANGED))
    service = _service(db_session_factory, comparator)

    result = asyncio.run(
        service.process(
            opinion_ids[1],
            as_of=datetime(2026, 9, 2, 23, 59, tzinfo=UTC),
        )
    )

    assert result.change_type is ThesisChangeType.THESIS_UNCHANGED
    assert result.previous_opinion_id == opinion_ids[0]
    assert comparator.calls[0].current.opinion_id == opinion_ids[1]


def test_late_historical_opinion_creates_new_predecessor_pair(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory, count=2)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_EXTENDED))
    service = _service(db_session_factory, comparator)

    initial = asyncio.run(service.process(opinion_ids[1]))
    with db_session_factory() as session:
        investor = session.scalar(select(Investor).where(Investor.name == "Thesis Investor"))
        asset = session.scalar(select(Asset).where(Asset.name == "Thesis Asset"))
        assert investor is not None and asset is not None
        event = RawEvent(
            investor_id=investor.id,
            event_type="POST",
            source="manual",
            url=f"https://example.test/thesis/late/{uuid4()}",
            published_time=datetime(2026, 9, 1, 12, tzinfo=UTC),
            content="Recovered historical thesis",
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
            collected_time=datetime(2026, 9, 3, tzinfo=UTC),
        )
        session.add(event)
        session.flush()
        analysis = EventAnalysis(
            event_id=event.id,
            analysis_version=ACTIVE_SPEC.analysis_version,
            model_version=ACTIVE_SPEC.model_version,
            prompt_version=ACTIVE_SPEC.prompt_version,
            schema_version=ACTIVE_SPEC.schema_version,
            status=EventAnalysisStatus.SUCCESS,
            investment_related=True,
            generated_time=datetime(2026, 9, 3, tzinfo=UTC),
            calculated_at=datetime(2026, 9, 3, tzinfo=UTC),
            confidence=0.8,
            structured_output={"analysis_spec": ACTIVE_SPEC.model_dump(mode="json")},
            provider_metadata={},
        )
        session.add(analysis)
        session.flush()
        recovered = Opinion(
            event_id=event.id,
            analysis_id=analysis.id,
            investor_id=investor.id,
            asset_id=asset.id,
            direction=OpinionDirection.BULLISH,
            strength=55,
            confidence=0.7,
            thesis=["recovered rationale"],
            catalysts=[],
            risks=[],
            time_horizon=None,
            generated_time=datetime(2026, 9, 3, tzinfo=UTC),
            model_version=ACTIVE_SPEC.model_version,
        )
        session.add(recovered)
        session.commit()
        recovered_id = recovered.id

    asyncio.run(service.process(recovered_id))
    revised = asyncio.run(service.process(opinion_ids[1]))

    assert initial.previous_opinion_id == opinion_ids[0]
    assert revised.previous_opinion_id == recovered_id
    assert revised.created is True
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ThesisChange)) == 3
        effective = ThesisChangeRepository(session).list_effective(POLICY)
        effective_ids = {item.id for item in effective}
        assert initial.thesis_change_id not in effective_ids
        assert revised.thesis_change_id in effective_ids


def test_late_opinion_before_first_rebuilds_effective_artifact_selection(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, opinion_ids = _seed_pair(db_session_factory, count=2)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_UNCHANGED))
    service = _service(db_session_factory, comparator)

    first = asyncio.run(service.process(opinion_ids[0]))
    second = asyncio.run(service.process(opinion_ids[1]))
    with db_session_factory() as session:
        event = RawEvent(
            investor_id=investor_id,
            event_type="POST",
            source="manual",
            url=f"https://example.test/thesis/earlier/{uuid4()}",
            published_time=datetime(2026, 8, 31, tzinfo=UTC),
            content="Earlier recovered thesis",
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
            collected_time=datetime(2026, 9, 3, tzinfo=UTC),
        )
        session.add(event)
        session.flush()
        analysis = EventAnalysis(
            event_id=event.id,
            analysis_version=ACTIVE_SPEC.analysis_version,
            model_version=ACTIVE_SPEC.model_version,
            prompt_version=ACTIVE_SPEC.prompt_version,
            schema_version=ACTIVE_SPEC.schema_version,
            status=EventAnalysisStatus.SUCCESS,
            investment_related=True,
            generated_time=datetime(2026, 9, 3, tzinfo=UTC),
            calculated_at=datetime(2026, 9, 3, tzinfo=UTC),
            confidence=0.8,
            structured_output={"analysis_spec": ACTIVE_SPEC.model_dump(mode="json")},
            provider_metadata={},
        )
        session.add(analysis)
        session.flush()
        earlier = Opinion(
            event_id=event.id,
            analysis_id=analysis.id,
            investor_id=investor_id,
            asset_id=asset_id,
            direction=OpinionDirection.BULLISH,
            strength=50,
            confidence=0.7,
            thesis=["earlier rationale"],
            catalysts=[],
            risks=[],
            time_horizon=None,
            generated_time=datetime(2026, 9, 3, tzinfo=UTC),
            model_version=ACTIVE_SPEC.model_version,
        )
        session.add(earlier)
        session.commit()
        earlier_id = earlier.id

    recovered = asyncio.run(service.process(earlier_id))
    revised_first = asyncio.run(service.process(opinion_ids[0]))
    revised_second = asyncio.run(service.process(opinion_ids[1]))

    assert first.change_type is ThesisChangeType.NEW_THESIS
    assert second.previous_opinion_id == opinion_ids[0]
    assert recovered.change_type is ThesisChangeType.NEW_THESIS
    assert recovered.previous_opinion_id is None
    assert revised_first.previous_opinion_id == earlier_id
    assert revised_second.previous_opinion_id == opinion_ids[0]
    with db_session_factory() as session:
        effective = ThesisChangeRepository(session).list_effective(POLICY)
        effective_by_current = {item.current_opinion_id: item for item in effective}
        assert effective_by_current[earlier_id].previous_opinion_id is None
        assert effective_by_current[opinion_ids[0]].previous_opinion_id == earlier_id
        assert effective_by_current[opinion_ids[1]].previous_opinion_id == opinion_ids[0]
        assert first.thesis_change_id not in {item.id for item in effective}
        assert second.thesis_change_id in {item.id for item in effective}


def test_missing_fields_are_not_interpreted_by_service_as_removals(
    db_session_factory: sessionmaker[Session],
) -> None:
    _, _, opinion_ids = _seed_pair(db_session_factory)
    comparator = RecordingComparator(_result(ThesisChangeType.THESIS_UNCHANGED))
    service = _service(db_session_factory, comparator)

    asyncio.run(service.process(opinion_ids[0]))
    asyncio.run(service.process(opinion_ids[1]))

    current = comparator.calls[0].current
    assert current.catalysts == ()
    assert current.risks == ()
    assert current.time_horizon is None
