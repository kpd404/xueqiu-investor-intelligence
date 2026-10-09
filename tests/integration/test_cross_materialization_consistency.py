"""Legacy cross projections rerun through real services in isolated SQLite."""

from datetime import timedelta

import pytest

from contracts import EventAnalysisStatus, FeedState, IntelligenceEventState, SignalState
from contracts.intelligence_feed import feed_display_context
from database.models import (
    Asset,
    CrossInvestorAssetSnapshot,
    IntelligenceEvent,
    IntelligenceEventPriority,
    Investor,
)
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from tests.integration.test_cross_signal_source_chains import CROSS, START, _chain, _legacy
from tests.integration.test_cross_snapshot_input_completeness import _refresh
from tests.integration.test_effective_cross_feed_query import _historical_feed, _http
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME
from tests.integration.test_thesis_change_signals import production_policies as production_policies


def _protected(factory):
    return {
        name: rows
        for name, rows in _snapshot(factory).items()
        if name not in {"intelligence_event_priorities", "intelligence_feed_items"}
    }


def _mixed(factory, policies, kind, state=FeedState.ACTIVE):
    chain = _chain(factory, policies)
    duplicate = _refresh(factory, chain, start=START - timedelta(hours=1))
    signals = [_legacy(factory, version, kind) for version in (chain, duplicate)]
    invalid = _legacy(
        factory,
        _refresh(factory, chain, as_of=duplicate[1].as_of + timedelta(days=1)),
        kind,
        state=SignalState.SUPERSEDED,
    )
    feed = _historical_feed(factory, chain[1].asset_id, [*signals, invalid], kind, state=state)
    # Simulate aggregation already run. Repeating it cannot rewrite historical
    # links or the polluted last time; only Priority/Feed are this task's writes.
    plan = IntelligenceEventAggregator.from_production(factory).dry_run()
    with factory() as session:
        priority = session.get(IntelligenceEventPriority, feed.priority_id)
        priority.priority_level = "HIGH" if kind is CROSS[0] else "LOW"
        event = session.get(IntelligenceEvent, priority.event_id)
        event.metadata_json = plan.candidates[0].metadata
        event.first_observed_at = FACT_TIME
        session.commit()
    return chain, feed


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("state", (FeedState.ACTIVE, FeedState.STALE, FeedState.RESOLVED))
def test_mixed_old_projections_use_same_effective_evidence_as_http(
    db_session_factory, production_policies, feed_api, kind, state
):
    chain, original = _mixed(db_session_factory, production_policies, kind, state)
    before = _snapshot(db_session_factory)
    assert (
        IntelligenceEventAggregator.from_production(db_session_factory)
        .aggregate()
        .created_evidence_count
        == 0
    )
    assert _snapshot(db_session_factory) == before
    priorities = IntelligencePriorityService.from_production(db_session_factory)
    plan = priorities.dry_run()
    assert plan.candidates[0].evidence_count == 1
    assert _snapshot(db_session_factory) == before
    actual = priorities.materialize().priorities[0]
    assert actual.reason.value == "CROSS_INVESTOR_DIRECTION_EVIDENCE"
    assert actual.priority_level.value == ("LOW" if kind is CROSS[0] else "HIGH")
    assert actual.id == original.priority_id and actual.created_at == original.created_at
    feeds = IntelligenceFeedService.from_production(db_session_factory)
    dry_before = _snapshot(db_session_factory)
    candidate = feeds.dry_run().candidates[0]
    assert _snapshot(db_session_factory) == dry_before
    assert candidate.observed_at == FACT_TIME and candidate.context["investor_count"] == 3
    stored = feeds.materialize().items[0]
    query_before = _snapshot(db_session_factory)
    current = _http(feed_api)["items"][0]
    assert feed_display_context(stored.context) == current["context"]
    assert stored.context["_thesis_lifecycle"] == original.context["_thesis_lifecycle"]
    assert stored.state is original.state
    assert stored.title == current["title"] and stored.reason.value == current["reason"]
    assert stored.observed_at.isoformat().replace("+00:00", "Z") == current["observed_at"]
    assert stored.id == original.id and stored.created_at == original.created_at
    assert {i["investor_id"] for i in current["investors"]} == {
        str(s.investor_id) for s in chain[0]
    }
    assert _snapshot(db_session_factory) == query_before
    assert _protected(db_session_factory) == {
        name: rows
        for name, rows in before.items()
        if name not in {"intelligence_event_priorities", "intelligence_feed_items"}
    }
    stable = _snapshot(db_session_factory)
    assert priorities.materialize().reused_count == feeds.materialize().reused_count == 1
    assert _snapshot(db_session_factory) == stable
    assert _http(feed_api, since=(FACT_TIME + timedelta(days=1)).isoformat())["total"] == 0


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("invalid", ("inactive", "late_input", "inactive_event"))
def test_no_effective_or_inactive_event_skips_old_and_new_projections(
    db_session_factory, production_policies, feed_api, kind, invalid
):
    from database.repositories.intelligence_events import IntelligenceEventRepository
    from tests.integration.test_thesis_change_signals import _add_opinion

    chain = _chain(db_session_factory, production_policies)
    signal = _legacy(db_session_factory, chain, kind)
    old = _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, old.priority_id)
        if invalid == "inactive":
            session.get(
                CrossInvestorAssetSnapshot, chain[1].id
            ).opinion_analysis_version = "inactive"
        elif invalid == "late_input":
            source = chain[0][0]
            _add_opinion(
                session,
                session.get(Investor, source.investor_id),
                session.get(Asset, source.asset_id),
                production_policies[0].active_spec,
                FACT_TIME + timedelta(hours=1),
                EventAnalysisStatus.SUCCESS,
            )
        else:
            session.get(
                IntelligenceEvent, priority.event_id
            ).state = IntelligenceEventState.RESOLVED.value
        session.commit()
    before = _snapshot(db_session_factory)
    priority_service = IntelligencePriorityService.from_production(db_session_factory)
    feed_service = IntelligenceFeedService.from_production(db_session_factory)
    assert priority_service.dry_run().candidates == feed_service.dry_run().candidates == ()
    assert priority_service.materialize().priorities == feed_service.materialize().items == ()
    assert _snapshot(db_session_factory) == before
    if invalid != "inactive_event":
        assert _http(feed_api)["total"] == 0
    # A separate target Event without a Priority also gets no zero-evidence row.
    missing = _chain(db_session_factory, production_policies)
    other_signal = _legacy(db_session_factory, missing, kind)
    from contracts import IntelligenceEventCreate, IntelligenceEventEvidenceCreate
    from database.repositories.intelligence_event_evidence import (
        IntelligenceEventEvidenceRepository,
    )
    from tests.integration.test_effective_cross_feed_query import CALC, EVENTS

    with db_session_factory() as session:
        event, _ = IntelligenceEventRepository(session).add_if_absent(
            IntelligenceEventCreate(
                asset_id=missing[1].asset_id,
                event_type=EVENTS[CROSS.index(kind)],
                first_observed_at=CALC,
                last_observed_at=CALC,
            )
        )
        IntelligenceEventEvidenceRepository(session).add_if_absent(
            IntelligenceEventEvidenceCreate(event_id=event.id, signal_id=other_signal.id)
        )
        session.get(CrossInvestorAssetSnapshot, missing[1].id).opinion_analysis_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    assert priority_service.materialize(event_ids=(event.id,)).created_count == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("wrong", ("reason", "level", "count"))
