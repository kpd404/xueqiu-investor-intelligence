"""Real cross materialization before lifecycle; fixed clocks, historical links."""

from datetime import timedelta

import pytest

from contracts import EventAnalysisStatus, FeedState, IntelligenceEventState
from database.models import (
    CrossInvestorAssetSnapshot,
    IntelligenceEvent,
    IntelligenceEventPriority,
    IntelligenceFeedItem,
)
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from tests.integration.test_cross_materialization_consistency import _mixed
from tests.integration.test_cross_signal_source_chains import CROSS, _chain, _legacy
from tests.integration.test_effective_cross_feed_query import _historical_feed, _http
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME
from tests.integration.test_thesis_change_signals import production_policies as production_policies


def _materialize(factory):
    IntelligencePriorityService.from_production(factory).materialize()
    return IntelligenceFeedService.from_production(factory).materialize()


def _service(factory, now):
    return FeedLifecycleService.from_production(
        factory, policy=FeedLifecyclePolicy(), now_factory=lambda: now
    )


@pytest.mark.parametrize("kind", CROSS)
def test_three_old_links_one_effective_group_activates_after_real_materialization(
    db_session_factory, production_policies, feed_api, kind
):
    chain, old = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    feed = _materialize(db_session_factory).items[0]
    now = FACT_TIME + timedelta(hours=12)
    service = _service(db_session_factory, now)
    before = _snapshot(db_session_factory)
    plan = service.dry_run(now=now).plan
    assert len(plan.transitions) == 1
    assert plan.transitions[0].reasons == ("WITHIN_ACTIVATION_WINDOW",)
    assert _snapshot(db_session_factory) == before
    actual = service.apply(now=now)
    assert actual.updated_count == 1 and actual.baseline_updated_count == 0
    item = _http(feed_api, state="ACTIVE", since=(now - timedelta(days=1)).isoformat())["items"][0]
    assert item["id"] == str(old.id)
    assert item["context"]["signal_count"] == 1 and item["context"]["investor_count"] == 3
    assert item["observed_at"] == FACT_TIME.isoformat().replace("+00:00", "Z")
    assert item["title"] == feed.title and item["reason"] == feed.reason.value
    after = _snapshot(db_session_factory)
    assert {k: v for k, v in before.items() if k != "intelligence_feed_items"} == {
        k: v for k, v in after.items() if k != "intelligence_feed_items"
    }
    assert service.apply(now=now).updated_count == 0
    assert _snapshot(db_session_factory) == after
    # Only state changes: all other persisted Feed fields, including the private
    # region, are byte-for-byte equal to the pre-Lifecycle snapshot.
    old_rows = before["intelligence_feed_items"]
    new_rows = after["intelligence_feed_items"]
    assert [{k: v for k, v in row.items() if k != "state"} for row in old_rows] == [
        {k: v for k, v in row.items() if k != "state"} for row in new_rows
    ]


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("offset", (60, -1))
def test_old_or_future_facts_do_not_activate_even_with_compatibility_type(
    db_session_factory, production_policies, kind, offset
):
    chain = _chain(db_session_factory, production_policies)
    signal = _legacy(db_session_factory, chain, kind)
    _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind, state=FeedState.NEW)
    _materialize(db_session_factory)
    now = FACT_TIME + timedelta(days=offset)
    before = _snapshot(db_session_factory)
    assert _service(db_session_factory, now).apply(now=now).updated_count == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("state", (FeedState.ACTIVE, FeedState.STALE, FeedState.RESOLVED))
def test_old_active_expires_but_no_cross_reentry_or_reopen(
    db_session_factory, production_policies, feed_api, kind, state
):
    _mixed(db_session_factory, production_policies, kind, state)
    _materialize(db_session_factory)
    now = FACT_TIME + timedelta(days=60)
    service = _service(db_session_factory, now)
    before = _snapshot(db_session_factory)
    result = service.apply(now=now)
    assert result.updated_count == int(state is FeedState.ACTIVE)
    assert result.baseline_updated_count == 0
    if state is FeedState.ACTIVE:
        assert result.plan.transitions[0].to_state is FeedState.STALE
        assert result.plan.transitions[0].reasons == ("STALE_WINDOW",)
    else:
        assert _snapshot(db_session_factory) == before
    assert (
        _http(feed_api, state="ACTIVE", since=(now - timedelta(days=1)).isoformat())["total"] == 0
    )
    assert service.apply(now=now).updated_count == 0


