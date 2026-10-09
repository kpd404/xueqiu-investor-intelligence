"""Historical Feed pollution exercised through the real read-only HTTP path."""

from datetime import timedelta

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select

from contracts import (
    FeedItemCreate,
    FeedState,
    IntelligenceEventCreate,
    IntelligenceEventEvidenceCreate,
    IntelligenceEventPriorityCreate,
    IntelligenceEventType,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    SignalState,
    ThesisChangeType,
)
from database.base import Base
from database.repositories.intelligence_event_evidence import IntelligenceEventEvidenceRepository
from database.repositories.intelligence_event_priorities import IntelligenceEventPriorityRepository
from database.repositories.intelligence_events import IntelligenceEventRepository
from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository
from tests.integration import test_thesis_change_feed as feed_fixtures
from tests.integration import test_thesis_change_signals as signal_fixtures
from tests.integration.test_effective_thesis_signals import _persist_signal, _shared_asset_change
from tests.integration.test_thesis_change_signals import FACT_TIME, _seed_change

production_policies = signal_fixtures.production_policies
feed_api = feed_fixtures.feed_api


def _legacy_feed(factory, asset_id, signals, *, state=FeedState.ACTIVE, **updates):
    """Persist old Event/links/Priority/Feed without using corrected generators."""
    observed = updates.get("observed_at", FACT_TIME + timedelta(days=90))
    event_type = updates.get("event_type", IntelligenceEventType.INVESTOR_VIEW_CHANGE)
    with factory() as session:
        event, _ = IntelligenceEventRepository(session).add_if_absent(
            IntelligenceEventCreate(
                asset_id=updates.get("event_asset_id", asset_id),
                event_type=event_type,
                first_observed_at=observed,
                last_observed_at=observed,
                metadata={"signal_count": 999, "investor_ids": ["obsolete"]},
            )
        )
        for signal in signals:
            IntelligenceEventEvidenceRepository(session).add_if_absent(
                IntelligenceEventEvidenceCreate(event_id=event.id, signal_id=signal.id)
            )
        priority, _ = IntelligenceEventPriorityRepository(session).add_if_absent(
            IntelligenceEventPriorityCreate(
                event_id=event.id,
                priority_level=IntelligencePriorityLevel.MEDIUM,
                reason=IntelligencePriorityReason.THESIS_ACCELERATION,
                evidence_count=999,
                created_at=observed,
            )
        )
        feed, _ = IntelligenceFeedItemRepository(session).add_if_absent(
            FeedItemCreate(
                priority_id=priority.id,
                asset_id=updates.get("feed_asset_id", asset_id),
                event_type=event_type,
                title="Obsolete acceleration claim",
                context={
                    "signal_count": 999,
                    "source_count": 999,
                    "investor_count": 999,
                    "source_types": ["ObsoleteSource"],
                    "obsolete_claim": "acceleration",
                },
                reason=priority.reason,
                state=state,
                observed_at=observed,
                created_at=observed,
            )
        )
        session.commit()
        return feed


def _get(api, **params):
    response = api.get("/api/intelligence/feed", params=params)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    "invalid",
    (
        "NEW_THESIS",
        "THESIS_UNCHANGED",
        "INSUFFICIENT_EVIDENCE",
        "inactive_analysis",
        "inactive_comparison",
        "failed_analysis",
        "superseded_predecessor",
        "RESOLVED",
        "SUPERSEDED",
    ),
)
def test_active_legacy_feed_without_effective_thesis_is_excluded(
    db_session_factory, production_policies, feed_api, invalid
):
    kind = (
        ThesisChangeType(invalid)
        if invalid in ThesisChangeType.__members__
        else ThesisChangeType.THESIS_CHANGED
    )
    exclusion = (
        invalid
        if invalid.startswith("inactive")
        or invalid in {"failed_analysis", "superseded_predecessor"}
        else None
    )
    source = _seed_change(db_session_factory, production_policies, kind, exclusion=exclusion)
    updates = {"state": SignalState(invalid)} if invalid in {"RESOLVED", "SUPERSEDED"} else {}
    signal = _persist_signal(db_session_factory, source, **updates)
    _legacy_feed(db_session_factory, source.asset_id, (signal,))
    assert _get(feed_api, state="ACTIVE")["total"] == 0


