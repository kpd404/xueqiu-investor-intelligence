from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_asset_intelligence_product_service
from backend.app.main import app
from contracts import (
    FeedItem,
    FeedState,
    IntelligenceAttentionClass,
    IntelligenceEventEvidenceView,
    IntelligenceEventPriorityView,
    IntelligenceEventState,
    IntelligenceEventType,
    IntelligenceEventView,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    SignalSeverity,
    SignalState,
    SignalType,
    SignalView,
    ThesisChangeType,
    ThesisChangeView,
)
from intelligence.attention_classification.rules import (
    AttentionClassificationFacts,
    classify_attention,
)
from intelligence.attention_classification.service import (
    IntelligenceAttentionClassificationService,
)
from intelligence.context.service import IntelligenceContextService
from intelligence.discovery.service import IntelligenceDiscoveryService
from intelligence.evolution.service import IntelligenceEvolutionService
from intelligence.narrative.service import IntelligenceNarrativeService
from intelligence.patterns.service import IntelligencePatternService
from intelligence.product.schemas import AssetIntelligenceView
from intelligence.product.service import AssetIntelligenceProductService
from intelligence.read_scope import (
    AssetIntelligenceReadScope,
    AssetIntelligenceReadScopeLoader,
    AssetIntelligenceReadScopeNotFoundError,
    AssetReadIdentity,
)

NOW = datetime(2026, 9, 19, tzinfo=UTC)
FORBIDDEN = {
    "score",
    "rank",
    "ranking",
    "weight",
    "hotness",
    "confidence",
    "recommendation",
    "prediction",
    "expected_return",
    "buy",
    "sell",
    "target_price",
}


def _walk_keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _walk_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_keys(child)


class _ScopeLoader:
    def __init__(self, scope):
        self.scope = scope
        self.calls = 0

    def load(self, asset_id, *, as_of=None):
        self.calls += 1
        if asset_id != self.scope.asset.asset_id:
            raise AssetIntelligenceReadScopeNotFoundError(str(asset_id))
        return self.scope


def _product_service(scope):
    loader = _ScopeLoader(scope)
    discovery = IntelligenceDiscoveryService(lambda: None)
    context = IntelligenceContextService(
        discovery,
        lambda: None,
        now_factory=lambda: NOW,
    )
    pattern = IntelligencePatternService(context)
    evolution = IntelligenceEvolutionService(
        discovery,
        context,
        pattern,
        lambda: None,
    )
    attention = IntelligenceAttentionClassificationService(
        discovery,
        evolution,
        lambda: None,
    )
    service = AssetIntelligenceProductService(
        loader,
        discovery,
        IntelligenceNarrativeService(discovery),
        context,
        pattern,
        evolution,
        attention,
    )
    return service, loader


def _thesis(asset_id, investor_id, *, change_type):
    current_opinion_id = uuid4()
    current_event_id = uuid4()
    return ThesisChangeView(
        id=uuid4(),
        investor_id=investor_id,
        asset_id=asset_id,
        previous_opinion_id=uuid4() if change_type != ThesisChangeType.NEW_THESIS else None,
        current_opinion_id=current_opinion_id,
        previous_event_id=uuid4() if change_type != ThesisChangeType.NEW_THESIS else None,
        current_event_id=current_event_id,
        effective_time=NOW - timedelta(days=1),
        change_type=change_type,
        confidence=0.7,
        summary="existing ThesisChange semantic",
        evidence=(),
        opinion_analysis_version="test-analysis",
        comparison_version="test-comparison",
        calculated_at=NOW,
        input_identity=str(uuid4()),
    )


