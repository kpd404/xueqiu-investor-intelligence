"""Signal selection through real effective ThesisChange queries and persistence."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from config import (
    Settings,
    get_production_analysis_policy,
    get_production_thesis_comparison_policy,
)
from contracts import (
    PRODUCTION_OPINION_ANALYSIS_VERSION,
    PRODUCTION_THESIS_COMPARISON_VERSION,
    AnalysisSpec,
    EventAnalysisStatus,
    OpinionDirection,
    SignalType,
    ThesisChangeCreate,
    ThesisChangeType,
)
from database.models import Asset, EventAnalysis, Investor, Opinion, RawEvent, Signal, ThesisChange
from database.repositories.thesis_changes import ThesisChangeRepository
from signal_engine.generator import SqlAlchemySignalSourceReader
from signal_engine.service import SignalGenerator

FACT_TIME = datetime(2026, 9, 2, 9, 30, tzinfo=UTC)
CALCULATED_AT = FACT_TIME + timedelta(days=10)
THESIS_SIGNALS = frozenset({SignalType.THESIS_CHANGE})
TYPE_CASES = (
    (ThesisChangeType.THESIS_REINFORCED, True),
    (ThesisChangeType.THESIS_EXTENDED, True),
    (ThesisChangeType.THESIS_CHANGED, True),
    (ThesisChangeType.NEW_THESIS, False),
    (ThesisChangeType.THESIS_UNCHANGED, False),
    (ThesisChangeType.INSUFFICIENT_EVIDENCE, False),
)


@pytest.fixture
def production_policies(monkeypatch):
    # Only configuration is isolated. Production policy validation and all SQL
    # source selectors execute normally; no extractor/comparator is instantiated.
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        llm_provider_id="deepseek",
        llm_model="deepseek-v4-flash",
        llm_api_key="",
        production_opinion_analysis_version=PRODUCTION_OPINION_ANALYSIS_VERSION,
        production_thesis_comparison_version=PRODUCTION_THESIS_COMPARISON_VERSION,
    )
    monkeypatch.setattr("config.production.get_settings", lambda: settings)
    return get_production_analysis_policy(), get_production_thesis_comparison_policy()


def _add_opinion(session, investor, asset, spec, published_time, status):
    raw_event = RawEvent(
        investor_id=investor.id,
        event_type="POST",
        source="manual",
        url=f"https://example.test/signal/{uuid4()}",
        published_time=published_time,
        content="Recorded thesis evidence",
        raw_data={},
        hash=uuid4().hex + uuid4().hex,
        collected_time=CALCULATED_AT,
    )
    session.add(raw_event)
    session.flush()
    analysis = EventAnalysis(
        event_id=raw_event.id,
        analysis_version=spec.analysis_version,
        model_version=spec.model_version,
        prompt_version=spec.prompt_version,
        schema_version=spec.schema_version,
        status=status,
        investment_related=True,
        generated_time=CALCULATED_AT,
        calculated_at=CALCULATED_AT,
        confidence=0.9,
        structured_output={"analysis_spec": spec.model_dump(mode="json")},
    )
    session.add(analysis)
    session.flush()
    opinion = Opinion(
        event_id=raw_event.id,
        analysis_id=analysis.id,
        investor_id=investor.id,
        asset_id=asset.id,
        direction=OpinionDirection.BULLISH,
        strength=70,
        confidence=0.9,
        thesis=["Recorded thesis"],
        catalysts=[],
        risks=[],
        generated_time=CALCULATED_AT,
        model_version=spec.model_version,
    )
    session.add(opinion)
    session.flush()
    return opinion


def _seed_change(factory, policies, change_type, *, exclusion=None, partial=False):
    opinion_policy, comparison_policy = policies
    spec = opinion_policy.active_spec
    if exclusion == "inactive_analysis":
        spec = AnalysisSpec.from_model_version("inactive-opinion-model")
    comparison_version = comparison_policy.active_analysis_version
    if exclusion == "inactive_comparison":
        comparison_version = "inactive-comparison"
    status = EventAnalysisStatus.PARTIALLY_RESOLVED if partial else EventAnalysisStatus.SUCCESS
    with factory() as session:
        investor = Investor(
            name="Signal Investor", platform="manual", platform_user_id=str(uuid4())
        )
        asset = Asset(name="Signal Asset", market="SH", symbol=uuid4().hex[:8])
        session.add_all([investor, asset])
        session.flush()
        previous = None
        if change_type is not ThesisChangeType.NEW_THESIS:
            previous = _add_opinion(
                session, investor, asset, spec, FACT_TIME - timedelta(days=1), status
            )
        current = _add_opinion(
            session,
            investor,
            asset,
            spec,
            FACT_TIME,
            EventAnalysisStatus.FAILED if exclusion == "failed_analysis" else status,
        )
        command = ThesisChangeCreate(
            investor_id=investor.id,
            asset_id=asset.id,
            previous_opinion_id=previous.id if previous else None,
            current_opinion_id=current.id,
            previous_event_id=previous.event_id if previous else None,
            current_event_id=current.event_id,
            effective_time=FACT_TIME,
            change_type=change_type,
            confidence=0.9,
            summary="Recorded comparison",
            evidence=("Traceable comparison evidence",),
            opinion_analysis_version=(
                "inactive-artifact-policy"
                if exclusion == "inactive_artifact_policy"
                else spec.analysis_version
            ),
            comparison_version=comparison_version,
            calculated_at=CALCULATED_AT,
            input_identity=(
                f"{previous.id if previous else 'first'}:{current.id}:{comparison_version}"
            ),
        )
        change = ThesisChangeRepository(session).add_if_absent(command)
        if exclusion == "superseded_predecessor":
            # A late fact becomes the immediate predecessor, leaving the old
            # comparison persisted but no longer effective.
            _add_opinion(session, investor, asset, spec, FACT_TIME - timedelta(hours=12), status)
        session.commit()
        return change


def _candidates(session, **scope):
    return SqlAlchemySignalSourceReader(session).list_candidates(
        signal_types=THESIS_SIGNALS, **scope
    )


@pytest.mark.parametrize("change_type,eligible", TYPE_CASES, ids=[x[0].value for x in TYPE_CASES])
def test_thesis_signal_requires_material_change(
    db_session_factory, production_policies, change_type, eligible
):
    change = _seed_change(db_session_factory, production_policies, change_type)
    with db_session_factory() as session:
        effective = ThesisChangeRepository(session).list_effective(
            production_policies[0].as_effective_policy(),
            production_policies[1].active_analysis_version,
        )
        # Excluded types must reach the real selector; an invalid fixture must
        # not make the material-change assertion pass accidentally.
        assert [item.id for item in effective] == [change.id]
        candidates = _candidates(session)
    assert len(candidates) == int(eligible)
    if eligible:
        candidate = candidates[0]
        assert candidate.source_id == change.id
        assert candidate.source_type == "ThesisChange"
        assert candidate.asset_id == change.asset_id
        assert candidate.investor_id == change.investor_id
        assert candidate.observed_at == change.effective_time == FACT_TIME
        assert candidate.observed_at != change.calculated_at
        assert candidate.metadata == {
            "change_type": change_type.value,
            "current_opinion_id": str(change.current_opinion_id),
            "previous_opinion_id": str(change.previous_opinion_id),
        }


@pytest.mark.parametrize(
    "exclusion",
    (
        "inactive_analysis",
        "inactive_comparison",
        "inactive_artifact_policy",
        "failed_analysis",
        "superseded_predecessor",
    ),
)
def test_material_thesis_signal_still_requires_effective_source(
    db_session_factory, production_policies, exclusion
):
    change = _seed_change(
        db_session_factory,
        production_policies,
        ThesisChangeType.THESIS_CHANGED,
        exclusion=exclusion,
    )
    with db_session_factory() as session:
        assert session.get(ThesisChange, change.id) is not None
        assert (
            ThesisChangeRepository(session).list_effective(
                production_policies[0].as_effective_policy(),
                production_policies[1].active_analysis_version,
            )
            == []
        )
        assert _candidates(session) == ()


def test_partial_analysis_material_thesis_signal_remains_eligible(
    db_session_factory, production_policies
):
    change = _seed_change(
        db_session_factory, production_policies, ThesisChangeType.THESIS_EXTENDED, partial=True
    )
    with db_session_factory() as session:
        assert [item.source_id for item in _candidates(session)] == [change.id]


@pytest.mark.parametrize(
    "scope,expected",
    (
        ("asset", True),
        ("event", True),
        ("both", True),
        ("wrong_asset", False),
        ("wrong_event", False),
        ("previous_event", False),
        ("empty_assets", False),
        ("empty_events", False),
    ),
)
def test_material_thesis_signal_preserves_scope_filters(
    db_session_factory, production_policies, scope, expected
):
    change = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    other = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_EXTENDED)
    scopes = {
        "asset": {"asset_ids": frozenset({change.asset_id})},
        "event": {"event_ids": frozenset({change.current_event_id})},
        "both": {
            "asset_ids": frozenset({change.asset_id}),
            "event_ids": frozenset({change.current_event_id}),
        },
        "wrong_asset": {
            "asset_ids": frozenset({other.asset_id}),
            "event_ids": frozenset({change.current_event_id}),
        },
        "wrong_event": {
            "asset_ids": frozenset({change.asset_id}),
            "event_ids": frozenset({other.current_event_id}),
        },
        "previous_event": {"event_ids": frozenset({change.previous_event_id})},
        "empty_assets": {"asset_ids": frozenset()},
        "empty_events": {"event_ids": frozenset()},
    }
    with db_session_factory() as session:
        candidates = _candidates(session, **scopes[scope])
    assert [item.source_id for item in candidates] == ([change.id] if expected else [])


def _source_rows(session):
    return {
        table.name: tuple(session.execute(select(table)).mappings())
        for table in (Opinion.__table__, ThesisChange.__table__)
    }


def test_thesis_signal_dry_run_and_generation_are_idempotent_and_preserve_sources(
    db_session_factory, production_policies
):
    changes = [
        (_seed_change(db_session_factory, production_policies, change_type), eligible)
        for change_type, eligible in TYPE_CASES
    ]
    expected_ids = {change.id for change, eligible in changes if eligible}
    with db_session_factory() as session:
        before = _source_rows(session)
    generator = SignalGenerator.from_production(db_session_factory)
    plan = generator.dry_run(signal_types=THESIS_SIGNALS)
    assert plan.dry_run is True
    assert plan.created_count == 3
    assert plan.reused_count == 0
    assert plan.signals == ()
    assert {item.source_id for item in plan.candidates} == expected_ids
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 0
        assert _source_rows(session) == before

    first = generator.generate(signal_types=THESIS_SIGNALS)
    second = generator.generate_many(signal_types=THESIS_SIGNALS)
    assert first.created_count == 3
    assert first.reused_count == 0
    assert second.created_count == 0
    assert second.reused_count == 3
    assert first.duplicate_count == second.duplicate_count == 0
    assert {item.source_id for item in first.signals} == expected_ids
    assert {item.id for item in first.signals} == {item.id for item in second.signals}
    assert all(item.observed_at == FACT_TIME for item in first.signals)
    planned_by_source = {item.source_id: item for item in plan.candidates}
    for signal in first.signals:
        candidate = planned_by_source[signal.source_id]
        assert signal.signal_type is SignalType.THESIS_CHANGE
        assert signal.source_type == candidate.source_type == "ThesisChange"
        assert signal.asset_id == candidate.asset_id
        assert signal.investor_id == candidate.investor_id
        assert signal.metadata == candidate.metadata
    after_plan = generator.dry_run(signal_types=THESIS_SIGNALS)
    assert after_plan.created_count == 0
    assert after_plan.reused_count == 3
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 3
        assert _source_rows(session) == before
