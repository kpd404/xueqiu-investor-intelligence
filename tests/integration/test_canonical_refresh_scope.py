"""Canonical orchestration, real DB/services; only the external comparator is a fixture."""

import asyncio
from datetime import timedelta

import pytest

from contracts import (
    EventAnalysisStatus,
    FeedState,
    ThesisChangeType,
    ThesisComparisonResult,
    ThesisComparisonSpec,
)
from database.models import (
    Asset,
    EventAnalysis,
    IntelligenceEventPriority,
    Investor,
    Opinion,
    ThesisChange,
)
from database.repositories.opinions import OpinionRepository
from intelligence.feed.lifecycle import FeedLifecyclePolicy, FeedLifecycleService
from intelligence.services.thesis_change import ThesisChangeService
from operations.refresh import CollectionStageResult, OperationalRefreshService
from tests.integration.test_effective_cross_feed_query import _http
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_feed import feed_api as feed_api
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion, _seed_change
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


@pytest.fixture
def offline_comparator(monkeypatch, production_policies):
    class FixtureComparator:
        # Deterministic structured provider fixture, not an Intelligence classifier.
        request_count = retry_count = 0
        calls = 0
        comparison_spec = ThesisComparisonSpec.from_analysis_spec(
            production_policies[1].active_spec
        )

        async def compare(self, input_data):
            self.calls += 1
            return ThesisComparisonResult(
                change_type=self.results.get(
                    input_data.current.opinion_id, ThesisChangeType.THESIS_CHANGED
                ),
                confidence=0.9,
                summary="Structured fixture change",
                evidence=("fixture",),
            )

    fixture = FixtureComparator()
    fixture.results = {}
    original = FeedLifecycleService.from_production
    monkeypatch.setattr(
        "operations.refresh.FeedLifecycleService.from_production",
        lambda factory: original(
            factory,
            policy=FeedLifecyclePolicy(),
            now_factory=lambda: FACT_TIME + timedelta(hours=12),
        ),
    )
    monkeypatch.setattr(
        "operations.refresh.OpenAICompatibleThesisComparator.from_settings", lambda: fixture
    )

    async def empty_external_collection(self, **kwargs):
        return CollectionStageResult(run_id=None, stop_reason="SOURCE_NO_OP")

    monkeypatch.setattr(OperationalRefreshService, "_collect", empty_external_collection)
    return fixture


def _align_identities(factory, policies, comparator):
    # The old generic fixtures use simple identities. Convert only their fixture
    # identities with the real service function before exercising canonical reuse.
    service = ThesisChangeService(lambda: None, policies[0].as_effective_policy(), comparator)
    from sqlalchemy import select

    with factory() as session:
        reader = OpinionRepository(session)
        for change in session.scalars(select(ThesisChange)):
            current = reader.get_effective_comparison_view(
                change.current_opinion_id, policies[0].as_effective_policy()
            )
            previous = (
                reader.get_effective_comparison_view(
                    change.previous_opinion_id, policies[0].as_effective_policy()
                )
                if change.previous_opinion_id
                else None
            )
            if current is not None:
                change.input_identity = service._input_identity(previous, current)
        session.commit()


def _run(factory, raw_ids=(), observer=None):
    return asyncio.run(
        OperationalRefreshService(factory, stage_observer=observer).run(
            skip_collection=bool(raw_ids),
            raw_event_ids=raw_ids,
            analysis_concurrency=1,
            attention_concurrency=1,
        )
    )


def test_observed_asset_does_not_fail_on_unrelated_old_thesis_feed(
    db_session_factory, production_policies, offline_comparator
):
    _old_source, old_feed = _history(db_session_factory, production_policies)
    current = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _align_identities(db_session_factory, production_policies, offline_comparator)
    before = _snapshot(db_session_factory)
    result = asyncio.run(
        OperationalRefreshService(db_session_factory).run(
            skip_collection=True,
            raw_event_ids=(current.current_event_id,),
            analysis_concurrency=1,
            attention_concurrency=1,
        )
    )
    assert result.result == "SUCCESS", result.errors
    assert result.counts["llm_requests"]["opinion_analysis"] == 0
    assert str(current.asset_id) in result.counts["affected_assets"]
    assert result.counts["events"]["deferred_feed_count"] == 1
    assert result.counts["feed_lifecycle"]["evaluated_items"] >= 1
    after = _snapshot(db_session_factory)
    for table in ("intelligence_event_priorities", "intelligence_feed_items"):
        key = old_feed.priority_id if table == "intelligence_event_priorities" else old_feed.id
        assert next(row for row in before[table] if row["id"] == key) == next(
            row for row in after[table] if row["id"] == key
        )