def _discoverable_scope() -> AssetIntelligenceReadScope:
    asset_id = uuid4()
    investor_id = uuid4()
    thesis = _thesis(asset_id, investor_id, change_type=ThesisChangeType.THESIS_CHANGED)
    signal = SignalView(
        id=uuid4(),
        asset_id=asset_id,
        investor_id=investor_id,
        signal_type=SignalType.THESIS_CHANGE,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.LOW,
        source_type="ThesisChange",
        source_id=thesis.id,
        created_at=NOW,
        observed_at=thesis.effective_time,
        metadata={"change_type": thesis.change_type.value},
    )
    event = IntelligenceEventView(
        id=uuid4(),
        asset_id=asset_id,
        event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
        state=IntelligenceEventState.ACTIVE,
        first_observed_at=signal.observed_at,
        last_observed_at=signal.observed_at,
        metadata={"signal_count": 1},
    )
    priority = IntelligenceEventPriorityView(
        id=uuid4(),
        event_id=event.id,
        priority_level=IntelligencePriorityLevel.MEDIUM,
        reason=IntelligencePriorityReason.THESIS_ACCELERATION,
        evidence_count=1,
        created_at=NOW,
    )
    feed = FeedItem(
        id=uuid4(),
        priority_id=priority.id,
        asset_id=asset_id,
        event_type=event.event_type,
        title="Thesis activity",
        context={},
        reason=priority.reason,
        state=FeedState.ACTIVE,
        observed_at=signal.observed_at,
        created_at=NOW,
    )
    return AssetIntelligenceReadScope(
        asset=AssetReadIdentity(
            asset_id=asset_id,
            name="Product Asset",
            market="SH",
            symbol="600001",
        ),
        as_of=NOW,
        signals=(signal,),
        events=(event,),
        event_evidence=(
            IntelligenceEventEvidenceView(
                id=uuid4(),
                event_id=event.id,
                signal_id=signal.id,
            ),
        ),
        priorities=(priority,),
        feed_items=(feed,),
        thesis_changes=(thesis,),
        attention_occurrences=(),
        snapshots=(),
        alignments=(),
        consensus_evidences=(),
    )


def _no_feed_scope() -> AssetIntelligenceReadScope:
    asset_id = uuid4()
    investor_id = uuid4()
    thesis = _thesis(asset_id, investor_id, change_type=ThesisChangeType.NEW_THESIS)
    attention_source_id = uuid4()
    attention_signal = SignalView(
        id=uuid4(),
        asset_id=asset_id,
        investor_id=investor_id,
        signal_type=SignalType.NEW_ATTENTION,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.LOW,
        source_type="AttentionOccurrence",
        source_id=attention_source_id,
        created_at=NOW,
        observed_at=thesis.effective_time,
        metadata={},
    )
    thesis_signal = SignalView(
        id=uuid4(),
        asset_id=asset_id,
        investor_id=investor_id,
        signal_type=SignalType.THESIS_CHANGE,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.LOW,
        source_type="ThesisChange",
        source_id=thesis.id,
        created_at=NOW,
        observed_at=thesis.effective_time,
        metadata={"change_type": "NEW_THESIS"},
    )
    event = IntelligenceEventView(
        id=uuid4(),
        asset_id=asset_id,
        event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
        state=IntelligenceEventState.ACTIVE,
        first_observed_at=thesis.effective_time,
        last_observed_at=thesis.effective_time,
        metadata={"signal_count": 1},
    )
    return AssetIntelligenceReadScope(
        asset=AssetReadIdentity(
            asset_id=asset_id,
            name="中国海洋石油",
            market="HK",
            symbol="00883",
        ),
        as_of=NOW,
        signals=(attention_signal, thesis_signal),
        events=(event,),
        event_evidence=(
            IntelligenceEventEvidenceView(
                id=uuid4(),
                event_id=event.id,
                signal_id=thesis_signal.id,
            ),
        ),
        priorities=(),
        feed_items=(),
        thesis_changes=(thesis,),
        attention_occurrences=(),
        snapshots=(),
        alignments=(),
        consensus_evidences=(),
    )


def test_product_contract_and_composition_have_no_forbidden_fields():
    scope = _discoverable_scope()
    service, loader = _product_service(scope)

    view = service.get_asset_view(scope.asset.asset_id)

    assert isinstance(view, AssetIntelligenceView)
    assert loader.calls == 1
    assert view.discovery.is_discoverable is True
    assert view.review.attention_class is IntelligenceAttentionClass.IMMEDIATE_REVIEW
    assert "THESIS_TRANSITION" in view.current_state.patterns
    assert view.evolution.step_count >= 1
    assert view.feed.active_count == 1
    assert view.events.active_count == 1
    assert view.data_quality.historical_completeness == "UNKNOWN"
    assert view.data_quality.historical_comparison_supported is False
    assert view.data_quality.absence_inference_supported is False
    assert not FORBIDDEN.intersection(set(_walk_keys(view.model_dump())))


