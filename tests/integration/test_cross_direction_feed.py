"""Real direction evidence through Signal/Event/Priority/Feed/Lifecycle/HTTP."""

from datetime import timedelta

import pytest

from contracts import (
    IntelligenceEventPriorityCreate,
    IntelligenceEventType,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    OpinionDirection,
)
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from signal_engine.service import SignalGenerator
from tests.integration.test_cross_signal_source_chains import CROSS, _chain
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME
from tests.integration.test_thesis_change_signals import production_policies as production_policies

REASON = "CROSS_INVESTOR_DIRECTION_EVIDENCE"
TITLE = "Cross-investor direction evidence was observed"
NOW = FACT_TIME + timedelta(hours=12)


@pytest.mark.parametrize(
    "directions,state",
    (
        ((OpinionDirection.BULLISH,) * 3, "CONSENSUS_BULLISH"),
        (
            (OpinionDirection.BULLISH, OpinionDirection.BULLISH, OpinionDirection.BEARISH),
            "DIVERGENT",
        ),
    ),
)
def test_current_direction_state_is_not_a_temporal_change(
    db_session_factory, production_policies, feed_api, directions, state
):
    chain = _chain(db_session_factory, production_policies, directions=directions)
    assert chain[3].consensus_state.value == state
    signals = SignalGenerator.from_production(db_session_factory).generate(signal_types=CROSS)
    events = IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    priorities = IntelligencePriorityService.from_production(db_session_factory).materialize()
    feed = IntelligenceFeedService.from_production(db_session_factory).materialize()
    FeedLifecycleService.from_production(db_session_factory, policy=FeedLifecyclePolicy()).apply(
        now=NOW
    )
    assert (
        signals.created_count
        == events.created_event_count
        == priorities.created_count
        == feed.created_count
        == 2
    )
    event_by_id = {event.id: event for event in events.events}
    assert {priority.reason.value for priority in priorities.priorities} == {REASON}
    assert {
        priority.priority_level
        for priority in priorities.priorities
        if event_by_id[priority.event_id].event_type is IntelligenceEventType.CONSENSUS_STATE_CHANGE
    } == {IntelligencePriorityLevel.HIGH}
    assert {
        priority.priority_level
        for priority in priorities.priorities
        if event_by_id[priority.event_id].event_type
        is IntelligenceEventType.CROSS_INVESTOR_DISCOVERY
    } == {IntelligencePriorityLevel.LOW}
    assert {item.title for item in feed.items} == {TITLE}
    assert {item.observed_at for item in feed.items} == {FACT_TIME}
    before = _snapshot(db_session_factory)
    response = feed_api.get(
        "/api/intelligence/feed",
        params={"state": "ACTIVE", "since": (NOW - timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["reason"] for item in body["items"]} == {REASON}
    assert {item["title"] for item in body["items"]} == {TITLE}
    assert {item["observed_at"] for item in body["items"]} == {
        FACT_TIME.isoformat().replace("+00:00", "Z")
    }
    assert {item["event_type"] for item in body["items"]} == {
        "CROSS_INVESTOR_DISCOVERY",
        "CONSENSUS_STATE_CHANGE",
    }
    assert all(
        "change" not in item["title"].lower() and "formed" not in item["title"].lower()
        for item in body["items"]
    )
    assert _snapshot(db_session_factory) == before
    assert (
        SignalGenerator.from_production(db_session_factory)
        .generate(signal_types=CROSS)
        .created_count
        == 0
    )
    assert (
        IntelligenceEventAggregator.from_production(db_session_factory)
        .aggregate()
        .created_evidence_count
        == 0
    )
    again = IntelligencePriorityService.from_production(db_session_factory).materialize()
    assert again.created_count == 0 and again.reused_count == 2
    assert {p.id for p in again.priorities} == {p.id for p in priorities.priorities}
    repeated = IntelligenceFeedService.from_production(db_session_factory).materialize()
    assert repeated.created_count == 0 and repeated.reused_count == 2
    assert {i.id for i in repeated.items} == {i.id for i in feed.items}
    assert {i.created_at for i in repeated.items} == {i.created_at for i in feed.items}
    assert {i.title for i in repeated.items} == {TITLE}


@pytest.mark.parametrize("invalid_source", (False, True))
def test_old_priority_fields_refresh_only_on_explicit_materialization(
    db_session_factory, production_policies, feed_api, invalid_source
):
    from database.models import CrossInvestorAssetSnapshot, IntelligenceFeedItem
    from database.repositories.intelligence_event_priorities import (
        IntelligenceEventPriorityRepository,
    )

    chain = _chain(db_session_factory, production_policies)
    SignalGenerator.from_production(db_session_factory).generate(signal_types=CROSS)
    events = IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    old = {}
    with db_session_factory() as session:
        for event in events.events:
            consensus = event.event_type is IntelligenceEventType.CONSENSUS_STATE_CHANGE
            reason = (
                IntelligencePriorityReason.CONSENSUS_STATE_CHANGE
                if consensus
                else IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY
            )
            priority, _ = IntelligenceEventPriorityRepository(session).add_if_absent(
                IntelligenceEventPriorityCreate(
                    event_id=event.id,
                    priority_level=IntelligencePriorityLevel.HIGH
                    if consensus
                    else IntelligencePriorityLevel.LOW,
                    reason=reason,
                    evidence_count=99,
                    created_at=FACT_TIME - timedelta(days=1),
                )
            )
            old[priority.id] = priority
        session.commit()
    service = IntelligencePriorityService.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    plan = service.dry_run()
    assert {p.reason.value for p in plan.candidates} == {REASON}
    assert {p.reason for p in plan.priorities} == {p.reason for p in old.values()}
    assert _snapshot(db_session_factory) == before
    actual = service.materialize()
    assert actual.created_count == 0 and actual.reused_count == 2
    for priority in actual.priorities:
        assert priority.id in old
        assert priority.reason.value == REASON
        assert priority.created_at == old[priority.id].created_at
        assert priority.evidence_count == 1
    feeds = IntelligenceFeedService.from_production(db_session_factory).materialize()
    assert all(item.title == TITLE for item in feeds.items)
    FeedLifecycleService.from_production(db_session_factory, policy=FeedLifecyclePolicy()).apply(
        now=NOW
    )
    with db_session_factory() as session:
        for item in feeds.items:
            # Simulate a pre-fix stored display title: reads label it, not rewrite it.
            session.get(
                IntelligenceFeedItem, item.id
            ).title = "A consensus state change was observed"
        if invalid_source:
            session.get(
                CrossInvestorAssetSnapshot, chain[1].id
            ).opinion_analysis_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    response = feed_api.get("/api/intelligence/feed", params={"state": "ACTIVE"})
    assert response.status_code == 200
    assert response.json()["total"] == (0 if invalid_source else 2)
    for item in response.json()["items"]:
        assert item["reason"] == REASON
        assert item["title"] == TITLE
    assert _snapshot(db_session_factory) == before
    if invalid_source:
        from signal_engine.repository import SignalRepository

        with db_session_factory() as session:
            assert (
                SignalRepository(session).list_cross_investor_signals_with_valid_references() == ()
            )
        # Stored legacy projections remain; only current HTTP consumption excludes them.


def test_new_reason_and_legacy_values_are_independent_and_all_titles_readable():
    observed = IntelligencePriorityReason(REASON)
    for legacy in (
        IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
        IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
    ):
        assert observed is not legacy and observed.value != legacy.value
        assert IntelligencePriorityReason(legacy.value) is legacy
        assert "unverified" in IntelligenceFeedService._title(legacy)
    for reason in IntelligencePriorityReason:
        assert IntelligenceFeedService._title(reason)


def test_lifecycle_compatibility_types_no_longer_activate_old_facts(
    db_session_factory, production_policies, feed_api
):
    _chain(db_session_factory, production_policies)
    SignalGenerator.from_production(db_session_factory).generate(signal_types=CROSS)
    IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    IntelligencePriorityService.from_production(db_session_factory).materialize()
    IntelligenceFeedService.from_production(db_session_factory).materialize()
    later = FACT_TIME + timedelta(days=60)
    result = FeedLifecycleService.from_production(
        db_session_factory, policy=FeedLifecyclePolicy()
    ).apply(now=later)
    assert result.updated_count == 0 and result.plan.transitions == ()
    reasons = {reason for transition in result.plan.transitions for reason in transition.reasons}
    assert not ({"HIGH_PRIORITY", "CONSENSUS_EVENT", "CROSS_INVESTOR_EVENT"} & reasons)
    assert "WITHIN_ACTIVATION_WINDOW" not in reasons
    response = feed_api.get(
        "/api/intelligence/feed",
        params={"state": "ACTIVE", "since": (later - timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 200 and response.json()["total"] == 0
