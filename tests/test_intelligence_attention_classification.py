from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_intelligence_attention_classification_service,
)
from backend.app.main import app
from contracts import (
    FeedItem,
    FeedState,
    IntelligenceAttentionClass,
    IntelligenceAttentionReason,
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
)
from intelligence.attention_classification.rules import (
    AttentionClassificationFacts,
    classify_attention,
)
from intelligence.attention_classification.service import (
    IntelligenceAttentionClassificationService,
)
from intelligence.discovery.service import DiscoveryAssetNotFoundError
from intelligence.evolution.schemas import (
    EvolutionAssetIdentity,
    EvolutionCurrentState,
    EvolutionSourceRef,
    EvolutionStep,
    EvolutionStepType,
    EvolutionTimelineRange,
    IntelligenceEvolutionView,
)
from intelligence.schemas.discovery import (
    DiscoveryActivitySummary,
    DiscoveryAssetIdentity,
    DiscoveryEventSummary,
    DiscoveryTimeline,
    IntelligenceDiscoveryCandidate,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)
FORBIDDEN_FIELDS = {
    "score",
    "rank",
    "ranking",
    "weight",
    "hotness",
    "confidence",
    "recommendation",
    "prediction",
    "buy",
    "sell",
    "target_price",
}


class _Reader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _Uow:
    def __init__(self, values):
        self.intelligence_events = _Reader(values.get("events", ()))
        self.intelligence_event_priorities = _Reader(values.get("priorities", ()))
        self.intelligence_feed_items = _Reader(values.get("feeds", ()))
        self.intelligence_event_evidence = _Reader(values.get("links", ()))
        self.signals = _Reader(values.get("signals", ()))
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


class _Discovery:
    def __init__(self, identities, candidates):
        self.identities = identities
        self.candidates = candidates

    def get_candidate_by_asset(self, asset_id):
        if asset_id not in self.identities:
            raise DiscoveryAssetNotFoundError(f"asset not found: {asset_id}")
        return self.candidates.get(asset_id)

    def get_asset_identity(self, asset_id):
        if asset_id not in self.identities:
            raise DiscoveryAssetNotFoundError(f"asset not found: {asset_id}")
        return self.identities[asset_id]


class _Evolution:
    def __init__(self, views):
        self.views = views

    def get_asset_evolution(self, asset_id):
        return self.views[asset_id]


def _identity(asset_id: UUID, name: str, market: str, symbol: str):
    return DiscoveryAssetIdentity(
        asset_id=asset_id,
        name=name,
        market=market,
        symbol=symbol,
    )


def _candidate(identity: DiscoveryAssetIdentity) -> IntelligenceDiscoveryCandidate:
    return IntelligenceDiscoveryCandidate(
        candidate_id=identity.asset_id,
        asset=identity,
        activity_summary=DiscoveryActivitySummary(
            investor_count=3,
            signal_count=1,
            event_count=1,
            feed_count=1,
        ),
        event_summary=DiscoveryEventSummary(
            event_types=(IntelligenceEventType.CONSENSUS_STATE_CHANGE,),
            priority_reasons=(IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,),
        ),
        timeline=DiscoveryTimeline(
            first_observed_at=NOW - timedelta(days=2),
            latest_observed_at=NOW - timedelta(days=1),
        ),
        discovery_reasons=["CONSENSUS_ACTIVITY"],
    )


def _evolution(
    identity: DiscoveryAssetIdentity,
    *,
    patterns=(),
    alignment=None,
    consensus=None,
    steps=(),
    limitations=(),
) -> IntelligenceEvolutionView:
    observed = [step.observed_at for step in steps]
    return IntelligenceEvolutionView(
        asset=EvolutionAssetIdentity(**identity.model_dump()),
        timeline=list(steps),
        current_state=EvolutionCurrentState(
            patterns=list(patterns),
            alignment_state=alignment,
            consensus_state=consensus,
        ),
        timeline_range=EvolutionTimelineRange(
            first_observed_at=min(observed) if observed else None,
            latest_observed_at=max(observed) if observed else None,
        ),
        limitations=list(limitations),
    )


def _service(identity, candidate, evolution, values):
    return IntelligenceAttentionClassificationService(
        _Discovery({identity.asset_id: identity}, {identity.asset_id: candidate}),
        _Evolution({identity.asset_id: evolution}),
        lambda: _Uow(values),
    )