def test_event_active_does_not_equal_active_review_and_cnooc_history_remains_visible():
    scope = _no_feed_scope()
    service, _ = _product_service(scope)

    view = service.get_asset_view(scope.asset.asset_id)

    assert view.events.states == {"ACTIVE": 1}
    assert view.feed.active_count == 0
    assert view.discovery.is_discoverable is False
    assert view.review.attention_class is IntelligenceAttentionClass.BACKGROUND_MONITORING
    assert view.evolution.step_count == 2
    assert {"AttentionOccurrence", "ThesisChange"} <= set(view.traceability_summary.source_types)


def test_active_review_is_human_review_eligibility_not_event_lifecycle():
    event_only = classify_attention(
        AttentionClassificationFacts(
            active_event_count=1,
            historical_artifact_count=1,
        )
    )
    feed_eligible = classify_attention(
        AttentionClassificationFacts(
            active_event_count=1,
            active_feed_count=1,
            historical_artifact_count=1,
        )
    )
    discovery_eligible = classify_attention(
        AttentionClassificationFacts(
            discovery_candidate_present=True,
            historical_artifact_count=1,
        )
    )

    assert event_only.attention_class is IntelligenceAttentionClass.BACKGROUND_MONITORING
    assert feed_eligible.attention_class is IntelligenceAttentionClass.ACTIVE_REVIEW
    assert discovery_eligible.attention_class is IntelligenceAttentionClass.ACTIVE_REVIEW


def test_discovery_eligibility_does_not_automatically_upgrade_to_immediate_review():
    scope = _discoverable_scope()
    non_material = _thesis(
        scope.asset.asset_id,
        scope.signals[0].investor_id,
        change_type=ThesisChangeType.NEW_THESIS,
    )
    signal = scope.signals[0].model_copy(
        update={
            "source_id": non_material.id,
            "metadata": {"change_type": "NEW_THESIS"},
        }
    )
    scope = replace(
        scope,
        signals=(signal,),
        thesis_changes=(non_material,),
    )
    service, _ = _product_service(scope)

    view = service.get_asset_view(scope.asset.asset_id)

    assert view.discovery.is_discoverable is True
    assert view.current_state.patterns == ()
    assert view.review.attention_class is IntelligenceAttentionClass.ACTIVE_REVIEW


class _CountingAsset:
    def __init__(self, counts, asset):
        self.counts = counts
        self.asset = asset

    def get(self, asset_id):
        self.counts["asset"] += 1
        return self.asset if asset_id == self.asset.id else None


class _CountingAssetRows:
    def __init__(self, counts, key, values):
        self.counts = counts
        self.key = key
        self.values = tuple(values)

    def list_by_asset(self, asset_id, *args, **kwargs):
        self.counts[self.key] += 1
        return self.values

    def list_effective_by_asset(self, asset_id, *args, **kwargs):
        self.counts[self.key] += 1
        return list(self.values)


class _CountingEventRows:
    def __init__(self, counts, key, values):
        self.counts = counts
        self.key = key
        self.values = tuple(values)
        self.received_ids = None

    def list_by_event_ids(self, event_ids):
        self.counts[self.key] += 1
        self.received_ids = event_ids
        return self.values