def _mixed(factory, policies):
    valid = _seed_change(factory, policies, ThesisChangeType.THESIS_CHANGED)
    invalid = _shared_asset_change(
        factory,
        policies,
        valid.asset_id,
        ThesisChangeType.NEW_THESIS,
        FACT_TIME + timedelta(days=90),
    )
    good_signal = _persist_signal(factory, valid)
    bad_signal = _persist_signal(factory, invalid)
    feed = _legacy_feed(factory, valid.asset_id, (good_signal, bad_signal))
    return valid, invalid, good_signal, feed


def test_mixed_old_links_correct_context_investors_time_reason_and_title(
    db_session_factory, production_policies, feed_api
):
    valid, _, _, feed = _mixed(db_session_factory, production_policies)
    result = _get(feed_api, state="ACTIVE")
    assert result["total"] == 1
    item = result["items"][0]
    assert item["id"] == str(feed.id)
    assert item["reason"] == "THESIS_CHANGE_OBSERVED"
    assert item["title"] == "A thesis change was observed"
    assert item["context"] == {
        "signal_count": 1,
        "source_count": 1,
        "investor_count": 1,
        "source_types": ["ThesisChange"],
    }
    assert [investor["investor_id"] for investor in item["investors"]] == [str(valid.investor_id)]
    assert item["observed_at"] == FACT_TIME.isoformat().replace("+00:00", "Z")
    assert item["state"] == "ACTIVE"


