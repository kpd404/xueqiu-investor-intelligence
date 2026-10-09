"""Real corrected projections consumed by independent Context and Asset scope."""

from datetime import timedelta
from uuid import uuid4

import pytest

from contracts import FeedState
from database.models import (
    CrossInvestorAssetSnapshot,
    IntelligenceEventPriority,
    IntelligenceFeedItem,
)
from intelligence.context.service import IntelligenceContextService
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from intelligence.product.service import AssetIntelligenceProductService
from intelligence.read_scope import AssetIntelligenceReadScopeLoader
from signal_engine.repository import SignalRepository
from tests.integration.test_canonical_refresh_scope import offline_comparator as offline_comparator
from tests.integration.test_cross_materialization_consistency import _mixed
from tests.integration.test_cross_signal_source_chains import CROSS, _chain, _legacy
from tests.integration.test_cross_snapshot_input_completeness import _refresh
from tests.integration.test_effective_cross_feed_query import _historical_feed
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_signals import FACT_TIME
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


def _read_both(factory, asset_id, at):
    context = IntelligenceContextService.from_production(factory).get_asset_context(
        asset_id, as_of=at
    )
    product = AssetIntelligenceProductService.from_production(factory).get_asset_view(
        asset_id, as_of=at
    )
    for field in (
        "activity_context",
        "investor_context",
        "attention_context",
        "thesis_context",
        "timeline_context",
    ):
        assert getattr(context, field) == getattr(product.context, field)
    return context, product


def _ready(factory):
    IntelligencePriorityService.from_production(factory).materialize()
    IntelligenceFeedService.from_production(factory).materialize()
    FeedLifecycleService.from_production(factory, policy=FeedLifecyclePolicy()).apply(
        now=FACT_TIME + timedelta(hours=12)
    )