def _active_fixture():
    asset_id = uuid4()
    identity = _identity(asset_id, "紫金矿业", "SH", "601899")
    event_id = uuid4()
    priority_id = uuid4()
    feed_id = uuid4()
    signal_id = uuid4()
    canonical_id = uuid4()
    event = IntelligenceEventView(
        id=event_id,
        asset_id=asset_id,
        event_type=IntelligenceEventType.CONSENSUS_STATE_CHANGE,
        state=IntelligenceEventState.ACTIVE,
        first_observed_at=NOW - timedelta(days=2),
        last_observed_at=NOW - timedelta(days=1),
        metadata={},
    )
    priority = IntelligenceEventPriorityView(
        id=priority_id,
        event_id=event_id,
        priority_level=IntelligencePriorityLevel.HIGH,
        reason=IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
        evidence_count=1,
        created_at=NOW,
    )
    signal = SignalView(
        id=signal_id,
        asset_id=asset_id,
        investor_id=uuid4(),
        signal_type=SignalType.CONSENSUS_CHANGE,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.HIGH,
        source_type="CrossInvestorConsensusEvidence",
        source_id=canonical_id,
        created_at=NOW,
        observed_at=NOW - timedelta(days=1),
        metadata={},
    )
    feed = FeedItem(
        id=feed_id,
        priority_id=priority_id,
        asset_id=asset_id,
        event_type=event.event_type,
        title="Consensus state change",
        context={},
        reason=priority.reason,
        state=FeedState.ACTIVE,
        observed_at=event.last_observed_at,
        created_at=NOW,
    )
    step = EvolutionStep(
        step_id=uuid4(),
        observed_at=event.last_observed_at,
        step_type=EvolutionStepType.CONSENSUS_STATE,
        asset_id=asset_id,
        title="Consensus state observed",
        facts=["Consensus state: DIVERGENT."],
        source_refs=[
            EvolutionSourceRef(
                source_type="CrossInvestorConsensusEvidence", source_id=canonical_id
            ),
        ],
    )
    links = (
        IntelligenceEventEvidenceView(
            id=uuid4(),
            event_id=event_id,
            signal_id=signal_id,
        ),
    )
    evolution = _evolution(
        identity,
        patterns=("CONSENSUS_FRAGMENTATION",),
        alignment="MIXED_DIRECTION",
        consensus="DIVERGENT",
        steps=(step,),
        limitations=("Historical completeness is UNKNOWN.",),
    )
    return (
        identity,
        _candidate(DiscoveryAssetIdentity(**identity.model_dump())),
        evolution,
        {
            "events": (event,),
            "priorities": (priority,),
            "feeds": (feed,),
            "links": links,
            "signals": (signal,),
        },
        {
            "event": event_id,
            "priority": priority_id,
            "feed": feed_id,
            "signal": signal_id,
            "canonical": canonical_id,
        },
    )


def _walk_keys(value):
    if isinstance(value, dict):
        yield from value.keys()
        for child in value.values():
            yield from _walk_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_keys(child)


def test_contract_enumerates_review_classes_and_forbids_ranking_fields():
    assert set(IntelligenceAttentionClass) == {
        IntelligenceAttentionClass.IMMEDIATE_REVIEW,
        IntelligenceAttentionClass.ACTIVE_REVIEW,
        IntelligenceAttentionClass.BACKGROUND_MONITORING,
        IntelligenceAttentionClass.LIMITED_CONTEXT,
    }
    assert set(IntelligenceAttentionReason) >= {
        IntelligenceAttentionReason.CONSENSUS_STATE_CHANGE,
        IntelligenceAttentionReason.CONSENSUS_FRAGMENTATION,
        IntelligenceAttentionReason.MULTI_INVESTOR_EXPANSION,
        IntelligenceAttentionReason.THESIS_TRANSITION,
        IntelligenceAttentionReason.HIGH_PRIORITY_EVIDENCE,
    }


