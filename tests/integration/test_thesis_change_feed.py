"""Structured fixtures through real Thesis/Signal/Event/Priority/Feed services.

All persistence uses the isolated SQLite fixture. No LLM or production refresh
is invoked; only the historical-compatibility case seeds a legacy Priority.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from backend.app.api.dependencies import get_intelligence_feed_query_service
from backend.app.main import app
from contracts import (
    EventAnalysisStatus,
    FeedState,
    IntelligenceEventPriorityCreate,
    IntelligenceEventState,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    SignalType,
    ThesisChangeType,
)
from database.models import (
    Asset,
    IntelligenceEvent,
    IntelligenceEventEvidence,
    IntelligenceEventPriority,
    IntelligenceFeedItem,
    Investor,
    Signal,
)
from database.repositories.intelligence_event_priorities import (
    IntelligenceEventPriorityRepository,
)
from database.repositories.thesis_changes import ThesisChangeRepository
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService
from intelligence.feed.query import IntelligenceFeedQueryService
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from signal_engine.service import SignalGenerator
from tests.integration import test_thesis_change_signals as signal_fixtures
from tests.integration.test_thesis_change_signals import (
    FACT_TIME,
    TYPE_CASES,
    _add_opinion,
    _seed_change,
)

production_policies = signal_fixtures.production_policies
OBSERVED_REASON = "THESIS_CHANGE_OBSERVED"
NOW = FACT_TIME + timedelta(hours=12)


@pytest.fixture
def feed_api(db_session_factory, monkeypatch):
    service = IntelligenceFeedQueryService.from_production(db_session_factory)
    monkeypatch.setitem(
        app.dependency_overrides, get_intelligence_feed_query_service, lambda: service
    )
    with TestClient(app) as client:
        yield client


def _recent_feed(api, *, now=NOW):
    response = api.get(
        "/api/intelligence/feed",
        params={"state": "ACTIVE", "since": (now - timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 200
    return response.json()


def _generate_event(factory):
    signal_result = SignalGenerator.from_production(factory).generate(
        signal_types=(SignalType.THESIS_CHANGE,)
    )
    event_result = IntelligenceEventAggregator.from_production(factory).aggregate()
    return signal_result, event_result


def _downstream(factory, *, now=NOW):
    priorities = IntelligencePriorityService.from_production(factory).materialize()
    feed = IntelligenceFeedService.from_production(factory).materialize()
    lifecycle = FeedLifecycleService.from_production(factory, policy=FeedLifecyclePolicy()).apply(
        now=now
    )
    return priorities, feed, lifecycle


def _second_material_change(factory, policies, first):
    with factory() as session:
        current = _add_opinion(
            session,
            session.get(Investor, first.investor_id),
            session.get(Asset, first.asset_id),
            policies[0].active_spec,
            FACT_TIME + timedelta(hours=1),
            EventAnalysisStatus.SUCCESS,
        )
        command = first.model_copy(
            update={
                "previous_opinion_id": first.current_opinion_id,
                "previous_event_id": first.current_event_id,
                "current_opinion_id": current.id,
                "current_event_id": current.event_id,
                "effective_time": FACT_TIME + timedelta(hours=1),
                "change_type": ThesisChangeType.THESIS_EXTENDED,
                "input_identity": (
                    f"{first.current_opinion_id}:{current.id}:{first.comparison_version}"
                ),
            }
        )
        change = ThesisChangeRepository(session).add_if_absent(command)
        session.commit()
        return change


@pytest.mark.parametrize("change_type,eligible", TYPE_CASES, ids=[x[0].value for x in TYPE_CASES])
def test_single_thesis_change_reaches_recent_feed_only_when_material(
    db_session_factory, production_policies, feed_api, change_type, eligible
):
    change = _seed_change(db_session_factory, production_policies, change_type)
    signals, events = _generate_event(db_session_factory)
    priorities, feed, lifecycle = _downstream(db_session_factory)
    assert signals.created_count == events.created_event_count == int(eligible)
    assert (
        priorities.created_count == feed.created_count == lifecycle.updated_count == int(eligible)
    )
    response = _recent_feed(feed_api)
    assert response["total"] == int(eligible)
    if eligible:
        item = response["items"][0]
        assert item["reason"] == OBSERVED_REASON
        assert item["priority_level"] == "MEDIUM"
        assert item["title"] == "A thesis change was observed"
        assert item["context"]["signal_count"] == 1
        assert item["observed_at"] == FACT_TIME.isoformat().replace("+00:00", "Z")
        assert item["asset"]["asset_id"] == str(change.asset_id)
        assert signals.signals[0].source_id == change.id
        assert events.events[0].last_observed_at == change.effective_time
        assert priorities.priorities[0].event_id == events.events[0].id
        assert feed.items[0].priority_id == priorities.priorities[0].id
        assert lifecycle.plan.transitions[0].reasons == ("WITHIN_ACTIVATION_WINDOW",)


def test_two_material_changes_still_have_neutral_medium_priority(
    db_session_factory, production_policies, feed_api
):
    first = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    second = _second_material_change(db_session_factory, production_policies, first)
    signals, events = _generate_event(db_session_factory)
    assert {signal.source_id for signal in signals.signals} == {first.id, second.id}
    assert events.created_event_count == 1
    priorities, _, _ = _downstream(db_session_factory)
    assert priorities.priorities[0].reason.value == OBSERVED_REASON
    assert priorities.priorities[0].priority_level is IntelligencePriorityLevel.MEDIUM
    assert priorities.priorities[0].evidence_count == 2
    assert _recent_feed(feed_api)["items"][0]["reason"] == OBSERVED_REASON


@pytest.mark.parametrize("count", (1, 2))
def test_old_material_fact_does_not_activate_or_enter_recent_feed(
    db_session_factory, production_policies, feed_api, count
):
    first = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    if count == 2:
        _second_material_change(db_session_factory, production_policies, first)
    _generate_event(db_session_factory)
    old_now = NOW + timedelta(days=90)
    priorities, feed, lifecycle = _downstream(db_session_factory, now=old_now)
    assert priorities.priorities[0].reason.value == OBSERVED_REASON
    assert feed.items[0].observed_at == FACT_TIME + timedelta(hours=count - 1)
    assert lifecycle.updated_count == 0
    assert _recent_feed(feed_api, now=old_now)["total"] == 0
    response = feed_api.get("/api/intelligence/feed")
    assert response.status_code == 200
    assert response.json()["items"][0]["state"] == "NEW"


@pytest.mark.parametrize("state", (IntelligenceEventState.ACTIVE, IntelligenceEventState.RESOLVED))
def test_thesis_priority_requires_actual_evidence_and_active_event(
    db_session_factory, production_policies, state
):
    _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _, events = _generate_event(db_session_factory)
    with db_session_factory() as session:
        event = session.get(IntelligenceEvent, events.events[0].id)
        event.state = state.value
        event.metadata_json = {"signal_count": 999}
        if state is IntelligenceEventState.ACTIVE:
            session.execute(delete(IntelligenceEventEvidence))
        session.commit()
    service = IntelligencePriorityService.from_production(db_session_factory)
    assert service.dry_run().candidates == ()
    assert service.materialize().priorities == ()


def test_thesis_priority_uses_links_instead_of_metadata_count(
    db_session_factory, production_policies
):
    _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _, events = _generate_event(db_session_factory)
    with db_session_factory() as session:
        session.get(IntelligenceEvent, events.events[0].id).metadata_json = {"signal_count": 0}
        session.commit()
    plan = IntelligencePriorityService.from_production(db_session_factory).dry_run()
    assert len(plan.candidates) == 1
    assert plan.candidates[0].reason.value == OBSERVED_REASON
    assert plan.candidates[0].evidence_count == 1


def _counts(factory):
    with factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (
                Signal,
                IntelligenceEvent,
                IntelligenceEventEvidence,
                IntelligenceEventPriority,
                IntelligenceFeedItem,
            )
        )


def test_real_service_dry_runs_and_reruns_preserve_priority_and_feed_identity(
    db_session_factory, production_policies, feed_api
):
    _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    generator = SignalGenerator.from_production(db_session_factory)
    assert generator.dry_run(signal_types=(SignalType.THESIS_CHANGE,)).created_count == 1
    assert _counts(db_session_factory) == (0, 0, 0, 0, 0)
    generator.generate(signal_types=(SignalType.THESIS_CHANGE,))
    aggregator = IntelligenceEventAggregator.from_production(db_session_factory)
    assert aggregator.dry_run().created_event_count == 1
    assert _counts(db_session_factory) == (1, 0, 0, 0, 0)
    aggregator.aggregate()
    priority_service = IntelligencePriorityService.from_production(db_session_factory)
    assert priority_service.dry_run().created_count == 1
    assert _counts(db_session_factory) == (1, 1, 1, 0, 0)
    first_priority = priority_service.materialize().priorities[0]
    feed_service = IntelligenceFeedService.from_production(db_session_factory)
    assert feed_service.dry_run().created_count == 1
    assert _counts(db_session_factory) == (1, 1, 1, 1, 0)
    first_feed = feed_service.materialize().items[0]
    lifecycle = FeedLifecycleService.from_production(db_session_factory, now_factory=lambda: NOW)
    plan = lifecycle.dry_run(now=NOW)
    assert plan.updated_count == 1
    with db_session_factory() as session:
        assert session.get(IntelligenceFeedItem, first_feed.id).state == FeedState.NEW.value
    lifecycle.apply(plan=plan.plan)
    _generate_event(db_session_factory)
    second_priority, second_feed, second_lifecycle = _downstream(db_session_factory)
    assert (
        second_priority.created_count
        == second_feed.created_count
        == second_lifecycle.updated_count
        == 0
    )
    assert second_priority.reused_count == second_feed.reused_count == 1
    assert second_priority.priorities[0].id == first_priority.id
    assert second_feed.items[0].id == first_feed.id
    assert _counts(db_session_factory) == (1, 1, 1, 1, 1)
    assert _recent_feed(feed_api)["total"] == 1


def test_legacy_priority_is_readable_and_thesis_refresh_preserves_identity(
    db_session_factory, production_policies, feed_api
):
    first = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _second_material_change(db_session_factory, production_policies, first)
    _, events = _generate_event(db_session_factory)
    # This is explicitly a legacy-record fixture, not the positive pipeline.
    with db_session_factory() as session:
        old, _ = IntelligenceEventPriorityRepository(session).add_if_absent(
            IntelligenceEventPriorityCreate(
                event_id=events.events[0].id,
                priority_level=IntelligencePriorityLevel.MEDIUM,
                reason=IntelligencePriorityReason.THESIS_ACCELERATION,
                evidence_count=1,
                created_at=NOW,
            )
        )
        session.commit()
    service = IntelligencePriorityService.from_production(db_session_factory)
    plan = service.dry_run()
    assert plan.candidates[0].reason.value == OBSERVED_REASON
    assert plan.priorities[0].reason is IntelligencePriorityReason.THESIS_ACCELERATION
    reused = service.materialize()
    assert reused.created_count == 0
    assert reused.reused_count == 1
    assert reused.priorities[0].id == old.id
    assert reused.priorities[0].reason.value == OBSERVED_REASON
    assert reused.priorities[0].created_at == old.created_at
    assert reused.priorities[0].evidence_count == 2
    _downstream(db_session_factory)
    item = _recent_feed(feed_api)["items"][0]
    # The authorized Thesis-only materialization now corrects persisted derived
    # fields; the legacy enum remains readable before that refresh.
    assert item["reason"] == OBSERVED_REASON
    assert item["title"] == "A thesis change was observed"
    with db_session_factory() as session:
        assert session.get(IntelligenceEventPriority, old.id).reason == OBSERVED_REASON
        stored_feed = session.scalar(select(IntelligenceFeedItem))
        assert stored_feed.reason == OBSERVED_REASON
        assert stored_feed.title == "A thesis change was observed"


def test_new_and_legacy_thesis_reasons_are_distinct_contract_values():
    observed = IntelligencePriorityReason(OBSERVED_REASON)
    assert observed is not IntelligencePriorityReason.THESIS_ACCELERATION
    assert observed.value != IntelligencePriorityReason.THESIS_ACCELERATION.value