def test_feed_requires_priority_apply_not_just_a_dry_run(
    db_session_factory, production_policies, kind, wrong
):
    _chain_value, old = _mixed(db_session_factory, production_policies, kind)
    service = IntelligencePriorityService.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    assert service.dry_run().candidates[0].evidence_count == 1
    for operation in (
        IntelligenceFeedService.from_production(db_session_factory).dry_run,
        IntelligenceFeedService.from_production(db_session_factory).materialize,
    ):
        with pytest.raises(ValueError, match="Priority.*refreshed"):
            operation()
    assert _snapshot(db_session_factory) == before
    service.materialize()
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, old.priority_id)
        if wrong == "reason":
            priority.reason = "CONSENSUS_STATE_CHANGE"
        elif wrong == "level":
            priority.priority_level = "MEDIUM"
        else:
            priority.evidence_count = 3
        session.commit()
    before = _snapshot(db_session_factory)
    for operation in (
        IntelligenceFeedService.from_production(db_session_factory).dry_run,
        IntelligenceFeedService.from_production(db_session_factory).materialize,
    ):
        with pytest.raises(ValueError, match="Priority.*(refreshed|count)"):
            operation()
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_local_associated_alternative_wins_even_when_global_rep_unassociated(
    db_session_factory, production_policies, feed_api, kind
):
    from signal_engine.repository import SignalRepository

    chain = _chain(db_session_factory, production_policies)
    other = _refresh(db_session_factory, chain, start=START - timedelta(hours=1))
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, other)]
    with db_session_factory() as session:
        representative = SignalRepository(
            session
        ).list_cross_investor_signals_with_valid_references(signal_types={kind})[0]
    linked = next(signal for signal in signals if signal.id != representative.id)
    old = _historical_feed(db_session_factory, chain[1].asset_id, [linked], kind)
    protected = _protected(db_session_factory)
    assert (
        IntelligencePriorityService.from_production(db_session_factory)
        .materialize()
        .priorities[0]
        .evidence_count
        == 1
    )
    result = IntelligenceFeedService.from_production(db_session_factory).materialize().items[0]
    assert result.id == old.id and result.context["investor_count"] == 3
    assert _http(feed_api)["items"][0]["context"] == feed_display_context(result.context)
    assert _protected(db_session_factory) == protected