def test_clean_replay_and_no_collection_are_safe_without_llm_or_duplicate_artifacts(
    db_session_factory, production_policies, offline_comparator, feed_api
):
    current = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _align_identities(db_session_factory, production_policies, offline_comparator)
    first = _run(db_session_factory, (current.current_event_id,))
    assert first.result == "SUCCESS", first.errors
    body = _http(feed_api, state="ACTIVE", since=FACT_TIME.isoformat())
    assert body["total"] == 1 and body["items"][0]["context"]["signal_count"] == 1
    assert body["items"][0]["reason"] == "THESIS_CHANGE_OBSERVED"
    counts = first.database_after
    again = _run(db_session_factory, (current.current_event_id,))
    assert again.result == "SUCCESS", again.errors
    for key in (
        "raw_events",
        "event_analyses",
        "opinions",
        "thesis_changes",
        "signals",
        "intelligence_events",
        "intelligence_event_evidence",
        "priorities",
        "feed_items",
    ):
        assert again.database_after[key] == counts[key]
    assert offline_comparator.calls == 0
    assert set(again.counts["llm_requests"].values()) == {0}
    empty = _run(db_session_factory)
    assert empty.result == "SUCCESS", empty.errors
    assert empty.counts["feed_lifecycle"]["scope_event_ids"] == []
    assert empty.counts["feed_lifecycle"]["evaluated_items"] == 0
    assert empty.counts["events"]["deferred_feed_count"] == len(body["items"])


@pytest.mark.parametrize("loss", ("reduced", "all_late", "failed_source"))
def test_affected_old_projection_is_in_scope_even_without_new_material_candidate(
    db_session_factory, production_policies, offline_comparator, feed_api, loss, monkeypatch
):
    from tests.integration.test_effective_thesis_feed_query import _legacy_feed
    from tests.integration.test_effective_thesis_signals import _persist_signal
    from tests.integration.test_thesis_change_feed import _second_material_change

    old = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    if loss == "reduced":
        second = _second_material_change(db_session_factory, production_policies, old)
        # Two historically valid comparisons; late Opinion changes only second's predecessor.
        signals = [
            _persist_signal(db_session_factory, old),
            _persist_signal(db_session_factory, second),
        ]
    else:
        second = old
        signals = [_persist_signal(db_session_factory, old)]
    feed = _legacy_feed(db_session_factory, old.asset_id, signals, state=FeedState.NEW)
    _align_identities(db_session_factory, production_policies, offline_comparator)
    with db_session_factory() as session:
        if loss == "failed_source":
            opinion = session.get(Opinion, old.current_opinion_id)
            session.get(EventAnalysis, opinion.analysis_id).status = EventAnalysisStatus.FAILED
            raw_id = old.current_event_id
        else:
            time = (
                FACT_TIME + timedelta(minutes=30)
                if loss == "reduced"
                else FACT_TIME - timedelta(hours=12)
            )
            late = _add_opinion(
                session,
                session.get(Investor, old.investor_id),
                session.get(Asset, old.asset_id),
                production_policies[0].active_spec,
                time,
                EventAnalysisStatus.SUCCESS,
            )
            raw_id = late.event_id
            offline_comparator.results[late.id] = ThesisChangeType.THESIS_UNCHANGED
            offline_comparator.results[second.current_opinion_id] = (
                ThesisChangeType.THESIS_UNCHANGED
            )
        session.commit()
        target_event = session.get(IntelligenceEventPriority, feed.priority_id).event_id
    result = _run(db_session_factory, (raw_id,))
    assert result.stages["FEED_LIFECYCLE"]["status"] == "SUCCESS", result.errors
    if loss == "failed_source":
        assert (
            result.result == "PARTIAL_FAILURE"
        )  # existing FAILED Analysis is not silently successful
    elif loss == "all_late":
        assert result.result == "SUCCESS", result.errors
    else:
        # Asset Product now consumes the same corrected associated evidence.
        assert result.result == "SUCCESS", result.errors
        assert result.counts["product"]["failed"] == 0
    assert str(target_event) in result.counts["events"]["projection_event_ids"]
    assert str(feed.priority_id) in result.counts["priorities"]["projection_priority_ids"]
    assert str(target_event) in result.counts["feed_lifecycle"]["scope_event_ids"]
    with db_session_factory() as session:
        priority = session.get(IntelligenceEventPriority, feed.priority_id)
        if loss == "reduced":
            assert priority.evidence_count == 1
            assert priority.reason == "THESIS_CHANGE_OBSERVED"
            assert _http(feed_api, state="ACTIVE")["total"] == 1
            from operations.refresh import AssetIntelligenceProductService

            product = AssetIntelligenceProductService.from_production(
                db_session_factory
            ).get_asset_view(old.asset_id)
            assert product.context.activity_context.previous_signal_count == 1
            from backend.app.api.dependencies import (
                get_asset_intelligence_product_service,
                get_intelligence_context_service,
            )
            from backend.app.main import app
            from intelligence.context.service import IntelligenceContextService

            context_service = IntelligenceContextService.from_production(db_session_factory)
            product_service = AssetIntelligenceProductService.from_production(db_session_factory)
            for service in (context_service, product_service):
                service._scope_loader._now_factory = lambda: FACT_TIME + timedelta(hours=12)
            monkeypatch.setitem(
                app.dependency_overrides, get_intelligence_context_service, lambda: context_service
            )
            monkeypatch.setitem(
                app.dependency_overrides,
                get_asset_intelligence_product_service,
                lambda: product_service,
            )
            before_query = _snapshot(db_session_factory)
            for endpoint in ("context", "view"):
                response = feed_api.get(f"/api/intelligence/assets/{old.asset_id}/{endpoint}")
                assert response.status_code == 200
                payload = response.json()["context"] if endpoint == "view" else response.json()
                assert payload["activity_context"]["current_signal_count"] == 1
                assert payload["investor_context"]["current_investor_count"] == 1
            assert _snapshot(db_session_factory) == before_query
        else:
            assert result.counts["events"]["event_ids"] == []
            assert priority.evidence_count == 999  # skipped retained history, not forced to zero
            assert result.counts["feed_lifecycle"]["skipped_count"] == 1
            assert _http(feed_api)["total"] == 0


