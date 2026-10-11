"""Independent Discovery consumes real effective linked database evidence."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_intelligence_discovery_service
from backend.app.main import app
from contracts import FeedState, IntelligenceEventType, ThesisChangeType
from intelligence.discovery.service import IntelligenceDiscoveryService
from intelligence.read_scope import AssetIntelligenceReadScopeLoader
from tests.integration.test_cross_materialization_consistency import _mixed
from tests.integration.test_cross_signal_source_chains import CROSS
from tests.integration.test_effective_asset_context import _ready
from tests.integration.test_effective_thesis_feed_query import _legacy_feed, _snapshot
from tests.integration.test_effective_thesis_signals import _persist_signal, _shared_asset_change
from tests.integration.test_thesis_change_signals import FACT_TIME, _seed_change
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


@pytest.mark.parametrize("kind", ("thesis", *CROSS))
@pytest.mark.parametrize("field", ("count", "reason", "title", "context", "time"))
def test_actual_unrefreshed_projection_still_errors(
    db_session_factory, production_policies, monkeypatch, kind, field
):
    from database.models import IntelligenceEventPriority, IntelligenceFeedItem

    if kind == "thesis":
        _source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    else:
        _chain_data, feed = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _ready(db_session_factory)
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, feed.priority_id)
        row = session.get(IntelligenceFeedItem, feed.id)
        if field == "count":
            priority.evidence_count = 999
        elif field == "reason":
            priority.reason = row.reason = "THESIS_ACCELERATION"
        elif field == "title":
            row.title = "Old claim"
        elif field == "context":
            row.context = {"signal_count": 999}
        else:
            row.observed_at = FACT_TIME + timedelta(days=90)
        session.commit()
    service = IntelligenceDiscoveryService.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    with pytest.raises(ValueError, match="Context"):
        service.get_candidates()
    monkeypatch.setitem(
        app.dependency_overrides, get_intelligence_discovery_service, lambda: service
    )
    with TestClient(app) as client:
        assert client.get("/api/intelligence/discovery").status_code == 422
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", ("thesis", *CROSS))
def test_all_evidence_lost_is_excluded_read_only(db_session_factory, production_policies, kind):
    from sqlalchemy import select

    from database.models import CrossInvestorAssetSnapshot, EventAnalysis, Opinion

    if kind == "thesis":
        source, _feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    else:
        _chain_data, _feed = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _ready(db_session_factory)
    with db_session_factory() as session:
        if kind == "thesis":
            opinion = session.get(Opinion, source.current_opinion_id)
            session.get(EventAnalysis, opinion.analysis_id).analysis_version = "inactive"
        else:
            for snapshot in session.scalars(select(CrossInvestorAssetSnapshot)):
                snapshot.opinion_analysis_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    assert (
        IntelligenceDiscoveryService.from_production(db_session_factory).get_candidates().total == 0
    )
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_linked_equivalent_not_global_representative_is_consumed(
    db_session_factory, production_policies, kind
):
    from signal_engine.repository import SignalRepository
    from tests.integration.test_cross_signal_source_chains import START, _chain, _legacy
    from tests.integration.test_cross_snapshot_input_completeness import _refresh
    from tests.integration.test_effective_cross_feed_query import _historical_feed

    chain = _chain(db_session_factory, production_policies)
    other = _refresh(db_session_factory, chain, start=START - timedelta(hours=1))
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, other)]
    with db_session_factory() as session:
        representative = SignalRepository(
            session
        ).list_cross_investor_signals_with_valid_references(signal_types={kind})[0]
    linked = next(signal for signal in signals if signal.id != representative.id)
    _historical_feed(db_session_factory, chain[1].asset_id, [linked], kind, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    candidate = IntelligenceDiscoveryService.from_production(
        db_session_factory
    ).get_candidate_by_asset(chain[1].asset_id)
    assert candidate.activity_summary.signal_count == 1
    assert candidate.activity_summary.investor_count == 3
    assert candidate.timeline.latest_observed_at == FACT_TIME
    assert _snapshot(db_session_factory) == before


def test_late_predecessor_removes_old_evidence_without_borrowing_unlinked_signal(
    db_session_factory, production_policies
):
    from contracts import EventAnalysisStatus
    from database.models import Asset, Investor
    from tests.integration.test_thesis_change_signals import _add_opinion

    source, _feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
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
    unlinked = _shared_asset_change(
        db_session_factory,
        production_policies,
        source.asset_id,
        ThesisChangeType.THESIS_CHANGED,
        FACT_TIME,
    )
    _persist_signal(db_session_factory, unlinked)
    before = _snapshot(db_session_factory)
    assert (
        IntelligenceDiscoveryService.from_production(db_session_factory).get_candidates().total == 0
    )
    assert _snapshot(db_session_factory) == before


def test_effective_sort_filter_limit_and_missing_asset(db_session_factory, production_policies):
    from intelligence.discovery.service import DiscoveryAssetNotFoundError

    sources = [
        _history(db_session_factory, production_policies, state=FeedState.NEW)[0] for _ in range(2)
    ]
    _ready(db_session_factory)
    service = IntelligenceDiscoveryService.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    rows = service.get_candidates()
    expected = sorted(
        rows.items,
        key=lambda x: (
            -x.timeline.latest_observed_at.timestamp(),
            x.asset.name,
            x.asset.market,
            x.asset.symbol,
            x.asset.asset_id.int,
        ),
    )
    first = service.get_candidates(limit=1)
    assert first.total == 2 and first.has_more and list(first.items) == expected[:1]
    for source in sources:
        assert service.get_candidates(asset_id=source.asset_id).total == 1
    assert (
        service.get_candidates(event_type=IntelligenceEventType.CONSENSUS_STATE_CHANGE).total == 0
    )
    with pytest.raises(DiscoveryAssetNotFoundError):
        service.get_candidates(asset_id=uuid4())
    assert _snapshot(db_session_factory) == before


def test_real_http_dependency_enables_shared_evidence(
    db_session_factory, production_policies, monkeypatch
):
    from backend.app.api import dependencies

    source, _feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    monkeypatch.setattr(dependencies, "_read_only_session", db_session_factory)
    before = _snapshot(db_session_factory)
    with TestClient(app) as client:
        response = client.get(
            "/api/intelligence/discovery", params={"asset_id": str(source.asset_id)}
        )
    assert response.status_code == 200
    assert response.json()["items"][0]["activity_summary"]["signal_count"] == 1
    assert _snapshot(db_session_factory) == before


def test_source_preparation_once_per_distinct_scope(
    db_engine, db_session_factory, production_policies
):
    from sqlalchemy import event as sqlalchemy_event

    from tests.integration.test_cross_signal_source_chains import START, _chain, _legacy
    from tests.integration.test_cross_snapshot_input_completeness import _refresh
    from tests.integration.test_effective_cross_feed_query import _historical_feed

    chain = _chain(db_session_factory, production_policies)

    def add(version):
        for kind in CROSS:
            signal = _legacy(db_session_factory, version, kind)
            _historical_feed(
                db_session_factory, chain[1].asset_id, [signal], kind, state=FeedState.NEW
            )

    add(chain)
    _ready(db_session_factory)
    statements = []

    def track(_connection, _cursor, statement, *_args):
        statements.append(statement)

    def read():
        statements.clear()
        before = _snapshot(db_session_factory)
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            result = IntelligenceDiscoveryService.from_production(
                db_session_factory
            ).get_candidates()
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert result.items[0].activity_summary.signal_count == 2
        assert result.items[0].activity_summary.investor_count == 3
        assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
        assert _snapshot(db_session_factory) == before
        return len(statements)

    first = read()
    for offset in range(1, 6):
        add(_refresh(db_session_factory, chain, start=START - timedelta(hours=offset)))
    _ready(db_session_factory)
    second = read()
    assert second == first
    print(f"Discovery scopes 1/6 SELECT: {first}/{second}")


@pytest.mark.parametrize("missing", ("priority", "event"))
def test_missing_required_entity_is_not_hidden_as_empty(
    db_session_factory, production_policies, missing
):
    from database.models import IntelligenceEventPriority, IntelligenceFeedItem

    _source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    # The existing SQLite test fixture permits explicit orphan rows. Do not
    # weaken production constraints or mock the source selector to test reads.
    with db_session_factory() as session:
        if missing == "priority":
            session.get(IntelligenceFeedItem, feed.id).priority_id = uuid4()
        else:
            session.get(IntelligenceEventPriority, feed.priority_id).event_id = uuid4()
        session.commit()
    before = _snapshot(db_session_factory)
    with pytest.raises(ValueError, match="not found"):
        IntelligenceDiscoveryService.from_production(db_session_factory).get_candidates()
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", ("thesis", *CROSS))
def test_independent_http_and_scope_use_same_effective_evidence(
    db_session_factory, production_policies, monkeypatch, kind
):
    if kind == "thesis":
        source, _feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
        asset_id, voters = source.asset_id, 1
    else:
        chain, _feed = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
        asset_id, voters = chain[1].asset_id, 3
    _ready(db_session_factory)
    service = IntelligenceDiscoveryService.from_production(db_session_factory)
    monkeypatch.setitem(
        app.dependency_overrides, get_intelligence_discovery_service, lambda: service
    )
    before = _snapshot(db_session_factory)
    with TestClient(app) as client:
        response = client.get("/api/intelligence/discovery", params={"asset_id": str(asset_id)})
    assert response.status_code == 200, response.text
    candidate = service.get_candidate_by_asset(asset_id)
    scope = AssetIntelligenceReadScopeLoader.from_production(db_session_factory).load(
        asset_id, as_of=FACT_TIME + timedelta(hours=12)
    )
    scoped = service.get_scope_candidate(scope)
    assert candidate == scoped
    assert candidate.activity_summary.signal_count == 1
    assert candidate.activity_summary.investor_count == voters
    assert candidate.timeline.latest_observed_at == FACT_TIME
    assert response.json()["items"][0] == candidate.model_dump(mode="json")
    assert _snapshot(db_session_factory) == before


def test_four_effective_nine_historical_links_no_false_count_error(
    db_session_factory, production_policies
):
    first = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    sources = [first]
    for index in range(8):
        sources.append(
            _shared_asset_change(
                db_session_factory,
                production_policies,
                first.asset_id,
                ThesisChangeType.THESIS_CHANGED if index < 3 else ThesisChangeType.NEW_THESIS,
                FACT_TIME if index < 3 else FACT_TIME + timedelta(days=90),
            )
        )
    _legacy_feed(
        db_session_factory,
        first.asset_id,
        [_persist_signal(db_session_factory, source) for source in sources],
        state=FeedState.NEW,
    )
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    candidate = IntelligenceDiscoveryService.from_production(
        db_session_factory
    ).get_candidate_by_asset(first.asset_id)
    assert candidate.activity_summary.signal_count == candidate.activity_summary.investor_count == 4
    assert candidate.timeline.latest_observed_at == FACT_TIME
    assert len(before["intelligence_event_evidence"]) == 9
    assert _snapshot(db_session_factory) == before
