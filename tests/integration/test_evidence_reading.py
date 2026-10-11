"""Real database/API source reading; no source selectors or content providers mocked."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sql_event
from sqlalchemy import select, update

from backend.app.api.routes.intelligence_evidence import get_evidence_reading_service
from backend.app.main import app
from contracts import EventAnalysisStatus, FeedState, ThesisChangeType
from database.models import Asset, Investor, RawEvent, Signal
from intelligence.product.evidence import EvidenceReadingService, safe_source_url
from tests.integration.test_cross_signal_source_chains import CROSS
from tests.integration.test_effective_asset_context import _ready
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion, _seed_change
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


@pytest.fixture
def reading_api(db_session_factory, monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_evidence_reading_service,
        lambda: EvidenceReadingService(db_session_factory),
    )
    with TestClient(app) as client:
        yield client


def test_thesis_inbox_reads_exact_valid_pair_and_late_source_invalidates(
    db_session_factory,
    production_policies,
    reading_api,
):
    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    url = f"/api/intelligence/assets/{source.asset_id}/evidence"
    response = reading_api.get(url, params={"feed_id": str(feed.id)})
    assert response.status_code == 200, response.text
    group = response.json()["groups"][0]
    assert len(group["opinions"]) == 2
    assert {o["opinion_id"] for o in group["opinions"]} == {
        str(source.current_opinion_id),
        str(source.previous_opinion_id),
    }
    assert group["basis"] == "CURRENT_ASSOCIATION"
    assert group["comparison"]["change_type"] == "THESIS_CHANGED"
    assert all(o["raw"]["content"] == "Recorded thesis evidence" for o in group["opinions"])
    assert all(o["analysis_version"] for o in group["opinions"])
    assert _snapshot(db_session_factory) == before
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
    before = _snapshot(db_session_factory)
    assert reading_api.get(url, params={"signal_id": group["signal_id"]}).status_code == 409
    history = reading_api.get(url, params={"thesis_change_id": str(source.id), "history": "true"})
    assert history.status_code == 200, history.text
    assert history.json()["groups"][0]["basis"] == "HISTORICAL_REFERENCE"
    assert _snapshot(db_session_factory) == before


def test_first_observation_missing_fields_and_complete_safe_repost_read(
    db_session_factory,
    production_policies,
    reading_api,
):
    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.NEW_THESIS)
    body = "<p>作者自述</p>" + "长文内容" * 5000 + "//@引用作者:引用观点<script>alert(1)</script>"
    # Structured fixture setup in isolated SQLite only, before the read-only baseline.
    with db_session_factory() as session:
        session.execute(
            update(RawEvent)
            .where(RawEvent.id == source.current_event_id)
            .values(
                content=body,
                raw_data={"post_kind": "REPOST"},
                url="javascript:alert(1)",
            )
        )
        session.commit()
    before = _snapshot(db_session_factory)
    url = f"/api/intelligence/assets/{source.asset_id}/evidence"
    response = reading_api.get(url, params={"thesis_change_id": str(source.id)})
    assert response.status_code == 200, response.text
    group = response.json()["groups"][0]
    assert group["comparison"]["change_type"] == "NEW_THESIS"
    assert group["basis"] == "EFFECTIVE_HISTORY"
    assert len(group["opinions"]) == 1
    opinion = group["opinions"][0]
    assert opinion["risks"] == opinion["catalysts"] == []
    assert opinion["time_horizon"] is None
    assert opinion["raw"]["content"] == body
    assert len(opinion["raw"]["readable_content"]) > 20000
    assert "引用观点" not in opinion["raw"]["current_author_text"]
    assert "<script>" not in opinion["raw"]["readable_content"]
    assert opinion["raw"]["source_url"] is None
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_cross_reads_actual_votes_attention_only_and_batches_content(
    db_engine,
    db_session_factory,
    production_policies,
    reading_api,
    feed_api,
    kind,
):
    from tests.integration.test_effective_cross_feed_query import (
        test_attention_only_contributor_is_not_a_direction_voter,
    )

    test_attention_only_contributor_is_not_a_direction_voter(
        db_session_factory,
        production_policies,
        feed_api,
        kind,
    )
    _ready(db_session_factory)
    with db_session_factory() as session:
        asset_id = session.scalar(select(Signal.asset_id))
    before = _snapshot(db_session_factory)
    queries = []

    def track(_conn, _cursor, statement, *_args):
        queries.append(statement)

    sql_event.listen(db_engine, "before_cursor_execute", track)
    try:
        response = reading_api.get(f"/api/intelligence/assets/{asset_id}/evidence")
    finally:
        sql_event.remove(db_engine, "before_cursor_execute", track)
    assert response.status_code == 200, response.text
    group = response.json()["groups"][0]
    assert len(group["opinions"]) == len(group["direction_voter_ids"]) == 3
    assert len(group["attention_only_investor_ids"]) == 1
    assert sum(a["attention_only"] for a in group["attention"]) == 1
    assert all(o["role"] == "DIRECTION_VOTE" for o in group["opinions"])
    assert group["comparison"] is None
    assert group["source_window_start"] and group["source_window_end"]
    # Full content uses one Opinion batch and one Attention batch, never per voter.
    assert (
        sum(
            "raw_events.content" in q and "investors.name" in q and "FROM opinions JOIN" in q
            for q in queries
        )
        == 1
    )
    assert (
        sum(
            "raw_events.content" in q
            and "investors.name" in q
            and "FROM attention_occurrences JOIN" in q
            for q in queries
        )
        == 1
    )
    assert all(q.lstrip().upper().startswith("SELECT") for q in queries)
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "javascript:alert(1)",
        "data:text/html,x",
        "//xueqiu.com/1",
        "https://user:secret@example.test",
        "https://example.test/\n1",
    ],
)
def test_unsafe_or_missing_source_urls_are_not_linked(url):
    assert safe_source_url(url) is None


def test_saved_http_https_links_are_preserved():
    assert safe_source_url("https://xueqiu.com/123/456") == "https://xueqiu.com/123/456"
    assert safe_source_url("http://example.test/1") == "http://example.test/1"


def test_attention_inbox_reads_effective_source_without_direction_vote_claim(
    db_session_factory,
    production_policies,
    reading_api,
):
    from contracts import SignalType
    from intelligence.events.aggregator import IntelligenceEventAggregator
    from signal_engine.service import SignalGenerator
    from tests.integration.test_cross_signal_source_chains import _chain

    chain = _chain(db_session_factory, production_policies)
    SignalGenerator.from_production(db_session_factory).generate(
        signal_types={SignalType.NEW_ATTENTION}
    )
    IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    response = reading_api.get(f"/api/intelligence/assets/{chain[1].asset_id}/evidence")
    assert response.status_code == 200, response.text
    assert len(response.json()["groups"]) == 3
    for group in response.json()["groups"]:
        assert group["source_type"] == "AttentionOccurrence"
        assert group["direction_voter_ids"] == []
        assert group["opinions"][0]["role"] == "ATTENTION_OPINION"
        assert (
            group["attention"][0]["raw"]["raw_event_id"]
            == group["opinions"][0]["raw"]["raw_event_id"]
        )
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_non_global_representative_keeps_exact_associated_source_for_reading(
    db_session_factory,
    production_policies,
    feed_api,
    reading_api,
    kind,
):
    from tests.integration.test_effective_cross_feed_query import (
        test_event_link_to_non_global_representative_is_kept,
    )

    test_event_link_to_non_global_representative_is_kept(
        db_session_factory,
        production_policies,
        feed_api,
        kind,
    )
    _ready(db_session_factory)
    with db_session_factory() as session:
        asset_id = session.scalar(select(Signal.asset_id))
    before = _snapshot(db_session_factory)
    response = reading_api.get(f"/api/intelligence/assets/{asset_id}/evidence")
    assert response.status_code == 200, response.text
    assert len(response.json()["groups"]) == 1
    group = response.json()["groups"][0]
    assert len(group["opinions"]) == 3
    pinned = reading_api.get(
        f"/api/intelligence/assets/{asset_id}/evidence",
        params={"signal_id": group["signal_id"], "event_id": group["event_id"]},
    )
    assert pinned.json()["groups"] == [group]
    assert _snapshot(db_session_factory) == before