@pytest.mark.parametrize("kind", CROSS)
def test_lifecycle_accepts_effective_count_after_correct_materialization(
    db_session_factory, production_policies, kind
):
    from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService

    _mixed(db_session_factory, production_policies, kind)
    IntelligencePriorityService.from_production(db_session_factory).materialize()
    IntelligenceFeedService.from_production(db_session_factory).materialize()
    before = _snapshot(db_session_factory)
    lifecycle = FeedLifecycleService.from_production(
        db_session_factory, policy=FeedLifecyclePolicy()
    )
    for operation in (lifecycle.dry_run, lifecycle.apply):
        result = operation(now=FACT_TIME + timedelta(hours=12))
        assert result.updated_count == 0 and result.plan.skipped == ()
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_attention_only_does_not_raise_materialized_voter_count(
    db_session_factory, production_policies, feed_api, kind
):
    from uuid import uuid4

    from contracts import AttentionEvidence, AttentionEvidenceType, AttentionOccurrenceCreate
    from database.repositories.attention_occurrences import AttentionOccurrenceRepository
    from tests.integration.test_thesis_change_signals import _add_opinion

    chain = _chain(db_session_factory, production_policies)
    with db_session_factory() as session:
        investor = Investor(name="Attention only", platform="manual", platform_user_id=uuid4().hex)
        session.add(investor)
        session.flush()
        time = FACT_TIME + timedelta(hours=6)
        opinion = _add_opinion(
            session,
            investor,
            session.get(Asset, chain[1].asset_id),
            production_policies[0].active_spec,
            time,
            EventAnalysisStatus.FAILED,
        )
        AttentionOccurrenceRepository(session).replace_for_event(
            opinion.event_id,
            "attention-occurrence-v1",
            (
                AttentionOccurrenceCreate(
                    investor_id=investor.id,
                    asset_id=chain[1].asset_id,
                    event_id=opinion.event_id,
                    published_time=time,
                    evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
                    evidence=(
                        AttentionEvidence(
                            evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                            matched_by="fixture",
                        ),
                    ),
                    attention_policy_version="attention-occurrence-v1",
                    calculated_at=time,
                ),
            ),
        )
        session.commit()
        observer_id = investor.id
    current = _refresh(db_session_factory, chain)
    assert current[1].attention_investor_count == 4
    signal = _legacy(db_session_factory, current, kind)
    _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    protected = _protected(db_session_factory)
    IntelligencePriorityService.from_production(db_session_factory).materialize()
    materialized = (
        IntelligenceFeedService.from_production(db_session_factory).materialize().items[0]
    )
    assert materialized.context["investor_count"] == 3 and materialized.observed_at == FACT_TIME
    assert _http(feed_api)["items"][0]["context"] == feed_display_context(materialized.context)
    assert _http(feed_api, investor_id=str(observer_id))["total"] == 0
    assert _protected(db_session_factory) == protected


@pytest.mark.parametrize("kind", CROSS)
def test_unassociated_effective_source_does_not_refresh_an_empty_event(
    db_session_factory, production_policies, kind
):
    chain = _chain(db_session_factory, production_policies)
    _legacy(db_session_factory, chain, kind)
    _historical_feed(db_session_factory, chain[1].asset_id, [], kind)
    before = _snapshot(db_session_factory)
    assert (
        IntelligencePriorityService.from_production(db_session_factory).materialize().priorities
        == ()
    )
    assert IntelligenceFeedService.from_production(db_session_factory).materialize().items == ()
    assert _snapshot(db_session_factory) == before


