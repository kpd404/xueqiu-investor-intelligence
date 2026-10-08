"""Fixed-clock RawEvent-based reentry through real isolated services."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

import config.production as production_config
from config import Settings
from contracts import (
    AnalysisSpec,
    EventAnalysisStatus,
    FeedState,
    IntelligenceEventType,
    SignalType,
    ThesisChangeType,
)
from database.models import Asset, EventAnalysis, IntelligenceFeedItem, Investor, Opinion
from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository
from database.repositories.thesis_changes import ThesisChangeRepository
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from signal_engine.service import SignalGenerator
from tests.integration import test_thesis_change_feed as feed_fixtures
from tests.integration import test_thesis_change_signals as signal_fixtures
from tests.integration.test_effective_thesis_feed_query import _get, _legacy_feed, _snapshot
from tests.integration.test_effective_thesis_signals import _persist_signal, _shared_asset_change
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion, _seed_change

production_policies = signal_fixtures.production_policies
feed_api = feed_fixtures.feed_api
KEY = "_thesis_lifecycle"


def _pipeline(factory, *, aggregate=True):
    SignalGenerator.from_production(factory).generate(signal_types=(SignalType.THESIS_CHANGE,))
    if aggregate:
        IntelligenceEventAggregator.from_production(factory).aggregate()
    IntelligencePriorityService.from_production(factory).materialize()
    IntelligenceFeedService.from_production(factory).materialize()


def _stored(factory):
    with factory() as session:
        return IntelligenceFeedItemRepository(session).list()[0]


def _lifecycle(factory, clock):
    # Inject the fixed evaluation clock without any real waiting.
    from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

    return FeedLifecycleService(
        lambda: SqlAlchemyIntelligenceFeedUnitOfWork(factory),
        policy=FeedLifecyclePolicy(),
        now_factory=lambda: clock[0],
    )


def _expired(factory, policies):
    source = _seed_change(factory, policies, ThesisChangeType.THESIS_CHANGED)
    _pipeline(factory)
    clock = [FACT_TIME + timedelta(hours=12)]
    lifecycle = _lifecycle(factory, clock)
    lifecycle.apply()
    clock[0] = FACT_TIME + timedelta(days=40)
    lifecycle.apply()
    assert _stored(factory).state is FeedState.STALE
    clock[0] += timedelta(hours=2)
    return source, clock, lifecycle


def _new(factory, policies, source, at, kind=ThesisChangeType.THESIS_CHANGED):
    return _shared_asset_change(factory, policies, source.asset_id, kind, at)


def test_new_recent_raw_fact_reenters_and_materialization_preserves_baseline(
    db_session_factory, production_policies, feed_api
):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    before = _stored(db_session_factory)
    baseline = before.context[KEY]
    new = _new(db_session_factory, production_policies, source, clock[0] - timedelta(hours=1))
    _pipeline(db_session_factory)
    projected = _stored(db_session_factory)
    assert projected.state is FeedState.STALE
    assert projected.context[KEY] == baseline
    snapshot = _snapshot(db_session_factory)
    plan = lifecycle.dry_run()
    assert _snapshot(db_session_factory) == snapshot
    assert len(plan.plan.transitions) == 1
    assert plan.plan.transitions[0].reasons == ("NEW_EFFECTIVE_THESIS_FACT",)
    result = lifecycle.apply(plan=plan.plan)
    assert result.updated_count == 1
    after_snapshot = _snapshot(db_session_factory)
    assert {
        name: rows for name, rows in after_snapshot.items() if name != "intelligence_feed_items"
    } == {name: rows for name, rows in snapshot.items() if name != "intelligence_feed_items"}
    after = _stored(db_session_factory)
    assert after.id == before.id and after.priority_id == before.priority_id
    assert after.created_at == before.created_at and after.state is FeedState.ACTIVE
    assert str(new.current_event_id) in after.context[KEY]["known_raw_event_ids"]
    assert after.context[KEY]["last_transition"]["source_facts"][0]["raw_event_id"] == str(
        new.current_event_id
    )
    current = _get(feed_api, state="ACTIVE", since=(clock[0] - timedelta(days=1)).isoformat())
    assert current["total"] == 1 and KEY not in current["items"][0]["context"]
    stable = _snapshot(db_session_factory)
    assert lifecycle.apply().updated_count == 0
    assert lifecycle.apply(plan=result.plan).updated_count == 0
    assert _snapshot(db_session_factory) == stable
    clock[0] += timedelta(days=40)
    assert lifecycle.apply().updated_count == 1
    assert _stored(db_session_factory).state is FeedState.STALE
    assert lifecycle.apply().updated_count == 0


@pytest.mark.parametrize(
    "case", ("same", "old", "equal_time", "non_material", "unlinked", "future", "interpretation")
)
def test_false_reentry_cases_do_not_reopen(db_session_factory, production_policies, case):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    if case != "same":
        at = clock[0] - timedelta(hours=1)
        if case == "old":
            at = FACT_TIME + timedelta(days=35)
        if case == "equal_time":
            at = FACT_TIME
        if case == "future":
            at = clock[0] + timedelta(days=1)
        if case == "interpretation":
            with db_session_factory() as session:
                original = ThesisChangeRepository(session).get(source.id)
                clone = original.model_copy(
                    update={"input_identity": str(uuid4()), "calculated_at": clock[0]}
                )
                ThesisChangeRepository(session).add_if_absent(clone)
                session.commit()
        else:
            _new(
                db_session_factory,
                production_policies,
                source,
                at,
                ThesisChangeType.THESIS_UNCHANGED
                if case == "non_material"
                else ThesisChangeType.THESIS_CHANGED,
            )
    _pipeline(db_session_factory, aggregate=case != "unlinked")
    result = lifecycle.apply()
    assert result.updated_count == 0
    assert _stored(db_session_factory).state is FeedState.STALE


def test_legacy_stale_initializes_without_activation_then_new_fact_can_reenter(
    db_session_factory, production_policies
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _pipeline(db_session_factory)
    with db_session_factory() as session:
        session.scalar(select(IntelligenceFeedItem)).state = "STALE"
        session.commit()
    clock = [FACT_TIME + timedelta(hours=12)]
    lifecycle = _lifecycle(db_session_factory, clock)
    snapshot = _snapshot(db_session_factory)
    plan = lifecycle.dry_run()
    assert _snapshot(db_session_factory) == snapshot
    assert plan.plan.transitions == ()
    assert lifecycle.apply().updated_count == 0
    assert KEY in _stored(db_session_factory).context
    assert _stored(db_session_factory).state is FeedState.STALE
    clock[0] += timedelta(hours=2)
    _new(db_session_factory, production_policies, source, clock[0] - timedelta(minutes=1))
    _pipeline(db_session_factory)
    assert lifecycle.apply().updated_count == 1


def test_preexisting_raw_fact_new_interpretation_is_not_new_fact(
    db_session_factory, production_policies
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    old_interpretation = _new(
        db_session_factory,
        production_policies,
        source,
        FACT_TIME + timedelta(days=35),
        ThesisChangeType.THESIS_UNCHANGED,
    )
    _pipeline(db_session_factory)
    clock = [FACT_TIME + timedelta(hours=12)]
    lifecycle = _lifecycle(db_session_factory, clock)
    lifecycle.apply()
    clock[0] = FACT_TIME + timedelta(days=40)
    lifecycle.apply()
    with db_session_factory() as session:
        command = old_interpretation.model_copy(
            update={"change_type": ThesisChangeType.THESIS_CHANGED, "input_identity": str(uuid4())}
        )
        ThesisChangeRepository(session).add_if_absent(command)
        session.commit()
    _pipeline(db_session_factory)
    assert lifecycle.apply().updated_count == 0
    assert _stored(db_session_factory).state is FeedState.STALE


@pytest.mark.parametrize("invalidated", ("source", "window", "baseline", "projection"))
def test_external_plan_is_rechecked_before_reentry(
    db_session_factory, production_policies, invalidated
):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    added = _new(db_session_factory, production_policies, source, clock[0] - timedelta(hours=1))
    _pipeline(db_session_factory)
    plan = lifecycle.dry_run().plan
    assert plan.transitions
    if invalidated == "window":
        clock[0] += timedelta(days=40)
    elif invalidated == "source":
        with db_session_factory() as session:
            _add_opinion(
                session,
                session.get(Investor, added.investor_id),
                session.get(Asset, added.asset_id),
                production_policies[0].active_spec,
                added.effective_time - timedelta(hours=12),
                EventAnalysisStatus.SUCCESS,
            )
            session.commit()
        _pipeline(db_session_factory)
    elif invalidated == "projection":
        with db_session_factory() as session:
            session.scalar(select(IntelligenceFeedItem)).context = {"signal_count": 999}
            session.commit()
    else:
        # A different evaluation consumes the facts as a compatibility checkpoint.
        with db_session_factory() as session:
            row = session.scalar(select(IntelligenceFeedItem))
            context = dict(row.context)
            context.pop(KEY)
            row.context = context
            session.commit()
        lifecycle.apply()
    before = _snapshot(db_session_factory)
    with pytest.raises(ValueError):
        lifecycle.apply(plan=plan)
    assert _snapshot(db_session_factory) == before
    assert _stored(db_session_factory).state is FeedState.STALE


def test_state_and_baseline_rollback_atomically_on_failure(
    db_session_factory, production_policies, monkeypatch
):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    _new(db_session_factory, production_policies, source, clock[0] - timedelta(hours=1))
    _pipeline(db_session_factory)
    original = IntelligenceFeedItemRepository.update_thesis_lifecycle

    def fail_after_write(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("simulated failure after flush")

    monkeypatch.setattr(IntelligenceFeedItemRepository, "update_thesis_lifecycle", fail_after_write)
    before = _snapshot(db_session_factory)
    with pytest.raises(RuntimeError):
        lifecycle.apply()
    assert _snapshot(db_session_factory) == before


def test_resolved_is_not_reopened(db_session_factory, production_policies):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    with db_session_factory() as session:
        session.scalar(select(IntelligenceFeedItem)).state = "RESOLVED"
        session.commit()
    _new(db_session_factory, production_policies, source, clock[0] - timedelta(hours=1))
    _pipeline(db_session_factory)
    before = _snapshot(db_session_factory)
    assert lifecycle.apply().updated_count == 0
    assert _snapshot(db_session_factory) == before


def test_future_seen_fact_does_not_reenter_later_just_because_clock_advances(
    db_session_factory, production_policies
):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    _new(db_session_factory, production_policies, source, clock[0] + timedelta(days=1))
    _pipeline(db_session_factory)
    assert lifecycle.apply().updated_count == 0
    clock[0] += timedelta(days=2)
    assert lifecycle.apply().updated_count == 0
    assert _stored(db_session_factory).state is FeedState.STALE


def test_late_predecessor_repair_uses_old_current_raw_identity(
    db_session_factory, production_policies
):
    anchor = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    old = _new(
        db_session_factory,
        production_policies,
        anchor,
        FACT_TIME + timedelta(days=35),
        ThesisChangeType.THESIS_UNCHANGED,
    )
    _pipeline(db_session_factory)
    clock = [FACT_TIME + timedelta(hours=12)]
    lifecycle = _lifecycle(db_session_factory, clock)
    lifecycle.apply()
    clock[0] = FACT_TIME + timedelta(days=40)
    lifecycle.apply()
    with db_session_factory() as session:
        late = _add_opinion(
            session,
            session.get(Investor, old.investor_id),
            session.get(Asset, old.asset_id),
            production_policies[0].active_spec,
            old.effective_time - timedelta(hours=12),
            EventAnalysisStatus.SUCCESS,
        )
        command = old.model_copy(
            update={
                "previous_opinion_id": late.id,
                "previous_event_id": late.event_id,
                "change_type": ThesisChangeType.THESIS_CHANGED,
                "input_identity": str(uuid4()),
            }
        )
        ThesisChangeRepository(session).add_if_absent(command)
        session.commit()
    _pipeline(db_session_factory)
    assert lifecycle.apply().updated_count == 0


def test_policy_switch_and_restoration_cannot_reset_fact_progress(
    db_session_factory, production_policies, monkeypatch
):
    anchor = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    old = _new(
        db_session_factory,
        production_policies,
        anchor,
        FACT_TIME + timedelta(days=35),
        ThesisChangeType.THESIS_UNCHANGED,
    )
    _pipeline(db_session_factory)
    clock = [FACT_TIME + timedelta(hours=12)]
    lifecycle = _lifecycle(db_session_factory, clock)
    lifecycle.apply()
    clock[0] = FACT_TIME + timedelta(days=40)
    lifecycle.apply()
    baseline = _stored(db_session_factory).context[KEY]
    original_settings = production_config.get_settings
    opinion_spec = production_policies[0].active_spec.model_copy(
        update={"model_version": "test-reinterpretation"}
    )
    opinion_spec = AnalysisSpec.for_provider(
        **{
            key: getattr(opinion_spec, key)
            for key in (
                "provider_id",
                "model_version",
                "prompt_version",
                "schema_version",
                "analysis_policy_version",
            )
        }
    )
    comparison_spec = production_policies[1].active_spec
    comparison_spec = AnalysisSpec.for_provider(
        provider_id=comparison_spec.provider_id,
        model_version="test-reinterpretation",
        prompt_version=comparison_spec.prompt_version,
        schema_version=comparison_spec.schema_version,
        analysis_policy_version=comparison_spec.analysis_policy_version,
    )
    settings = Settings(
        _env_file=None,
        llm_provider_id=opinion_spec.provider_id,
        llm_model=opinion_spec.model_version,
        llm_api_key="",
        production_opinion_analysis_version=opinion_spec.analysis_version,
        production_thesis_comparison_version=comparison_spec.analysis_version,
    )
    with db_session_factory() as session:
        new_opinions = []
        for identity in (old.previous_opinion_id, old.current_opinion_id):
            original = session.get(Opinion, identity)
            analysis = EventAnalysis(
                event_id=original.event_id,
                analysis_version=opinion_spec.analysis_version,
                model_version=opinion_spec.model_version,
                prompt_version=opinion_spec.prompt_version,
                schema_version=opinion_spec.schema_version,
                status=EventAnalysisStatus.SUCCESS,
                investment_related=True,
                confidence=0.9,
                structured_output={},
                generated_time=clock[0],
                calculated_at=clock[0],
            )
            session.add(analysis)
            session.flush()
            opinion = Opinion(
                event_id=original.event_id,
                analysis_id=analysis.id,
                investor_id=original.investor_id,
                asset_id=original.asset_id,
                direction=original.direction,
                strength=original.strength,
                confidence=original.confidence,
                thesis=original.thesis,
                catalysts=[],
                risks=[],
                model_version=opinion_spec.model_version,
                generated_time=clock[0],
            )
            session.add(opinion)
            session.flush()
            new_opinions.append(opinion)
        command = old.model_copy(
            update={
                "previous_opinion_id": new_opinions[0].id,
                "current_opinion_id": new_opinions[1].id,
                "opinion_analysis_version": opinion_spec.analysis_version,
                "comparison_version": comparison_spec.analysis_version,
                "change_type": ThesisChangeType.THESIS_CHANGED,
                "input_identity": str(uuid4()),
            }
        )
        ThesisChangeRepository(session).add_if_absent(command)
        session.commit()
    monkeypatch.setattr(production_config, "get_settings", lambda: settings)
    _pipeline(db_session_factory)
    assert lifecycle.apply().updated_count == 0
    changed = _stored(db_session_factory).context[KEY]
    assert changed["high_watermark"] >= baseline["high_watermark"]
    assert set(baseline["known_raw_event_ids"]) <= set(changed["known_raw_event_ids"])
    assert baseline["consumed_facts"].items() <= changed["consumed_facts"].items()
    monkeypatch.setattr(production_config, "get_settings", original_settings)
    _pipeline(db_session_factory)
    assert lifecycle.apply().updated_count == 0
    assert _stored(db_session_factory).context[KEY]["high_watermark"] == changed["high_watermark"]


def test_all_invalid_sources_keep_skip_and_baseline_unchanged(
    db_session_factory, production_policies
):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    with db_session_factory() as session:
        _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            FACT_TIME - timedelta(hours=12),
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    _pipeline(db_session_factory)
    before = _snapshot(db_session_factory)
    result = lifecycle.apply()
    assert result.updated_count == result.baseline_updated_count == 0
    assert result.plan.skipped[0].reason == "NO_EFFECTIVE_THESIS_EVIDENCE"
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize(
    "kind",
    (
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        IntelligenceEventType.CONSENSUS_STATE_CHANGE,
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
    ),
)
def test_other_stale_types_do_not_reenter(db_session_factory, production_policies, kind):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    signal = _persist_signal(db_session_factory, source)
    old = _legacy_feed(
        db_session_factory, source.asset_id, (signal,), state=FeedState.STALE, event_type=kind
    )
    from database.models import IntelligenceEventPriority

    with db_session_factory() as session:
        session.get(IntelligenceEventPriority, old.priority_id).evidence_count = 1
        session.commit()
    before = _snapshot(db_session_factory)
    assert _lifecycle(db_session_factory, [old.observed_at]).apply().updated_count == 0
    assert _snapshot(db_session_factory) == before


def test_forged_plan_without_fact_checkpoint_is_rejected(db_session_factory, production_policies):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    from intelligence.feed.lifecycle import FeedLifecyclePlan, FeedLifecycleTransition

    item = _stored(db_session_factory)
    plan = FeedLifecyclePlan(
        clock[0],
        {},
        {},
        (
            FeedLifecycleTransition(
                item.id, FeedState.STALE, FeedState.ACTIVE, ("NEW_EFFECTIVE_THESIS_FACT",)
            ),
        ),
    )
    before = _snapshot(db_session_factory)
    with pytest.raises(ValueError, match="checkpoint"):
        lifecycle.apply(plan=plan)
    assert _snapshot(db_session_factory) == before


def test_invalid_baseline_is_not_reset(db_session_factory, production_policies):
    _, _, lifecycle = _expired(db_session_factory, production_policies)
    with db_session_factory() as session:
        row = session.scalar(select(IntelligenceFeedItem))
        row.context = {**row.context, KEY: {"version": 999}}
        session.commit()
    before = _snapshot(db_session_factory)
    with pytest.raises(ValueError, match="Invalid Thesis"):
        lifecycle.apply()
    assert _snapshot(db_session_factory) == before


def test_inconsistent_derived_time_is_not_sufficient_for_reentry(
    db_session_factory, production_policies
):
    source, clock, lifecycle = _expired(db_session_factory, production_policies)
    new = _new(db_session_factory, production_policies, source, clock[0] - timedelta(hours=1))
    with db_session_factory() as session:
        command = new.model_copy(
            update={
                "effective_time": new.effective_time + timedelta(minutes=5),
                "input_identity": str(uuid4()),
            }
        )
        ThesisChangeRepository(session).add_if_absent(command)
        session.commit()
    _pipeline(db_session_factory)
    assert lifecycle.apply().updated_count == 0
    assert _stored(db_session_factory).state is FeedState.STALE