def test_reduced_thesis_context_and_product_use_effective_linked_input(
    db_session_factory, production_policies
):
    source, _feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    at = FACT_TIME + timedelta(hours=12)
    context = IntelligenceContextService.from_production(db_session_factory).get_asset_context(
        source.asset_id, as_of=at
    )
    product = AssetIntelligenceProductService.from_production(db_session_factory).get_asset_view(
        source.asset_id, as_of=at
    )
    assert (
        context.activity_context.current_signal_count
        == product.context.activity_context.current_signal_count
        == 1
    )
    assert context.investor_context.current_investor_count == 1
    assert context.timeline_context.latest_observed_at == FACT_TIME
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", ("thesis", *CROSS))
@pytest.mark.parametrize(
    "field", ("priority_count", "priority_reason", "title", "context", "observed_at")
)
def test_valid_evidence_requires_refreshed_projection_at_both_entry_points(
    db_session_factory, production_policies, kind, field
):
    if kind == "thesis":
        source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
        asset_id = source.asset_id
    else:
        chain, feed = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
        asset_id = chain[1].asset_id
    _ready(db_session_factory)
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, feed.priority_id)
        row = session.get(IntelligenceFeedItem, feed.id)
        if field == "priority_count":
            priority.evidence_count = 999
        elif field == "priority_reason":
            priority.reason = "THESIS_ACCELERATION"
        elif field == "context":
            row.context = {"signal_count": 999}
        elif field == "observed_at":
            row.observed_at = FACT_TIME + timedelta(days=90)
        else:
            row.title = "Old claim"
        session.commit()
    before = _snapshot(db_session_factory)
    for service, method in (
        (IntelligenceContextService.from_production(db_session_factory), "get_asset_context"),
        (AssetIntelligenceProductService.from_production(db_session_factory), "get_asset_view"),
    ):
        with pytest.raises(ValueError, match="Context"):
            getattr(service, method)(asset_id, as_of=FACT_TIME + timedelta(hours=12))
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", ("thesis", *CROSS))
def test_all_current_evidence_lost_excludes_active_history_without_writes(
    db_session_factory, production_policies, kind
):
    if kind == "thesis":
        source, _feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
        asset_id = source.asset_id
    else:
        chain, _feed = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
        asset_id = chain[1].asset_id
    _ready(db_session_factory)
    from sqlalchemy import select

    with db_session_factory() as session:
        if kind == "thesis":
            from database.models import EventAnalysis, Opinion

            op = session.get(Opinion, source.current_opinion_id)
            session.get(EventAnalysis, op.analysis_id).analysis_version = "inactive"
        else:
            for snapshot in session.scalars(
                select(CrossInvestorAssetSnapshot).where(
                    CrossInvestorAssetSnapshot.asset_id == asset_id
                )
            ):
                snapshot.opinion_analysis_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    context, product = _read_both(db_session_factory, asset_id, FACT_TIME + timedelta(hours=12))
    assert context.activity_context.current_signal_count == 0
    assert context.investor_context.current_investor_count == 0
    assert context.timeline_context.latest_observed_at is None
    assert not product.discovery.is_discoverable
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_associated_non_global_representative_and_votes_are_kept(
    db_session_factory, production_policies, kind
):
    from tests.integration.test_cross_signal_source_chains import START

    chain = _chain(db_session_factory, production_policies)
    other = _refresh(db_session_factory, chain, start=START - timedelta(hours=1))
    signals = [_legacy(db_session_factory, version, kind) for version in (chain, other)]
    with db_session_factory() as session:
        rep = SignalRepository(session).list_cross_investor_signals_with_valid_references(
            signal_types={kind}
        )[0]
    linked = next(signal for signal in signals if signal.id != rep.id)
    _historical_feed(db_session_factory, chain[1].asset_id, [linked], kind, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    context, _product = _read_both(
        db_session_factory, chain[1].asset_id, FACT_TIME + timedelta(hours=12)
    )
    assert context.activity_context.current_signal_count == 1
    assert context.investor_context.current_investor_count == 3
    assert _snapshot(db_session_factory) == before


def test_context_public_candidate_and_batch_use_shared_validated_scope(
    db_session_factory, production_policies
):
    source, _feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    at = FACT_TIME + timedelta(hours=12)
    scope = AssetIntelligenceReadScopeLoader.from_production(db_session_factory).load(
        source.asset_id, as_of=at
    )
    from intelligence.discovery.service import IntelligenceDiscoveryService

    candidate = IntelligenceDiscoveryService.from_production(
        db_session_factory
    ).get_scope_candidate(scope)
    context_service = IntelligenceContextService.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    expected = context_service.get_asset_context(source.asset_id, as_of=at)
    assert context_service.get_candidate_context(candidate, as_of=at) == expected
    assert context_service.batch_get_context((candidate,), as_of=at) == (expected,)
    assert context_service.batch_get_context(as_of=at) == (expected,)
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_attention_only_is_not_context_voter_and_new_invalid_time_is_ignored(
    db_session_factory, production_policies, kind
):
    from contracts import (
        AttentionEvidence,
        AttentionEvidenceType,
        AttentionOccurrenceCreate,
        EventAnalysisStatus,
    )
    from database.models import Asset, Investor
    from database.repositories.attention_occurrences import AttentionOccurrenceRepository
    from tests.integration.test_thesis_change_signals import _add_opinion

    chain = _chain(db_session_factory, production_policies)
    with db_session_factory() as session:
        investor = Investor(name="Attention only", platform="manual", platform_user_id=uuid4().hex)
        session.add(investor)
        session.flush()
        time = FACT_TIME + timedelta(hours=6)
        op = _add_opinion(
            session,
            investor,
            session.get(Asset, chain[1].asset_id),
            production_policies[0].active_spec,
            time,
            EventAnalysisStatus.FAILED,
        )
        AttentionOccurrenceRepository(session).replace_for_event(
            op.event_id,
            "attention-occurrence-v1",
            (
                AttentionOccurrenceCreate(
                    investor_id=investor.id,
                    asset_id=chain[1].asset_id,
                    event_id=op.event_id,
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
        attention_id = investor.id
    current = _refresh(db_session_factory, chain)
    signal = _legacy(db_session_factory, current, kind)
    _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind, state=FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    context, _product = _read_both(
        db_session_factory, chain[1].asset_id, FACT_TIME + timedelta(hours=12)
    )
    assert context.investor_context.current_investor_count == 3
    assert attention_id not in context.investor_context.new_investors
    assert context.timeline_context.latest_observed_at == FACT_TIME
    old_window, _product = _read_both(
        db_session_factory, chain[1].asset_id, FACT_TIME + timedelta(days=40)
    )
    assert old_window.activity_context.current_signal_count == 0
    assert old_window.activity_context.previous_signal_count == 1
    assert old_window.investor_context.previous_investor_count == 3
    assert _snapshot(db_session_factory) == before


def test_canonical_product_failure_still_returns_partial_not_success(
    db_session_factory, production_policies, monkeypatch, offline_comparator
):
    from contracts import ThesisChangeType
    from operations.refresh import AssetIntelligenceProductService
    from tests.integration.test_canonical_refresh_scope import _align_identities, _run
    from tests.integration.test_thesis_change_signals import _seed_change

    source = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _align_identities(db_session_factory, production_policies, offline_comparator)

    def failure(*args, **kwargs):
        raise ValueError("isolated product integrity failure")

    # Inject exactly one necessary product read fault, not a replacement stage.
    monkeypatch.setattr(AssetIntelligenceProductService, "get_asset_view", failure)
    result = _run(db_session_factory, (source.current_event_id,))
    assert result.result == "PARTIAL_FAILURE"
    assert result.stages["PRODUCT_VERIFICATION"]["status"] == "PARTIAL"
    assert result.counts["product"]["failed"] >= 1


def test_shared_product_read_only_source_queries_are_once_per_scope(
    db_engine, db_session_factory, production_policies
):
    from sqlalchemy import event as sqlalchemy_event

    from tests.integration.test_cross_signal_source_chains import START

    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        signal = _legacy(db_session_factory, chain, kind)
        _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind, state=FeedState.NEW)
    _ready(db_session_factory)
    statements = []

    def track(_connection, _cursor, statement, *_args):
        statements.append(statement)

    def read(product):
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            if product:
                view = AssetIntelligenceProductService.from_production(
                    db_session_factory
                ).get_asset_view(chain[1].asset_id, as_of=FACT_TIME + timedelta(days=2))
                assert view.context.activity_context.current_signal_count == 2
            else:
                view = IntelligenceContextService.from_production(
                    db_session_factory
                ).get_asset_context(chain[1].asset_id, as_of=FACT_TIME + timedelta(days=2))
                assert view.activity_context.current_signal_count == 2
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
        return len(statements)

    before = _snapshot(db_session_factory)
    first = read(True)
    assert first == 30
    assert read(False) == first
    assert _snapshot(db_session_factory) == before
    for offset in range(1, 6):
        version = _refresh(db_session_factory, chain, start=START - timedelta(hours=offset))
        for kind in CROSS:
            signal = _legacy(db_session_factory, version, kind)
            _historical_feed(db_session_factory, chain[1].asset_id, [signal], kind)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    assert read(True) == read(False) == first + 5 * 9
    assert _snapshot(db_session_factory) == before


def test_context_and_asset_http_use_real_shared_scope_and_report_inconsistency(
    db_session_factory, production_policies, monkeypatch
):
    from fastapi.testclient import TestClient

    from backend.app.api.dependencies import (
        get_asset_intelligence_product_service,
        get_intelligence_context_service,
    )
    from backend.app.main import app

    source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    context = IntelligenceContextService.from_production(db_session_factory)
    product = AssetIntelligenceProductService.from_production(db_session_factory)
    for service in (context, product):
        service._scope_loader._now_factory = lambda: FACT_TIME + timedelta(hours=12)
    monkeypatch.setitem(app.dependency_overrides, get_intelligence_context_service, lambda: context)
    monkeypatch.setitem(
        app.dependency_overrides, get_asset_intelligence_product_service, lambda: product
    )
    with TestClient(app) as client:
        before = _snapshot(db_session_factory)
        for endpoint in ("context", "view"):
            response = client.get(f"/api/intelligence/assets/{source.asset_id}/{endpoint}")
            assert response.status_code == 200
            data = response.json()["context"] if endpoint == "view" else response.json()
            assert data["activity_context"]["current_signal_count"] == 1
            assert data["investor_context"]["current_investor_count"] == 1
            assert data["thesis_context"]["current_thesis_changes"] == 1
        assert _snapshot(db_session_factory) == before
        with db_session_factory() as session:
            session.get(IntelligenceEventPriority, feed.priority_id).evidence_count = 2
            session.commit()
        before = _snapshot(db_session_factory)
        for endpoint in ("context", "view"):
            assert (
                client.get(f"/api/intelligence/assets/{source.asset_id}/{endpoint}").status_code
                == 422
            )
        assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_equivalent_cross_context_uses_real_votes_and_fact_time(
    db_session_factory, production_policies, kind
):
    chain, _feed = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    at = FACT_TIME + timedelta(hours=12)
    context = IntelligenceContextService.from_production(db_session_factory).get_asset_context(
        chain[1].asset_id, as_of=at
    )
    product = AssetIntelligenceProductService.from_production(db_session_factory).get_asset_view(
        chain[1].asset_id, as_of=at
    )
    assert context.activity_context.current_signal_count == 1
    assert (
        context.investor_context.current_investor_count
        == product.context.investor_context.current_investor_count
        == 3
    )
    assert set(context.investor_context.new_investors) == {s.investor_id for s in chain[0]}
    assert context.timeline_context.latest_observed_at == FACT_TIME
    assert _snapshot(db_session_factory) == before
