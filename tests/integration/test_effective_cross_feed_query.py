"""Historical cross Feed links through real source validation and HTTP queries."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event

from contracts import (
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceCreate,
    EventAnalysisStatus,
    FeedItemCreate,
    FeedState,
    IntelligenceEventCreate,
    IntelligenceEventEvidenceCreate,
    IntelligenceEventPriorityCreate,
    IntelligenceEventType,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    OpinionDirection,
    SignalState,
    ThesisChangeType,
)
from database.models import (
    Asset,
    CrossInvestorAssetSnapshot,
    EventAnalysis,
    Investor,
    Opinion,
    Signal,
)
from database.repositories.attention_occurrences import AttentionOccurrenceRepository
from database.repositories.intelligence_event_evidence import IntelligenceEventEvidenceRepository
from database.repositories.intelligence_event_priorities import IntelligenceEventPriorityRepository
from database.repositories.intelligence_events import IntelligenceEventRepository
from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository
from signal_engine.repository import SignalRepository
from tests.integration.test_cross_signal_source_chains import CROSS, END, START, _chain, _legacy
from tests.integration.test_cross_snapshot_input_completeness import _attention, _refresh
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion
from tests.integration.test_thesis_change_signals import production_policies as production_policies

EVENTS = (
    IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
    IntelligenceEventType.CONSENSUS_STATE_CHANGE,
)
CALC = FACT_TIME + timedelta(days=90)


def _historical_feed(
    factory,
    asset_id,
    signals,
    kind,
    *,
    state=FeedState.ACTIVE,
    observed_at=CALC,
    feed_asset_id=None,
    event_asset_id=None,
    feed_type=None,
):
    index = CROSS.index(kind)
    reason = (
        IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
        IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
    )[index]
    with factory() as session:
        event, _ = IntelligenceEventRepository(session).add_if_absent(
            IntelligenceEventCreate(
                asset_id=event_asset_id or asset_id,
                event_type=EVENTS[index],
                first_observed_at=observed_at,
                last_observed_at=observed_at,
                metadata={"signal_count": 999, "investor_ids": ["obsolete"]},
            )
        )
        for signal in signals:
            IntelligenceEventEvidenceRepository(session).add_if_absent(
                IntelligenceEventEvidenceCreate(
                    event_id=event.id,
                    signal_id=signal.id,
                )
            )
        priority, _ = IntelligenceEventPriorityRepository(session).add_if_absent(
            IntelligenceEventPriorityCreate(
                event_id=event.id,
                priority_level=IntelligencePriorityLevel.LOW
                if index == 0
                else IntelligencePriorityLevel.HIGH,
                reason=reason,
                evidence_count=999,
                created_at=observed_at,
            )
        )
        feed, _ = IntelligenceFeedItemRepository(session).add_if_absent(
            FeedItemCreate(
                priority_id=priority.id,
                asset_id=feed_asset_id or asset_id,
                event_type=feed_type or EVENTS[index],
                title="A consensus state change was observed",
                reason=reason,
                state=state,
                context={
                    "signal_count": 999,
                    "investor_count": 999,
                    "source_count": 999,
                    "source_types": ["ObsoleteSource"],
                    "_thesis_lifecycle": {"secret": True},
                },
                observed_at=observed_at,
                created_at=observed_at,
            )
        )
        session.commit()
        return feed


def _http(api, **params):
    response = api.get("/api/intelligence/feed", params=params)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("kind", CROSS)
def test_old_active_feed_with_inactive_source_is_excluded(
    db_session_factory, production_policies, feed_api, kind
):
    chain = _chain(db_session_factory, production_policies)
    signal = _legacy(db_session_factory, chain, kind)
    _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    with db_session_factory() as session:
        session.get(CrossInvestorAssetSnapshot, chain[1].id).opinion_analysis_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    assert _http(feed_api, state="ACTIVE")["total"] == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize(
    "invalid",
    (
        "failed",
        "late_input",
        "late_predecessor",
        "inactive_comparison",
        "non_active",
        "missing",
        "wrong_kind",
        "signal_asset",
        "signal_investor",
        "feed_asset",
        "event_asset",
        "feed_type",
    ),
)
def test_invalid_historical_associations_never_support_current_response(
    db_session_factory, production_policies, feed_api, kind, invalid
):
    chain = _chain(db_session_factory, production_policies)
    signal_kind = CROSS[1 - CROSS.index(kind)] if invalid == "wrong_kind" else kind
    signal = _legacy(
        db_session_factory,
        chain,
        signal_kind,
        **({"source_id": uuid4()} if invalid == "missing" else {}),
    )
    updates = {}
    other = None
    if invalid in {"signal_asset", "feed_asset", "event_asset"}:
        other = _chain(db_session_factory, production_policies)
        if invalid != "signal_asset":
            updates[invalid + "_id"] = other[1].asset_id
    if invalid == "feed_type":
        updates["feed_type"] = EVENTS[1 - CROSS.index(kind)]
    _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind, **updates)
    with db_session_factory() as session:
        source = chain[0][0]
        if invalid == "failed":
            opinion = session.get(Opinion, source.current_opinion_id)
            session.get(EventAnalysis, opinion.analysis_id).status = EventAnalysisStatus.FAILED
        elif invalid in {"late_input", "late_predecessor"}:
            _add_opinion(
                session,
                session.get(Investor, source.investor_id),
                session.get(Asset, source.asset_id),
                production_policies[0].active_spec,
                FACT_TIME + timedelta(hours=1)
                if invalid == "late_input"
                else FACT_TIME - timedelta(hours=12),
                EventAnalysisStatus.SUCCESS,
            )
        elif invalid == "inactive_comparison":
            from database.models import ThesisChange

            session.get(ThesisChange, source.id).comparison_version = "inactive"
        elif invalid == "non_active":
            session.get(Signal, signal.id).state = SignalState.SUPERSEDED.value
        elif invalid == "signal_asset":
            session.get(Signal, signal.id).asset_id = other[1].asset_id
        elif invalid == "signal_investor":
            session.get(Signal, signal.id).investor_id = source.investor_id
        session.commit()
    before = _snapshot(db_session_factory)
    assert _http(feed_api)["total"] == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_invalid_newer_source_votes_cannot_refresh_or_match_investor(
    db_session_factory, production_policies, feed_api, kind
):
    chain = _chain(db_session_factory, production_policies)
    from tests.integration.test_effective_thesis_signals import _shared_asset_change

    bad_investors = []
    for _ in range(3):
        source = _shared_asset_change(
            db_session_factory,
            production_policies,
            chain[1].asset_id,
            ThesisChangeType.THESIS_CHANGED,
            FACT_TIME + timedelta(days=3),
        )
        bad_investors.append(source.investor_id)
        with db_session_factory() as session:
            _attention(
                session, session.get(Opinion, source.current_opinion_id), source.effective_time
            )
            session.commit()
    newer = _refresh(db_session_factory, chain, end=FACT_TIME + timedelta(days=4))
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, newer)]
    _historical_feed(db_session_factory, chain[1].asset_id, signals, kind)
    with db_session_factory() as session:
        session.get(
            CrossInvestorAssetSnapshot, newer[1].id
        ).cross_investor_policy_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    item = _http(feed_api)["items"][0]
    assert item["context"] == {
        "signal_count": 1,
        "investor_count": 3,
        "source_count": 1,
        "source_types": [signals[0].source_type],
    }
    assert {i["investor_id"] for i in item["investors"]} == {str(s.investor_id) for s in chain[0]}
    assert _http(feed_api, since=(FACT_TIME + timedelta(days=1)).isoformat())["total"] == 0
    for investor in bad_investors:
        assert _http(feed_api, investor_id=str(investor))["total"] == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_attention_only_contributor_is_not_a_direction_voter(
    db_session_factory, production_policies, feed_api, kind
):
    chain = _chain(db_session_factory, production_policies)
    with db_session_factory() as session:
        investor = Investor(name="Attention only", platform="manual", platform_user_id=uuid4().hex)
        session.add(investor)
        session.flush()
        time = FACT_TIME + timedelta(hours=6)
        raw = _add_opinion(
            session,
            investor,
            session.get(Asset, chain[1].asset_id),
            production_policies[0].active_spec,
            time,
            EventAnalysisStatus.FAILED,
        )
        AttentionOccurrenceRepository(session).replace_for_event(
            raw.event_id,
            "attention-occurrence-v1",
            (
                AttentionOccurrenceCreate(
                    investor_id=investor.id,
                    asset_id=chain[1].asset_id,
                    event_id=raw.event_id,
                    published_time=time,
                    evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
                    evidence=(
                        AttentionEvidence(
                            evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                            matched_by="fixture",
                        ),
                    ),
                    attention_policy_version="attention-occurrence-v1",
                    calculated_at=CALC,
                ),
            ),
        )
        session.commit()
        mention_investor = investor.id
    refreshed = _refresh(db_session_factory, chain)
    assert refreshed[1].attention_investor_count == 4
    assert refreshed[1].opinion_investor_count == 3
    signal = _legacy(db_session_factory, refreshed, kind)
    _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    before = _snapshot(db_session_factory)
    item = _http(feed_api)["items"][0]
    assert item["context"]["investor_count"] == len(item["investors"]) == 3
    assert str(mention_investor) not in {i["investor_id"] for i in item["investors"]}
    assert _http(feed_api, investor_id=str(mention_investor))["total"] == 0
    assert _http(feed_api, since=(FACT_TIME + timedelta(hours=1)).isoformat())["total"] == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_distinct_historical_window_votes_not_combined_into_new_consensus(
    db_session_factory, production_policies, feed_api, kind
):
    chain = _chain(db_session_factory, production_policies)
    source = chain[0][0]
    later = FACT_TIME + timedelta(days=3)
    with db_session_factory() as session:
        opinion = _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            later,
            EventAnalysisStatus.SUCCESS,
        )
        opinion.direction = OpinionDirection.BEARISH
        _attention(session, opinion, later)
        session.commit()
    newer = _refresh(db_session_factory, chain, end=later + timedelta(days=1))
    assert chain[3].consensus_state.value == "CONSENSUS_BULLISH"
    assert newer[3].consensus_state.value == "DIVERGENT"
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, newer)]
    _historical_feed(db_session_factory, chain[1].asset_id, signals, kind)
    before = _snapshot(db_session_factory)
    item = _http(feed_api)["items"][0]
    assert item["context"]["signal_count"] == item["context"]["source_count"] == 2
    assert item["context"]["investor_count"] == len(item["investors"]) == 3
    assert set(item["context"]) == {
        "signal_count",
        "source_count",
        "source_types",
        "investor_count",
    }
    assert item["title"] == "Cross-investor direction evidence was observed"
    assert item["observed_at"] == later.isoformat().replace("+00:00", "Z")
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_duplicate_window_links_project_real_votes_and_fact_time(
    db_session_factory, production_policies, feed_api, kind
):
    chain = _chain(db_session_factory, production_policies)
    other = _refresh(
        db_session_factory, chain, start=START - timedelta(hours=1), end=END + timedelta(hours=1)
    )
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, other)]
    feed = _historical_feed(db_session_factory, chain[1].asset_id, signals, kind)
    before = _snapshot(db_session_factory)
    item = _http(feed_api, state="ACTIVE")["items"][0]
    assert item["context"]["signal_count"] == item["context"]["source_count"] == 1
    assert item["context"]["investor_count"] == 3
    assert {i["investor_id"] for i in item["investors"]} == {str(s.investor_id) for s in chain[0]}
    assert item["reason"] == "CROSS_INVESTOR_DIRECTION_EVIDENCE"
    assert item["title"] == "Cross-investor direction evidence was observed"
    assert item["observed_at"] == FACT_TIME.isoformat().replace("+00:00", "Z")
    assert item["id"] == str(feed.id) and item["created_at"] == CALC.isoformat().replace(
        "+00:00", "Z"
    )
    assert "_thesis_lifecycle" not in item["context"]
    assert _http(feed_api, since=(FACT_TIME + timedelta(days=1)).isoformat())["total"] == 0
    for source in chain[0]:
        assert _http(feed_api, investor_id=str(source.investor_id))["total"] == 1
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_event_link_to_non_global_representative_is_kept(
    db_session_factory, production_policies, feed_api, kind
):
    chain = _chain(db_session_factory, production_policies)
    other = _refresh(db_session_factory, chain, start=START - timedelta(hours=1))
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, other)]
    with db_session_factory() as session:
        global_rep = SignalRepository(session).list_cross_investor_signals_with_valid_references(
            signal_types={kind}
        )[0]
    linked = next(signal for signal in signals if signal.id != global_rep.id)
    _historical_feed(db_session_factory, chain[1].asset_id, [linked], kind)
    before = _snapshot(db_session_factory)
    body = _http(feed_api, state="ACTIVE")
    assert body["total"] == 1
    assert body["items"][0]["context"]["signal_count"] == 1
    assert body["items"][0]["context"]["investor_count"] == 3
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("invalid_link", (False, True))
def test_valid_unassociated_signal_never_fills_missing_event_evidence(
    db_session_factory, production_policies, feed_api, kind, invalid_link
):
    chain = _chain(db_session_factory, production_policies)
    other = _refresh(db_session_factory, chain, as_of=END + timedelta(days=1))
    unassociated = _legacy(db_session_factory, other, kind)
    linked = [_legacy(db_session_factory, chain, kind)] if invalid_link else []
    _historical_feed(db_session_factory, chain[1].asset_id, linked, kind)
    if invalid_link:
        with db_session_factory() as session:
            session.get(
                CrossInvestorAssetSnapshot, chain[1].id
            ).cross_investor_policy_version = "inactive"
            session.commit()
    with db_session_factory() as session:
        assert unassociated.id in {
            s.id
            for s in SignalRepository(session).list_cross_investor_signals_with_valid_references()
        }
    before = _snapshot(db_session_factory)
    assert _http(feed_api)["total"] == 0
    assert _snapshot(db_session_factory) == before


def _later_window(factory, policies, days):
    chain = _chain(factory, policies)
    time = FACT_TIME + timedelta(days=days)
    with factory() as session:
        for source in chain[0]:
            opinion = _add_opinion(
                session,
                session.get(Investor, source.investor_id),
                session.get(Asset, source.asset_id),
                policies[0].active_spec,
                time,
                EventAnalysisStatus.SUCCESS,
            )
            _attention(session, opinion, time)
        session.commit()
    return _refresh(factory, chain, end=time + timedelta(hours=1))


@pytest.mark.parametrize("kind", CROSS)
def test_filter_sort_pagination_and_feed_states_use_corrected_results(
    db_session_factory, production_policies, feed_api, kind
):
    entries = []
    for days, state in (
        (2, FeedState.ACTIVE),
        (3, FeedState.ACTIVE),
        (4, FeedState.STALE),
        (5, FeedState.RESOLVED),
        (6, FeedState.NEW),
    ):
        chain = _later_window(db_session_factory, production_policies, days)
        signal = _legacy(db_session_factory, chain, kind)
        item = _historical_feed(
            db_session_factory,
            chain[1].asset_id,
            [signal],
            kind,
            state=state,
            observed_at=CALC - timedelta(days=days),
        )
        entries.append((chain, item))
    bad = _chain(db_session_factory, production_policies)
    bad_signal = _legacy(db_session_factory, bad, kind)
    _historical_feed(
        db_session_factory,
        bad[1].asset_id,
        [bad_signal],
        kind,
        observed_at=CALC + timedelta(days=100),
    )
    with db_session_factory() as session:
        session.get(CrossInvestorAssetSnapshot, bad[1].id).opinion_analysis_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    active = _http(feed_api, state="ACTIVE", limit=1)
    assert active["total"] == 2 and active["has_more"] and active["limit"] == 1
    assert active["items"][0]["id"] == str(entries[1][1].id)
    all_rows = _http(feed_api, limit=100)
    assert all_rows["total"] == 5 and not all_rows["has_more"]
    assert [item["id"] for item in all_rows["items"]] == [
        str(entry[1].id) for entry in reversed(entries)
    ]
    for state in ("STALE", "RESOLVED", "NEW"):
        body = _http(feed_api, state=state)
        assert body["total"] == 1
        assert body["items"][0]["state"] == state
    recent = _http(
        feed_api, state="ACTIVE", since=(FACT_TIME + timedelta(days=2, hours=12)).isoformat()
    )
    assert recent["total"] == 1 and recent["items"][0]["id"] == str(entries[1][1].id)
    investor = entries[0][0][0][0].investor_id
    selected = _http(feed_api, investor_id=str(investor), state="ACTIVE")
    assert selected["total"] == 1 and selected["items"][0]["id"] == str(entries[0][1].id)
    assert _http(feed_api, asset_id=str(entries[0][0][1].asset_id))["total"] == 1
    assert _http(feed_api, event_type=EVENTS[1 - CROSS.index(kind)].value)["total"] == 0
    expected_level = "LOW" if kind is CROSS[0] else "HIGH"
    assert {item["priority_level"] for item in all_rows["items"]} == {expected_level}
    assert _http(feed_api, priority_level="MEDIUM")["total"] == 0
    assert _snapshot(db_session_factory) == before


def test_query_scope_batching_grows_with_scopes_not_signals_or_events(
    db_engine, db_session_factory, production_policies, feed_api
):
    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        signal = _legacy(db_session_factory, chain, kind)
        _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    statements = []

    def track(_connection, _cursor, statement, *_args):
        statements.append(statement)

    def count(**params):
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            body = _http(feed_api, **params)
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert all(value.lstrip().upper().startswith("SELECT") for value in statements)
        return body, len(statements)

    before = _snapshot(db_session_factory)
    assert count(event_type=EVENTS[0].value)[1] == 25
    assert count()[1] == 25  # two Events reuse the same scope and source reads
    assert _snapshot(db_session_factory) == before
    for _ in range(20):
        fake = _legacy(
            db_session_factory,
            chain,
            CROSS[0],
            source_id=uuid4(),
            metadata={"equivalence": "forged"},
        )
        _historical_feed(db_session_factory, chain[1].asset_id, [fake], CROSS[0])
    before = _snapshot(db_session_factory)
    body, queries = count()
    assert queries == 25 and body["total"] == 2
    assert _snapshot(db_session_factory) == before
    for offset in range(1, 6):
        version = _refresh(db_session_factory, chain, start=START - timedelta(hours=offset))
        for kind in CROSS:
            signal = _legacy(db_session_factory, version, kind)
            _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    before = _snapshot(db_session_factory)
    body, queries = count()
    assert queries == 70 and body["total"] == 2
    assert all(item["context"]["signal_count"] == 1 for item in body["items"])
    assert _snapshot(db_session_factory) == before
    for _ in range(5):
        other = _chain(db_session_factory, production_policies)
        for kind in CROSS:
            signal = _legacy(db_session_factory, other, kind)
            _historical_feed(db_session_factory, other[1].asset_id, [signal], kind)
    before = _snapshot(db_session_factory)
    body, queries = count()
    assert queries == 145 and body["total"] == 12
    assert _snapshot(db_session_factory) == before