@pytest.mark.parametrize("kind", CROSS)
def test_all_effective_evidence_lost_skips_and_does_not_block_good_item(
    db_session_factory, production_policies, feed_api, kind
):
    bad, old = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    good, fresh = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _materialize(db_session_factory)
    with db_session_factory() as session:
        session.get(CrossInvestorAssetSnapshot, bad[1].id).opinion_analysis_version = "inactive"
        # Both equivalent aliases must lose effectiveness, not just one source.
        from sqlalchemy import select

        for snapshot in session.scalars(
            select(CrossInvestorAssetSnapshot).where(
                CrossInvestorAssetSnapshot.asset_id == bad[1].asset_id
            )
        ):
            snapshot.opinion_analysis_version = "inactive"
        session.commit()
    now = FACT_TIME + timedelta(hours=12)
    before = _snapshot(db_session_factory)
    result = _service(db_session_factory, now).apply(now=now)
    assert result.updated_count == 1
    assert [(s.feed_item_id, s.reason) for s in result.plan.skipped] == [
        (old.id, "NO_EFFECTIVE_CROSS_DIRECTION_EVIDENCE")
    ]
    assert {t.feed_item_id for t in result.plan.transitions} == {fresh.id}
    with db_session_factory() as session:
        assert session.get(IntelligenceFeedItem, old.id).state == "NEW"
    assert _http(feed_api, state="ACTIVE")["total"] == 1
    after = _snapshot(db_session_factory)
    assert {k: v for k, v in before.items() if k != "intelligence_feed_items"} == {
        k: v for k, v in after.items() if k != "intelligence_feed_items"
    }


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize(
    "field",
    (
        "priority_reason",
        "priority_level",
        "priority_count",
        "feed_asset",
        "feed_type",
        "reason",
        "title",
        "context",
        "observed_at",
    ),
)
def test_lifecycle_rejects_unrefreshed_projection_without_repairing_it(
    db_session_factory, production_policies, kind, field
):
    _chain_value, old = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _materialize(db_session_factory)
    with db_session_factory() as session:
        feed = session.get(IntelligenceFeedItem, old.id)
        priority = session.get(IntelligenceEventPriority, old.priority_id)
        if field == "priority_reason":
            priority.reason = "CONSENSUS_STATE_CHANGE"
        elif field == "priority_level":
            priority.priority_level = "MEDIUM"
        elif field == "priority_count":
            priority.evidence_count = 3
        elif field == "feed_asset":
            other = _chain(db_session_factory, production_policies)
            feed.asset_id = other[1].asset_id
        elif field == "feed_type":
            feed.event_type = "ASSET_ACTIVITY_SPIKE"
        elif field == "observed_at":
            feed.observed_at = FACT_TIME + timedelta(days=90)
        elif field == "context":
            feed.context = {"signal_count": 3}
        elif field == "reason":
            feed.reason = "CONSENSUS_STATE_CHANGE"
        else:
            feed.title = "Obsolete title"
        session.commit()
    now = FACT_TIME + timedelta(hours=12)
    before = _snapshot(db_session_factory)
    service = _service(db_session_factory, now)
    for operation in (service.dry_run, service.apply):
        with pytest.raises(ValueError, match="(Priority|FeedItem|Cross Feed)"):
            operation(now=now)
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_non_active_event_does_not_activate_recent_new_feed(
    db_session_factory, production_policies, kind
):
    _chain_value, old = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _materialize(db_session_factory)
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, old.priority_id)
        session.get(
            IntelligenceEvent, priority.event_id
        ).state = IntelligenceEventState.RESOLVED.value
        session.commit()
    now = FACT_TIME + timedelta(hours=12)
    before = _snapshot(db_session_factory)
    assert _service(db_session_factory, now).apply(now=now).updated_count == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("changed", ("sources", "clock", "projection"))
def test_external_cross_plan_is_not_authority_for_evidence_or_time(
    db_session_factory, production_policies, kind, changed
):
    chain, old = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _materialize(db_session_factory)
    clock = [FACT_TIME + timedelta(hours=12)]
    service = FeedLifecycleService.from_production(
        db_session_factory, policy=FeedLifecyclePolicy(), now_factory=lambda: clock[0]
    )
    plan = service.dry_run(now=clock[0]).plan
    assert len(plan.transitions) == 1
    if changed == "clock":
        clock[0] += timedelta(days=60)
    elif changed == "projection":
        with db_session_factory() as session:
            session.get(IntelligenceFeedItem, old.id).event_type = "ASSET_ACTIVITY_SPIKE"
            session.commit()
    else:
        from sqlalchemy import select

        with db_session_factory() as session:
            for snapshot in session.scalars(
                select(CrossInvestorAssetSnapshot).where(
                    CrossInvestorAssetSnapshot.asset_id == chain[1].asset_id
                )
            ):
                snapshot.opinion_analysis_version = "inactive"
            session.commit()
    before = _snapshot(db_session_factory)
    with pytest.raises(ValueError, match="(Cross lifecycle plan no longer|FeedItem)"):
        service.apply(plan=plan)
    assert _snapshot(db_session_factory) == before