def test_other_event_keeps_generic_priority_reuse_and_scoped_writer_rejects_it(
    db_session_factory, production_policies
):
    from contracts import (
        IntelligenceEventPriorityCreate,
        IntelligencePriorityLevel,
        IntelligencePriorityReason,
        SignalType,
    )
    from database.repositories.intelligence_event_priorities import (
        IntelligenceEventPriorityRepository,
    )
    from signal_engine.service import SignalGenerator

    _chain(db_session_factory, production_policies)
    SignalGenerator.from_production(db_session_factory).generate(
        signal_types=(SignalType.NEW_ATTENTION,)
    )
    event = IntelligenceEventAggregator.from_production(db_session_factory).aggregate().events[0]
    with db_session_factory() as session:
        original, _ = IntelligenceEventPriorityRepository(session).add_if_absent(
            IntelligenceEventPriorityCreate(
                event_id=event.id,
                reason=IntelligencePriorityReason.THESIS_ACCELERATION,
                priority_level=IntelligencePriorityLevel.MEDIUM,
                evidence_count=1,
                created_at=FACT_TIME,
            )
        )
        session.commit()
    current = (
        IntelligencePriorityService.from_production(db_session_factory).materialize().priorities[0]
    )
    assert current.id == original.id and current.reason is original.reason
    assert current.priority_level is original.priority_level and current.evidence_count == 3
    before = _snapshot(db_session_factory)
    with db_session_factory() as session:
        with pytest.raises(ValueError, match="ACTIVE cross-investor Event"):
            IntelligenceEventPriorityRepository(session).add_or_refresh_cross_direction(
                IntelligenceEventPriorityCreate(
                    event_id=event.id,
                    reason=IntelligencePriorityReason.CROSS_INVESTOR_DIRECTION_EVIDENCE,
                    priority_level=IntelligencePriorityLevel.LOW,
                    evidence_count=1,
                    created_at=FACT_TIME,
                )
            )
    assert _snapshot(db_session_factory) == before


def test_materialization_dry_runs_share_scope_reads_not_per_signal_or_event(
    db_engine, db_session_factory, production_policies
):
    from sqlalchemy import event as sqlalchemy_event

    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        signal = _legacy(db_session_factory, chain, kind)
        _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    IntelligencePriorityService.from_production(db_session_factory).materialize()
    statements = []

    def track(_connection, _cursor, statement, *_args):
        statements.append(statement)

    def counts():
        result = []
        for service in (
            IntelligencePriorityService.from_production(db_session_factory),
            IntelligenceFeedService.from_production(db_session_factory),
        ):
            statements.clear()
            sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
            try:
                plan = service.dry_run()
                assert len(plan.candidates) == 2
                assert all(getattr(c, "evidence_count", 1) == 1 for c in plan.candidates)
            finally:
                sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
            assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
            result.append(len(statements))
        return result

    before = _snapshot(db_session_factory)
    assert counts() == [22, 23]
    assert _snapshot(db_session_factory) == before
    for offset in range(1, 6):
        version = _refresh(db_session_factory, chain, start=START - timedelta(hours=offset))
        for kind in CROSS:
            signal = _legacy(db_session_factory, version, kind)
            _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    # Historical fixture additions set stored counts back to 999. Follow the
    # required sequence before measuring Feed planning over the updated scope.
    IntelligencePriorityService.from_production(db_session_factory).materialize()
    before = _snapshot(db_session_factory)
    assert counts() == [67, 68]
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_distinct_real_inputs_remain_separate_without_combining_votes(
    db_session_factory, production_policies, feed_api, kind
):
    chain = _chain(db_session_factory, production_policies)
    other = _refresh(db_session_factory, chain, start=FACT_TIME - timedelta(hours=12))
    assert chain[1].opinion_count != other[1].opinion_count
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, other)]
    _historical_feed(db_session_factory, chain[1].asset_id, signals, kind)
    protected = _protected(db_session_factory)
    priority = (
        IntelligencePriorityService.from_production(db_session_factory).materialize().priorities[0]
    )
    assert priority.evidence_count == 2
    feed = IntelligenceFeedService.from_production(db_session_factory).materialize().items[0]
    assert feed.context["signal_count"] == feed.context["source_count"] == 2
    assert feed.context["investor_count"] == 3
    assert set(feed_display_context(feed.context)) == {
        "signal_count",
        "source_count",
        "source_types",
        "investor_count",
    }
    assert _http(feed_api)["items"][0]["context"] == feed_display_context(feed.context)
    assert _protected(db_session_factory) == protected