def test_between_stage_source_change_is_reported_at_exact_lifecycle_stage(
    db_session_factory, production_policies, offline_comparator
):
    from operations.refresh import RefreshStage
    from tests.integration.test_effective_thesis_signals import _shared_asset_change

    current = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _shared_asset_change(
        db_session_factory,
        production_policies,
        current.asset_id,
        ThesisChangeType.THESIS_CHANGED,
        FACT_TIME,
    )
    _align_identities(db_session_factory, production_policies, offline_comparator)

    def source_changes_after_feed(stage):
        if stage is not RefreshStage.FEED_LIFECYCLE:
            return
        with db_session_factory() as session:
            _add_opinion(
                session,
                session.get(Investor, current.investor_id),
                session.get(Asset, current.asset_id),
                production_policies[0].active_spec,
                FACT_TIME - timedelta(hours=12),
                EventAnalysisStatus.SUCCESS,
            )
            session.commit()

    result = _run(db_session_factory, (current.current_event_id,), source_changes_after_feed)
    assert result.result == "FAILED"
    assert result.errors[0]["stage"] == "FEED_LIFECYCLE"
    assert (
        "Priority evidence count does not match effective Thesis evidence"
        in result.errors[0]["message"]
    )
    assert result.stages["FEED"]["status"] == "SUCCESS"
    assert "PRODUCT_VERIFICATION" not in result.stages


def test_required_feed_coordination_failure_is_not_marked_success(
    db_session_factory, production_policies, offline_comparator, monkeypatch
):
    current = _seed_change(db_session_factory, production_policies, ThesisChangeType.THESIS_CHANGED)
    _align_identities(db_session_factory, production_policies, offline_comparator)

    def disk_failure(*args, **kwargs):
        raise RuntimeError("isolated feed write failure")

    # Fault injection into exactly one writer, not a replacement orchestration.
    from database.repositories.intelligence_feed_items import IntelligenceFeedItemRepository

    monkeypatch.setattr(IntelligenceFeedItemRepository, "add_if_absent", disk_failure)
    result = _run(db_session_factory, (current.current_event_id,))
    assert result.result == "FAILED"
    assert result.errors[0]["stage"] == "FEED"
    assert "isolated feed write failure" in result.errors[0]["message"]
    assert "FEED_LIFECYCLE" not in result.stages