def test_new_invalid_time_does_not_match_since_or_invalid_investor(
    db_session_factory, production_policies, feed_api
):
    valid, invalid, _, _ = _mixed(db_session_factory, production_policies)
    assert _get(feed_api, since=(FACT_TIME + timedelta(days=89)).isoformat())["total"] == 0
    assert _get(feed_api, investor_id=str(invalid.investor_id))["total"] == 0
    assert _get(feed_api, investor_id=str(valid.investor_id))["total"] == 1
    response = feed_api.get(f"/api/intelligence/investors/{invalid.investor_id}/feed")
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.parametrize("signal_offset", (-90, 90))
def test_source_fact_time_overrides_inconsistent_signal_and_feed_time_without_writes(
    db_session_factory, production_policies, feed_api, signal_offset
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    signal = _persist_signal(
        db_session_factory, source, observed_at=FACT_TIME + timedelta(days=signal_offset)
    )
    _legacy_feed(db_session_factory, source.asset_id, (signal,))
    item = _get(feed_api, state="ACTIVE", since=FACT_TIME.isoformat())["items"][0]
    assert item["observed_at"] == FACT_TIME.isoformat().replace("+00:00", "Z")
    assert _get(feed_api, since=(FACT_TIME + timedelta(days=1)).isoformat())["total"] == 0


def test_unlinked_material_signal_does_not_rescue_invalid_event(
    db_session_factory, production_policies, feed_api
):
    bad = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    good = _shared_asset_change(
        db_session_factory,
        production_policies,
        bad.asset_id,
        ThesisChangeType.THESIS_CHANGED,
        FACT_TIME + timedelta(hours=1),
    )
    _persist_signal(db_session_factory, good)
    _legacy_feed(db_session_factory, bad.asset_id, (_persist_signal(db_session_factory, bad),))
    assert _get(feed_api)["total"] == 0


@pytest.mark.parametrize("mismatch", ("event_asset", "feed_asset", "linked_signal_asset"))
def test_feed_event_and_effective_evidence_must_agree_on_asset(
    db_session_factory, production_policies, feed_api, mismatch
):
    first = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    other = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    signal = _persist_signal(
        db_session_factory, other if mismatch == "linked_signal_asset" else first
    )
    updates = {f"{mismatch}_id": other.asset_id} if mismatch != "linked_signal_asset" else {}
    _legacy_feed(db_session_factory, first.asset_id, (signal,), **updates)
    assert _get(feed_api)["total"] == 0


@pytest.mark.parametrize("state", tuple(FeedState))
def test_state_filter_preserves_stored_state_without_reactivation(
    db_session_factory, production_policies, feed_api, state
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _legacy_feed(
        db_session_factory,
        source.asset_id,
        (_persist_signal(db_session_factory, source),),
        state=state,
    )
    assert _get(feed_api, state=state.value)["items"][0]["state"] == state.value
    if state is not FeedState.ACTIVE:
        assert _get(feed_api, state="ACTIVE")["total"] == 0


def test_filter_sort_total_limit_and_has_more_use_effective_projection(
    db_session_factory, production_policies, feed_api
):
    expected = []
    for offset in (1, 2, 3):
        anchor = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
        source = _shared_asset_change(
            db_session_factory,
            production_policies,
            anchor.asset_id,
            ThesisChangeType.THESIS_CHANGED,
            FACT_TIME + timedelta(hours=offset),
        )
        feed = _legacy_feed(
            db_session_factory,
            source.asset_id,
            (_persist_signal(db_session_factory, source),),
            observed_at=FACT_TIME + timedelta(hours=10 - offset),
        )
        expected.append(feed.id)
    invalid = _seed_change(
        db_session_factory, production_policies, ThesisChangeType.THESIS_UNCHANGED
    )
    _legacy_feed(
        db_session_factory, invalid.asset_id, (_persist_signal(db_session_factory, invalid),)
    )
    page = _get(feed_api, state="ACTIVE", since=FACT_TIME.isoformat(), limit=2)
    assert page["total"] == 3 and page["limit"] == 2 and page["has_more"] is True
    assert [item["id"] for item in page["items"]] == [str(item) for item in reversed(expected[1:])]
    full = _get(feed_api, state="ACTIVE", limit=3)
    assert full["total"] == 3 and full["has_more"] is False
    assert [item["id"] for item in full["items"]] == [str(item) for item in reversed(expected)]


def _snapshot(factory):
    with factory() as session:
        return {
            table.name: tuple(
                session.execute(select(table).order_by(*table.primary_key.columns)).mappings()
            )
            for table in Base.metadata.sorted_tables
        }


def test_api_reads_all_business_tables_unchanged_and_uses_constant_batch_queries(
    db_engine, db_session_factory, production_policies, feed_api
):
    statements = []

    def track(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    def query_count():
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            response = _get(feed_api)
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        return response["total"], len(statements)

    _mixed(db_session_factory, production_policies)
    before = _snapshot(db_session_factory)
    assert query_count()[0] == 1
    first_count = query_count()[1]
    assert _snapshot(db_session_factory) == before
    for _ in range(5):
        _mixed(db_session_factory, production_policies)
    before = _snapshot(db_session_factory)
    total, last_count = query_count()
    assert total == 6
    assert first_count == last_count == 11
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize(
    "event_type",
    (
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        IntelligenceEventType.CONSENSUS_STATE_CHANGE,
    ),
)
def test_other_event_types_keep_stored_response_behavior(
    db_session_factory, production_policies, feed_api, event_type
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    signal = _persist_signal(db_session_factory, source, state=SignalState.RESOLVED)
    stored = _legacy_feed(db_session_factory, source.asset_id, (signal,), event_type=event_type)
    if event_type in {
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        IntelligenceEventType.CONSENSUS_STATE_CHANGE,
    }:
        # Cross Feed now requires linked current direction evidence. A resolved
        # non-material Thesis Signal cannot support these compatibility types.
        before = _snapshot(db_session_factory)
        assert _get(feed_api)["total"] == 0
        assert _snapshot(db_session_factory) == before
        return
    item = _get(feed_api)["items"][0]
    assert item["reason"] == stored.reason.value
    assert item["title"] == stored.title
    assert item["context"] == stored.context
    assert item["observed_at"] == stored.observed_at.isoformat().replace("+00:00", "Z")
