"""Historical Product audit references versus current validated associations."""

from datetime import timedelta

import pytest

from contracts import FeedState
from intelligence.product.service import AssetIntelligenceProductService
from tests.integration.test_cross_materialization_consistency import _mixed
from tests.integration.test_cross_signal_source_chains import CROSS
from tests.integration.test_effective_asset_context import _ready
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


@pytest.mark.parametrize("kind", ["thesis", *CROSS])
def test_traceability_preserves_history_and_resolves_only_consumed_sources(
    db_session_factory, production_policies, kind, monkeypatch
):
    if kind == "thesis":
        source, feed = _history(db_session_factory, production_policies, state=FeedState.NEW)
        asset_id = source.asset_id
    else:
        chain, feed = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
        asset_id = chain[1].asset_id
    _ready(db_session_factory)
    before = _snapshot(db_session_factory)
    product = AssetIntelligenceProductService.from_production(db_session_factory).get_asset_view(
        asset_id, as_of=FACT_TIME + timedelta(hours=12)
    )
    trace = product.traceability_summary
    assert trace.signal_count > 1  # compatibility: all persisted Asset Signals
    assert len(trace.historical_associations) > 1
    assert trace.validated_consumption.signal_count == 1
    assert len(trace.validated_consumption.chains) == 1
    chain = trace.validated_consumption.chains[0]
    assert chain.signal_id in trace.historical_signal_ids
    assert chain.opinion_facts
    assert all(fact.raw_event_id for fact in chain.opinion_facts)
    assert chain.investor_ids
    assert product.discovery.activity_summary.signal_count == 1
    assert product.context.activity_context.current_signal_count == 1
    from fastapi.testclient import TestClient

    from backend.app.api.dependencies import get_asset_intelligence_product_service
    from backend.app.main import app

    monkeypatch.setitem(
        app.dependency_overrides,
        get_asset_intelligence_product_service,
        lambda: AssetIntelligenceProductService.from_production(db_session_factory),
    )
    with TestClient(app) as http:
        response = http.get(
            f"/api/intelligence/assets/{asset_id}/view",
            params={"as_of": (FACT_TIME + timedelta(hours=12)).isoformat()},
        )
    assert response.status_code == 200, response.text
    assert response.json()["traceability_summary"] == trace.model_dump(mode="json")
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("invalid", ["nonmaterial", "inactive", "predecessor"])
def test_all_invalid_history_remains_auditable_not_current(
    db_session_factory, production_policies, invalid
):
    from contracts import EventAnalysisStatus, ThesisChangeType
    from database.models import Asset, Investor, ThesisChange
    from tests.integration.test_thesis_change_signals import _add_opinion

    source, _ = _history(db_session_factory, production_policies, state=FeedState.NEW)
    _ready(db_session_factory)
    with db_session_factory() as session:
        change = session.get(ThesisChange, source.id)
        if invalid == "nonmaterial":
            change.change_type = ThesisChangeType.THESIS_UNCHANGED.value
        elif invalid == "inactive":
            change.comparison_version = "inactive"
        else:
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
    product = AssetIntelligenceProductService.from_production(db_session_factory).get_asset_view(
        source.asset_id, as_of=FACT_TIME + timedelta(hours=12)
    )
    assert product.traceability_summary.signal_count == 2
    assert len(product.traceability_summary.historical_associations) == 2
    assert product.traceability_summary.validated_consumption.signal_count == 0
    assert product.traceability_summary.validated_consumption.chains == ()
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("scenario", ["attention_only", "non_global"])
def test_cross_provenance_uses_real_linked_votes_and_attention(
    db_session_factory, production_policies, feed_api, kind, scenario
):
    from sqlalchemy import select

    from database.models import Signal
    from tests.integration.test_effective_cross_feed_query import (
        test_attention_only_contributor_is_not_a_direction_voter,
        test_event_link_to_non_global_representative_is_kept,
    )

    # Reuse the full structured database fixture and its HTTP assertions, not a mocked selector.
    setup = (
        test_attention_only_contributor_is_not_a_direction_voter
        if scenario == "attention_only"
        else test_event_link_to_non_global_representative_is_kept
    )
    setup(db_session_factory, production_policies, feed_api, kind)
    _ready(db_session_factory)
    with db_session_factory() as session:
        asset_id = session.scalar(select(Signal.asset_id))
    before = _snapshot(db_session_factory)
    product = AssetIntelligenceProductService.from_production(db_session_factory).get_asset_view(
        asset_id, as_of=FACT_TIME + timedelta(hours=12)
    )
    trace = product.traceability_summary
    assert trace.validated_consumption.signal_count == 1
    chain = trace.validated_consumption.chains[0]
    assert len(chain.direction_voter_ids) == 3
    assert len(chain.attention_only_investor_ids) == (1 if scenario == "attention_only" else 0)
    assert set(chain.direction_voter_ids).isdisjoint(chain.attention_only_investor_ids)
    assert chain.signal_id in {link.signal_id for link in trace.historical_associations}
    from database.models import Opinion, RawEvent

    with db_session_factory() as session:
        for fact in chain.opinion_facts:
            opinion = session.get(Opinion, fact.opinion_id)
            raw = session.get(RawEvent, fact.raw_event_id)
            assert opinion.event_id == raw.id
            assert opinion.asset_id == asset_id
            assert opinion.investor_id == raw.investor_id == fact.investor_id
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize("invalid", ["failed_analysis", "inactive_snapshot"])
def test_invalid_cross_history_is_retained_but_never_exposed_as_current(
    db_session_factory, production_policies, kind, invalid
):
    from contracts import EventAnalysisStatus
    from database.models import CrossInvestorAssetSnapshot, EventAnalysis, Opinion

    source, _ = _mixed(db_session_factory, production_policies, kind, FeedState.NEW)
    _ready(db_session_factory)
    with db_session_factory() as session:
        if invalid == "failed_analysis":
            opinion = session.get(Opinion, source[0][0].current_opinion_id)
            session.get(
                EventAnalysis, opinion.analysis_id
            ).status = EventAnalysisStatus.FAILED.value
        else:
            from sqlalchemy import select

            for snapshot in session.scalars(select(CrossInvestorAssetSnapshot)):
                snapshot.cross_investor_policy_version = "inactive"
        session.commit()
    before = _snapshot(db_session_factory)
    trace = (
        AssetIntelligenceProductService.from_production(db_session_factory)
        .get_asset_view(source[1].asset_id, as_of=FACT_TIME + timedelta(hours=12))
        .traceability_summary
    )
    assert trace.signal_count == len(trace.historical_signal_ids) == 3
    assert len(trace.historical_associations) == 3
    assert trace.validated_consumption.signal_count == 0
    assert trace.validated_consumption.chains == ()
    assert _snapshot(db_session_factory) == before