def test_thesis_quantity_failure_remains_independent_of_cross_fix(
    db_session_factory, production_policies
):
    from tests.integration.test_thesis_materialization_consistency import _history

    _history(db_session_factory, production_policies, state=FeedState.NEW)
    # Same error category as the reported startup failure, deliberately without
    # refreshing this Thesis Priority. This is not a production-root-cause audit.
    before = _snapshot(db_session_factory)
    service = _service(db_session_factory, FACT_TIME + timedelta(hours=12))
    for operation in (service.dry_run, service.apply):
        with pytest.raises(
            ValueError, match="Priority evidence count does not match effective Thesis evidence"
        ):
            operation(now=FACT_TIME + timedelta(hours=12))
    assert _snapshot(db_session_factory) == before


def test_existing_thesis_checkpoint_survives_cross_state_updates(
    db_session_factory, production_policies
):
    from tests.integration.test_thesis_stale_reentry import _expired, _stored

    _source, clock, original_lifecycle = _expired(db_session_factory, production_policies)
    from tests.integration.test_effective_cross_feed_query import _later_window

    cross = _later_window(db_session_factory, production_policies, 40.5)
    signal = _legacy(db_session_factory, cross, CROSS[0])
    _historical_feed(db_session_factory, cross[1].asset_id, [signal], CROSS[0], state=FeedState.NEW)
    _materialize(db_session_factory)
    # Existing Thesis semantics absorb newly known RawEvent inventory. At this
    # clock the cross fact is still future, so no cross state changes yet.
    original_lifecycle.apply()
    thesis_before = _stored(db_session_factory)
    assert "_thesis_lifecycle" in thesis_before.context
    now = FACT_TIME + timedelta(days=41)
    result = _service(db_session_factory, now).apply(now=now)
    assert result.updated_count == 1 and result.baseline_updated_count == 0
    with db_session_factory() as session:
        thesis = session.get(IntelligenceFeedItem, thesis_before.id)
        assert thesis.state == thesis_before.state.value
        assert thesis.context["_thesis_lifecycle"] == thesis_before.context["_thesis_lifecycle"]


def test_cross_lifecycle_source_queries_share_complete_scopes(
    db_engine, db_session_factory, production_policies
):
    from sqlalchemy import event as sqlalchemy_event

    from tests.integration.test_cross_signal_source_chains import START
    from tests.integration.test_cross_snapshot_input_completeness import _refresh

    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        signal = _legacy(db_session_factory, chain, kind)
        _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind, state=FeedState.NEW)
    _materialize(db_session_factory)
    now = FACT_TIME + timedelta(hours=12)
    service = _service(db_session_factory, now)
    statements = []

    def track(_connection, _cursor, statement, *_args):
        statements.append(statement)

    def count():
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            result = service.dry_run(now=now)
            assert len(result.plan.transitions) == 2
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
        return len(statements)

    before = _snapshot(db_session_factory)
    assert count() == 23
    assert _snapshot(db_session_factory) == before
    for offset in range(1, 6):
        version = _refresh(db_session_factory, chain, start=START - timedelta(hours=offset))
        for kind in CROSS:
            signal = _legacy(db_session_factory, version, kind)
            _historical_feed(
                db_session_factory, chain[1].asset_id, [signal], kind, state=FeedState.NEW
            )
    _materialize(db_session_factory)
    before = _snapshot(db_session_factory)
    assert count() == 68
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_invalid_recent_fact_cannot_prevent_old_active_expiry(
    db_session_factory, production_policies, feed_api, kind
):
    from database.models import Asset, Investor
    from tests.integration.test_cross_snapshot_input_completeness import _attention, _refresh
    from tests.integration.test_thesis_change_signals import _add_opinion

    chain, _old = _mixed(db_session_factory, production_policies, kind, FeedState.ACTIVE)
    source = chain[0][0]
    recent_time = FACT_TIME + timedelta(days=59)
    with db_session_factory() as session:
        opinion = _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            recent_time,
            EventAnalysisStatus.SUCCESS,
        )
        _attention(session, opinion, recent_time)
        session.commit()
    newer = _refresh(db_session_factory, chain, end=recent_time + timedelta(days=1))
    linked = _legacy(db_session_factory, newer, kind)
    _historical_feed(db_session_factory, chain[1].asset_id, [linked], kind)
    with db_session_factory() as session:
        session.get(
            CrossInvestorAssetSnapshot, newer[1].id
        ).cross_investor_policy_version = "inactive"
        session.commit()
    _materialize(db_session_factory)
    now = FACT_TIME + timedelta(days=60)
    before = _snapshot(db_session_factory)
    result = _service(db_session_factory, now).apply(now=now)
    assert result.updated_count == 1
    assert result.plan.transitions[0].to_state is FeedState.STALE
    assert (
        _http(feed_api, state="ACTIVE", since=(now - timedelta(days=1)).isoformat())["total"] == 0
    )
    after = _snapshot(db_session_factory)
    assert {k: v for k, v in before.items() if k != "intelligence_feed_items"} == {
        k: v for k, v in after.items() if k != "intelligence_feed_items"
    }