def test_every_attention_class_rule_is_deterministic():
    immediate = classify_attention(
        AttentionClassificationFacts(
            active_event_types=frozenset({"CONSENSUS_STATE_CHANGE"}),
            active_priority_levels=frozenset({"HIGH"}),
            active_event_count=1,
        )
    )
    active = classify_attention(
        AttentionClassificationFacts(
            active_event_types=frozenset({"CROSS_INVESTOR_DISCOVERY"}),
            active_priority_levels=frozenset({"LOW"}),
            active_event_count=1,
            active_feed_count=1,
        )
    )
    background = classify_attention(AttentionClassificationFacts(historical_artifact_count=2))
    limited = classify_attention(AttentionClassificationFacts())

    assert immediate.attention_class is IntelligenceAttentionClass.IMMEDIATE_REVIEW
    assert active.attention_class is IntelligenceAttentionClass.ACTIVE_REVIEW
    assert background.attention_class is IntelligenceAttentionClass.BACKGROUND_MONITORING
    assert limited.attention_class is IntelligenceAttentionClass.LIMITED_CONTEXT


def test_immediate_precedence_combines_explicit_change_reasons():
    decision = classify_attention(
        AttentionClassificationFacts(
            active_event_types=frozenset({"CONSENSUS_STATE_CHANGE"}),
            active_priority_levels=frozenset({"HIGH"}),
            active_event_count=1,
            active_feed_count=1,
            pattern_types=frozenset(
                {"CONSENSUS_FRAGMENTATION", "MULTI_INVESTOR_EXPANSION", "THESIS_TRANSITION"}
            ),
            current_alignment="MIXED_DIRECTION",
            current_consensus="DIVERGENT",
            historical_artifact_count=3,
        )
    )

    assert decision.attention_class is IntelligenceAttentionClass.IMMEDIATE_REVIEW
    assert decision.reasons == (
        IntelligenceAttentionReason.CONSENSUS_STATE_CHANGE,
        IntelligenceAttentionReason.CONSENSUS_FRAGMENTATION,
        IntelligenceAttentionReason.MULTI_INVESTOR_EXPANSION,
        IntelligenceAttentionReason.THESIS_TRANSITION,
        IntelligenceAttentionReason.HIGH_PRIORITY_EVIDENCE,
    )


def test_consensus_insufficient_evidence_is_not_disagreement_by_itself():
    decision = classify_attention(
        AttentionClassificationFacts(
            active_event_types=frozenset({"CROSS_INVESTOR_DISCOVERY"}),
            active_priority_levels=frozenset({"LOW"}),
            active_event_count=1,
            active_feed_count=1,
            current_alignment="ALIGNED_BULLISH",
            current_consensus="INSUFFICIENT_EVIDENCE",
        )
    )
    assert decision.attention_class is IntelligenceAttentionClass.ACTIVE_REVIEW
    assert IntelligenceAttentionReason.CONSENSUS_FRAGMENTATION not in decision.reasons

    mixed = classify_attention(
        AttentionClassificationFacts(
            active_event_count=1,
            pattern_types=frozenset({"CONSENSUS_FRAGMENTATION"}),
            current_alignment="MIXED_DIRECTION",
            current_consensus="INSUFFICIENT_EVIDENCE",
        )
    )
    assert mixed.attention_class is IntelligenceAttentionClass.IMMEDIATE_REVIEW
    assert IntelligenceAttentionReason.CONSENSUS_FRAGMENTATION in mixed.reasons


def test_historical_completeness_guard_ignores_absence_sensitive_pattern_labels():
    decision = classify_attention(
        AttentionClassificationFacts(
            pattern_types=frozenset({"NEW_DISCOVERY", "ACCELERATING_ACTIVITY"}),
        )
    )
    assert decision.attention_class is IntelligenceAttentionClass.LIMITED_CONTEXT
    assert decision.reasons == (IntelligenceAttentionReason.LIMITED_CONTEXT,)