class _CountingUow:
    def __init__(self, scope):
        self.counts = Counter()
        asset = SimpleNamespace(
            id=scope.asset.asset_id,
            name=scope.asset.name,
            market=scope.asset.market,
            symbol=scope.asset.symbol,
        )
        self.assets = _CountingAsset(self.counts, asset)
        self.signals = _CountingAssetRows(self.counts, "signals", scope.signals)
        self.intelligence_events = _CountingAssetRows(self.counts, "events", scope.events)
        self.intelligence_event_evidence = _CountingEventRows(
            self.counts, "event_evidence", scope.event_evidence
        )
        self.intelligence_event_priorities = _CountingEventRows(
            self.counts, "priorities", scope.priorities
        )
        self.intelligence_feed_items = _CountingAssetRows(self.counts, "feed", scope.feed_items)
        self.thesis_changes = _CountingAssetRows(self.counts, "thesis", scope.thesis_changes)
        self.attention_occurrences = _CountingAssetRows(
            self.counts, "attention", scope.attention_occurrences
        )
        self.cross_investor_asset_snapshots = _CountingAssetRows(
            self.counts, "snapshots", scope.snapshots
        )
        self.cross_investor_asset_alignments = _CountingAssetRows(
            self.counts, "alignments", scope.alignments
        )
        self.cross_investor_consensus_evidences = _CountingAssetRows(
            self.counts, "consensus", scope.consensus_evidences
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def test_shared_scope_has_bounded_repository_calls_and_no_event_n_plus_one():
    scope = _discoverable_scope()
    uow = _CountingUow(scope)
    loader = AssetIntelligenceReadScopeLoader(lambda: uow, now_factory=lambda: NOW)

    loaded = loader.load(scope.asset.asset_id)

    assert loaded.asset == scope.asset
    assert set(uow.counts) == {
        "asset",
        "signals",
        "events",
        "event_evidence",
        "priorities",
        "feed",
        "thesis",
        "attention",
        "snapshots",
        "alignments",
        "consensus",
    }
    assert all(value == 1 for value in uow.counts.values())
    assert uow.intelligence_event_evidence.received_ids == tuple(item.id for item in scope.events)


def test_scope_rejects_cross_listing_artifacts():
    scope = _discoverable_scope()
    foreign_signal = scope.signals[0].model_copy(update={"asset_id": uuid4()})

    with pytest.raises(ValueError, match="cross-listing"):
        replace(scope, signals=(foreign_signal,))


def test_narrative_and_pattern_evolution_are_composed_once_from_shared_results():
    scope = _discoverable_scope()
    service, _ = _product_service(scope)
    view = service.get_asset_view(scope.asset.asset_id)

    assert view.narrative.headline.startswith("Observed intelligence activity")
    assert view.current_state.patterns == ("THESIS_TRANSITION",)
    assert view.evolution.step_count == len(view.evolution.recent_steps)
    assert any(step.step_type.value == "THESIS_ACTIVITY" for step in view.evolution.recent_steps)


def test_data_quality_wording_recognizes_available_but_incomplete_provenance():
    scope = _no_feed_scope()
    service, _ = _product_service(scope)
    view = service.get_asset_view(scope.asset.asset_id)

    assert (
        "Available collection provenance does not establish historical completeness."
        in view.data_quality.limitations
    )
    assert not any(
        "Collection provenance is unavailable" in item for item in view.data_quality.limitations
    )


def test_product_api_and_existing_routes_remain_registered():
    scope = _discoverable_scope()
    service, _ = _product_service(scope)
    app.dependency_overrides[get_asset_intelligence_product_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/assets/{scope.asset.asset_id}/view")
        assert response.status_code == 200
        assert response.json()["asset"]["symbol"] == "600001"
    finally:
        app.dependency_overrides.pop(get_asset_intelligence_product_service, None)

    paths = set(app.openapi()["paths"])
    assert {
        "/api/intelligence/discovery",
        "/api/intelligence/assets/{asset_id}/narrative",
        "/api/intelligence/assets/{asset_id}/context",
        "/api/intelligence/assets/{asset_id}/patterns",
        "/api/intelligence/assets/{asset_id}/evolution",
        "/api/intelligence/assets/{asset_id}/attention-classification",
        "/api/intelligence/assets/{asset_id}/view",
    } <= paths


def test_unknown_asset_product_api_returns_404():
    class Missing:
        def get_asset_view(self, asset_id):
            raise AssetIntelligenceReadScopeNotFoundError(str(asset_id))

    app.dependency_overrides[get_asset_intelligence_product_service] = lambda: Missing()
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/assets/{uuid4()}/view")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_asset_intelligence_product_service, None)
