"""Persist legacy Signals directly, then exercise real source selection/aggregation."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select

from contracts import (
    EventAnalysisStatus,
    IntelligenceEventCreate,
    IntelligenceEventEvidenceCreate,
    IntelligenceEventState,
    IntelligenceEventType,
    SignalCreate,
    SignalState,
    SignalType,
    ThesisChangeCreate,
    ThesisChangeType,
)
from database.models import (
    Asset,
    IntelligenceEvent,
    IntelligenceEventEvidence,
    Investor,
    Opinion,
    Signal,
    ThesisChange,
)
from database.repositories.intelligence_event_evidence import IntelligenceEventEvidenceRepository
from database.repositories.intelligence_events import IntelligenceEventRepository
from database.repositories.thesis_changes import ThesisChangeRepository
from database.unit_of_work import (
    SqlAlchemyIntelligenceEventUnitOfWork,
    SqlAlchemyIntelligenceFeedUnitOfWork,
)
from intelligence.events.aggregator import IntelligenceEventAggregator
from signal_engine.repository import SignalRepository
from tests.integration import test_thesis_change_signals as signal_fixtures
from tests.integration.test_thesis_change_signals import (
    FACT_TIME,
    TYPE_CASES,
    _add_opinion,
    _seed_change,
)

production_policies = signal_fixtures.production_policies


def _persist_signal(factory, change, **updates):
    # Intentionally bypass the corrected generator: legacy writers could save
    # any change category, wrong source identities, and misleading metadata.
    command = SignalCreate(
        asset_id=change.asset_id,
        investor_id=change.investor_id,
        signal_type=SignalType.THESIS_CHANGE,
        source_type="ThesisChange",
        source_id=change.id,
        created_at=FACT_TIME + timedelta(days=10),
        observed_at=change.effective_time,
        metadata={"change_type": "THESIS_CHANGED"},
    ).model_copy(update=updates)
    with factory() as session:
        signal, created = SignalRepository(session).add_if_absent(command)
        assert created
        session.commit()
        return signal


def _effective(repository, policies):
    return repository.list_effective_thesis_changes(
        policies[0].as_effective_policy(), policies[1].active_analysis_version
    )


def _history(session):
    return {
        table.name: tuple(session.execute(select(table)).mappings())
        for table in (Signal.__table__, Opinion.__table__, ThesisChange.__table__)
    }


def _assert_aggregation(factory, policies, signal, eligible):
    aggregator = IntelligenceEventAggregator.from_production(factory)
    with factory() as session:
        before = _history(session)
    plan = aggregator.dry_run()
    assert len(plan.candidates) == int(eligible)
    assert plan.created_evidence_count == int(eligible)
    with factory() as session:
        assert session.scalars(select(IntelligenceEvent)).all() == []
        assert session.scalars(select(IntelligenceEventEvidence)).all() == []
        assert _history(session) == before
        repository = SignalRepository(session)
        assert [item.id for item in _effective(repository, policies)] == (
            [signal.id] if eligible else []
        )
        assert repository.get(signal.id) == signal
        assert repository.list() == (signal,)
        assert repository.list_by_asset(signal.asset_id) == (signal,)
        assert not session.new and not session.dirty and not session.deleted
    first = aggregator.aggregate()
    second = aggregator.aggregate_many()
    assert first.created_event_count == first.created_evidence_count == int(eligible)
    assert second.created_event_count == second.created_evidence_count == 0
    assert second.reused_event_count == second.reused_evidence_count == int(eligible)
    if eligible:
        assert first.events[0].id == second.events[0].id
    with factory() as session:
        assert {link.signal_id for link in session.scalars(select(IntelligenceEventEvidence))} == (
            {signal.id} if eligible else set()
        )
        assert _history(session) == before


@pytest.mark.parametrize(
    "change_type,eligible", TYPE_CASES, ids=[item[0].value for item in TYPE_CASES]
)
def test_legacy_thesis_signals_require_material_sources(
    db_session_factory, production_policies, change_type, eligible
):
    change = _seed_change(db_session_factory, production_policies, change_type)
    signal = _persist_signal(db_session_factory, change)
    _assert_aggregation(db_session_factory, production_policies, signal, eligible)


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
def test_persisted_material_signal_requires_current_effective_source(
    db_session_factory, production_policies, exclusion
):
    change = _seed_change(
        db_session_factory,
        production_policies,
        ThesisChangeType.THESIS_CHANGED,
        exclusion=exclusion,
    )
    signal = _persist_signal(db_session_factory, change)
    _assert_aggregation(db_session_factory, production_policies, signal, False)


def test_partial_analysis_source_remains_effective(db_session_factory, production_policies):
    change = _seed_change(
        db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED, partial=True
    )
    signal = _persist_signal(db_session_factory, change, metadata={"change_type": "NEW_THESIS"})
    _assert_aggregation(db_session_factory, production_policies, signal, True)


@pytest.mark.parametrize("state", (SignalState.RESOLVED, SignalState.SUPERSEDED))
def test_non_active_thesis_signal_is_not_effective(db_session_factory, production_policies, state):
    change = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    signal = _persist_signal(db_session_factory, change, state=state)
    _assert_aggregation(db_session_factory, production_policies, signal, False)


@pytest.mark.parametrize(
    "mismatch", ("source_type", "missing_source", "asset", "investor", "no_investor")
)
def test_persisted_thesis_signal_requires_real_source_and_matching_identity(
    db_session_factory, production_policies, mismatch
):
    change = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    updates = {}
    if mismatch == "source_type":
        updates["source_type"] = "AttentionOccurrence"
    elif mismatch == "missing_source":
        updates["source_id"] = uuid4()
    elif mismatch == "no_investor":
        updates["investor_id"] = None
    else:
        other = _seed_change(
            db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED
        )
        updates[f"{mismatch}_id"] = getattr(other, f"{mismatch}_id")
    signal = _persist_signal(db_session_factory, change, **updates)
    _assert_aggregation(db_session_factory, production_policies, signal, False)


def _shared_asset_change(factory, policies, asset_id, kind, fact_time):
    with factory() as session:
        asset = session.get(Asset, asset_id)
        investor = Investor(
            name="Another Investor", platform="manual", platform_user_id=str(uuid4())
        )
        session.add(investor)
        session.flush()
        previous = None
        if kind is not ThesisChangeType.NEW_THESIS:
            previous = _add_opinion(
                session,
                investor,
                asset,
                policies[0].active_spec,
                fact_time - timedelta(days=1),
                EventAnalysisStatus.SUCCESS,
            )
        current = _add_opinion(
            session,
            investor,
            asset,
            policies[0].active_spec,
            fact_time,
            EventAnalysisStatus.SUCCESS,
        )
        command = ThesisChangeCreate(
            investor_id=investor.id,
            asset_id=asset_id,
            previous_opinion_id=previous.id if previous else None,
            previous_event_id=previous.event_id if previous else None,
            current_opinion_id=current.id,
            current_event_id=current.event_id,
            effective_time=fact_time,
            change_type=kind,
            confidence=0.9,
            summary="Structured source fixture",
            evidence=("Recorded source evidence",),
            opinion_analysis_version=policies[0].active_analysis_version,
            comparison_version=policies[1].active_analysis_version,
            calculated_at=fact_time + timedelta(days=10),
            input_identity=str(uuid4()),
        )
        change = ThesisChangeRepository(session).add_if_absent(command)
        session.commit()
        return change


def test_mixed_inputs_aggregate_only_effective_count_investors_and_times(
    db_session_factory, production_policies
):
    first = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    second = _shared_asset_change(
        db_session_factory,
        production_policies,
        first.asset_id,
        ThesisChangeType.THESIS_EXTENDED,
        FACT_TIME + timedelta(hours=1),
    )
    valid = [_persist_signal(db_session_factory, source) for source in (first, second)]
    for kind, offset in (
        (ThesisChangeType.NEW_THESIS, -30),
        (ThesisChangeType.THESIS_UNCHANGED, 30),
    ):
        source = _shared_asset_change(
            db_session_factory,
            production_policies,
            first.asset_id,
            kind,
            FACT_TIME + timedelta(days=offset),
        )
        _persist_signal(db_session_factory, source, metadata={"change_type": "THESIS_CHANGED"})
    aggregator = IntelligenceEventAggregator.from_production(db_session_factory)
    plan = aggregator.dry_run(asset_ids=(first.asset_id,))
    assert len(plan.candidates) == 1
    candidate = plan.candidates[0]
    assert candidate.metadata["signal_count"] == 2
    assert set(candidate.metadata["signal_ids"]) == {str(item.id) for item in valid}
    assert set(candidate.metadata["investor_ids"]) == {str(item.investor_id) for item in valid}
    assert candidate.first_observed_at == FACT_TIME
    assert candidate.last_observed_at == FACT_TIME + timedelta(hours=1)
    first_result = aggregator.aggregate(asset_ids=(first.asset_id,))
    second_result = aggregator.aggregate(asset_ids=(first.asset_id,))
    assert first_result.created_evidence_count == 2
    assert second_result.created_evidence_count == 0
    assert second_result.reused_evidence_count == 2
    with db_session_factory() as session:
        assert {item.signal_id for item in session.scalars(select(IntelligenceEventEvidence))} == {
            item.id for item in valid
        }
        assert len(SignalRepository(session).list()) == 4


def test_late_opinion_rechecks_global_predecessor_without_cached_validity(
    db_session_factory, production_policies
):
    change = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    signal = _persist_signal(db_session_factory, change)
    with db_session_factory() as session:
        repository = SignalRepository(session)
        assert [item.id for item in _effective(repository, production_policies)] == [signal.id]
        _add_opinion(
            session,
            session.get(Investor, change.investor_id),
            session.get(Asset, change.asset_id),
            production_policies[0].active_spec,
            FACT_TIME - timedelta(hours=12),
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
        assert _effective(repository, production_policies) == ()
        assert repository.list() == (signal,)
    # No Signal was created for the late Opinion. Its global predecessor impact
    # must still invalidate the scoped asset aggregation of the old Signal.
    assert (
        IntelligenceEventAggregator.from_production(db_session_factory)
        .dry_run(asset_ids=(change.asset_id,))
        .candidates
        == ()
    )


@pytest.mark.parametrize("with_valid", (False, True))
def test_old_event_pollution_is_retained_separately_from_current_candidates(
    db_session_factory, production_policies, with_valid
):
    bad_source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    bad = _persist_signal(db_session_factory, bad_source)
    polluted_first = FACT_TIME - timedelta(days=30)
    polluted_last = FACT_TIME + timedelta(days=30)
    with db_session_factory() as session:
        old_event, _ = IntelligenceEventRepository(session).add_if_absent(
            IntelligenceEventCreate(
                asset_id=bad.asset_id,
                event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
                first_observed_at=polluted_first,
                last_observed_at=polluted_last,
                metadata={"signal_count": 1, "signal_ids": [str(bad.id)]},
            )
        )
        old_link, _ = IntelligenceEventEvidenceRepository(session).add_if_absent(
            IntelligenceEventEvidenceCreate(event_id=old_event.id, signal_id=bad.id)
        )
        session.commit()
    valid = None
    if with_valid:
        source = _shared_asset_change(
            db_session_factory,
            production_policies,
            bad.asset_id,
            ThesisChangeType.THESIS_CHANGED,
            FACT_TIME,
        )
        valid = _persist_signal(db_session_factory, source)
    aggregator = IntelligenceEventAggregator.from_production(db_session_factory)
    plan = aggregator.dry_run()
    assert len(plan.candidates) == int(with_valid)
    if with_valid:
        assert plan.candidates[0].metadata["signal_ids"] == [str(valid.id)]
        assert (
            plan.candidates[0].first_observed_at == plan.candidates[0].last_observed_at == FACT_TIME
        )
    result = aggregator.aggregate()
    assert result.created_evidence_count == int(with_valid)
    with db_session_factory() as session:
        persisted = IntelligenceEventRepository(session).get(old_event.id)
        assert persisted.state is IntelligenceEventState.ACTIVE
        assert persisted.first_observed_at == polluted_first
        assert persisted.last_observed_at == polluted_last
        assert persisted.metadata["signal_ids"] == [str(valid.id if with_valid else bad.id)]
        links = IntelligenceEventEvidenceRepository(session).list_by_event(old_event.id)
        assert {item.signal_id for item in links} == (
            {bad.id, valid.id} if with_valid else {bad.id}
        )
        assert old_link.id in {item.id for item in links}
        assert SignalRepository(session).get(bad.id) == bad


def test_new_attention_keeps_existing_aggregation_behavior_without_policy_dependency(
    db_session_factory, production_policies, monkeypatch
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    active = []
    for kind in (SignalType.NEW_ATTENTION,):
        investors = (
            (source.investor_id, uuid4())
            if kind is SignalType.NEW_ATTENTION
            else (source.investor_id,)
        )
        with db_session_factory() as session:
            if len(investors) == 2:
                session.add(
                    Investor(
                        id=investors[1],
                        name="Other",
                        platform="manual",
                        platform_user_id=str(uuid4()),
                    )
                )
                session.commit()
        for investor_id in investors:
            active.append(
                _persist_signal(
                    db_session_factory,
                    source,
                    signal_type=kind,
                    source_id=uuid4(),
                    source_type="LegacyOtherSource",
                    investor_id=investor_id,
                )
            )
        _persist_signal(
            db_session_factory,
            source,
            signal_type=kind,
            source_id=uuid4(),
            state=SignalState.RESOLVED,
        )
    # NEW_ATTENTION remains outside the new Thesis and cross-source validation.
    monkeypatch.setattr("config.production.get_settings", lambda: None)
    result = IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    assert {item.event_type for item in result.candidates} == {
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
    }
    assert result.created_evidence_count == len(active)
    with db_session_factory() as session:
        assert {item.signal_id for item in session.scalars(select(IntelligenceEventEvidence))} == {
            item.id for item in active
        }


def test_effective_source_reads_are_batched_and_history_remains_available(
    db_engine, db_session_factory, production_policies
):
    statements = []

    def track(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    def read_count():
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            with db_session_factory() as session:
                result = _effective(SignalRepository(session), production_policies)
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        return len(result), len(statements)

    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _persist_signal(db_session_factory, source)
    assert read_count() == (1, 3)
    for _ in range(10):
        source = _seed_change(
            db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED
        )
        _persist_signal(db_session_factory, source)
    assert read_count() == (11, 3)


def test_only_event_uow_switches_to_effective_thesis_reading(
    db_session_factory, production_policies
):
    valid_source = _seed_change(
        db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED
    )
    invalid_source = _seed_change(
        db_session_factory, production_policies, ThesisChangeType.THESIS_UNCHANGED
    )
    valid = _persist_signal(db_session_factory, valid_source)
    invalid = _persist_signal(db_session_factory, invalid_source)
    with SqlAlchemyIntelligenceEventUnitOfWork(db_session_factory) as unit_of_work:
        assert {item.id for item in unit_of_work.signals.list()} == {valid.id}
    with SqlAlchemyIntelligenceFeedUnitOfWork(db_session_factory) as unit_of_work:
        assert {item.id for item in unit_of_work.signals.list()} == {valid.id, invalid.id}