def test_active_traceability_listing_identity_and_read_only_boundary():
    identity, candidate, evolution, values, ids = _active_fixture()
    other_asset = uuid4()
    other_event = IntelligenceEventView(
        id=uuid4(),
        asset_id=other_asset,
        event_type=IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        state=IntelligenceEventState.ACTIVE,
        first_observed_at=NOW,
        last_observed_at=NOW,
        metadata={},
    )
    values["events"] = (*values["events"], other_event)
    view = _service(identity, candidate, evolution, values).get_asset_attention_classification(
        identity.asset_id
    )

    assert view.attention_class is IntelligenceAttentionClass.IMMEDIATE_REVIEW
    assert view.asset.market == "SH"
    assert view.asset.symbol == "601899"
    assert ids["event"] in {
        ref.source_id for ref in view.evidence_refs if ref.source_type == "IntelligenceEvent"
    }
    assert ids["priority"] in {
        ref.source_id
        for ref in view.evidence_refs
        if ref.source_type == "IntelligenceEventPriority"
    }
    assert ids["feed"] in {
        ref.source_id for ref in view.evidence_refs if ref.source_type == "IntelligenceFeedItem"
    }
    assert ids["signal"] in {
        ref.source_id for ref in view.evidence_refs if ref.source_type == "Signal"
    }
    assert ids["canonical"] in {
        ref.source_id
        for ref in view.evidence_refs
        if ref.source_type == "CrossInvestorConsensusEvidence"
    }
    assert view.evidence_summary.evidence_ref_count == len(view.evidence_refs)
    assert not FORBIDDEN_FIELDS.intersection(set(_walk_keys(view.model_dump())))


def test_classification_read_scope_never_commits():
    identity, candidate, evolution, values, _ = _active_fixture()
    uow = _Uow(values)
    service = IntelligenceAttentionClassificationService(
        _Discovery({identity.asset_id: identity}, {identity.asset_id: candidate}),
        _Evolution({identity.asset_id: evolution}),
        lambda: uow,
    )

    service.get_asset_attention_classification(identity.asset_id)

    assert uow.commit_count == 0


def test_no_discovery_candidate_with_historical_artifact_is_background_not_empty():
    asset_id = uuid4()
    identity = _identity(asset_id, "中国海洋石油", "HK", "00883")
    attention_id = uuid4()
    thesis_id = uuid4()
    steps = (
        EvolutionStep(
            step_id=uuid4(),
            observed_at=NOW - timedelta(days=10),
            step_type=EvolutionStepType.INVESTOR_ATTENTION_ADDED,
            asset_id=asset_id,
            title="Investor attention observed",
            source_refs=[
                EvolutionSourceRef(source_type="AttentionOccurrence", source_id=attention_id)
            ],
        ),
        EvolutionStep(
            step_id=uuid4(),
            observed_at=NOW - timedelta(days=5),
            step_type=EvolutionStepType.THESIS_ACTIVITY,
            asset_id=asset_id,
            title="Thesis activity observed",
            source_refs=[EvolutionSourceRef(source_type="ThesisChange", source_id=thesis_id)],
        ),
    )
    evolution = _evolution(
        identity,
        steps=steps,
        limitations=("Historical completeness is UNKNOWN.",),
    )
    service = _service(identity, None, evolution, {})

    view = service.get_asset_attention_classification(asset_id)

    assert view.attention_class is IntelligenceAttentionClass.BACKGROUND_MONITORING
    assert view.evidence_summary.discovery_candidate_present is False
    assert view.evidence_summary.historical_artifact_count == 2
    assert any("historical artifacts remain visible" in item for item in view.limitations)
    assert any("does not infer cooling" in item for item in view.limitations)
    assert {attention_id, thesis_id} <= {ref.source_id for ref in view.evidence_refs}


def test_deterministic_output_is_stable_for_identical_read_inputs():
    identity, candidate, evolution, values, _ = _active_fixture()
    service = _service(identity, candidate, evolution, values)
    first = service.get_asset_attention_classification(identity.asset_id)
    second = service.get_asset_attention_classification(identity.asset_id)
    assert first == second


def test_unknown_asset_is_not_synthesized_and_api_is_read_only():
    asset_id = uuid4()

    class UnknownService:
        def get_asset_attention_classification(self, requested_id):
            raise DiscoveryAssetNotFoundError(str(requested_id))

    app.dependency_overrides[get_intelligence_attention_classification_service] = lambda: (
        UnknownService()
    )
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/assets/{asset_id}/attention-classification")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_intelligence_attention_classification_service, None)


def test_api_returns_the_contract_without_persistence_fields():
    identity, candidate, evolution, values, _ = _active_fixture()
    service = _service(identity, candidate, evolution, values)
    app.dependency_overrides[get_intelligence_attention_classification_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/intelligence/assets/{identity.asset_id}/attention-classification"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["attention_class"] == "IMMEDIATE_REVIEW"
        assert payload["asset"]["market"] == "SH"
        assert "score" not in payload
        assert "rank" not in payload
    finally:
        app.dependency_overrides.pop(get_intelligence_attention_classification_service, None)
