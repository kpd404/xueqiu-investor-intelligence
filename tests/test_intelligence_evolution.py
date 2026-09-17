from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_intelligence_evolution_service
from backend.app.main import app
from contracts import (
    DirectionalAlignmentState,
    IntelligenceEventPriorityView,
    IntelligenceEventType,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
    SignalSeverity,
    SignalState,
    SignalType,
    SignalView,
    ThesisChangeType,
)
from intelligence.context.schemas import (
    ActivityContext,
    AttentionContext,
    ContextAssetIdentity,
    CrossInvestorContext,
    IntelligenceContextView,
    InvestorContext,
    ThesisContext,
    TimelineContext,
)
from intelligence.evolution.schemas import (
    EvolutionStepType,
)
from intelligence.evolution.service import IntelligenceEvolutionService
from intelligence.patterns.schemas import (
    IntelligencePatternEvidence,
    IntelligencePatternType,
    IntelligencePatternView,
    PatternAssetIdentity,
    PatternDataQuality,
    PatternTimeline,
)
from intelligence.schemas.discovery import (
    DiscoveryActivitySummary,
    DiscoveryAssetIdentity,
    DiscoveryEventSummary,
    DiscoveryTimeline,
    IntelligenceDiscoveryCandidate,
    IntelligenceDiscoveryCandidateList,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)


class _Reader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _ThesisReader:
    def __init__(self, values):
        self.values = tuple(values)

    def list_effective_by_asset(self, asset_id, policy, comparison_version, *, as_of=None):
        return list(self.values)


class _CrossReader:
    def __init__(self, values):
        self.values = tuple(values)

    def list_by_asset(self, asset_id):
        return list(self.values)


class _Uow:
    def __init__(self, values):
        self.intelligence_feed_items = _Reader(values.get("feeds", ()))
        self.intelligence_event_priorities = _Reader(values.get("priorities", ()))
        self.intelligence_events = _Reader(values.get("events", ()))
        self.intelligence_event_evidence = _Reader(values.get("links", ()))
        self.signals = _Reader(values.get("signals", ()))
        self.thesis_changes = _ThesisReader(values.get("thesis", ()))
        self.cross_investor_asset_snapshots = _CrossReader(values.get("snapshots", ()))
        self.cross_investor_asset_alignments = _CrossReader(values.get("alignments", ()))
        self.cross_investor_consensus_evidences = _CrossReader(values.get("consensus", ()))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def _candidate(asset_id: object) -> IntelligenceDiscoveryCandidate:
    return IntelligenceDiscoveryCandidate(
        candidate_id=asset_id,
        asset=DiscoveryAssetIdentity(
            asset_id=asset_id, name="紫金矿业", market="SH", symbol="601899"
        ),
        activity_summary=DiscoveryActivitySummary(
            investor_count=2, signal_count=2, event_count=1, feed_count=1
        ),
        event_summary=DiscoveryEventSummary(),
        timeline=DiscoveryTimeline(first_observed_at=NOW, latest_observed_at=NOW),
        discovery_reasons=[],
    )


def _context(candidate: IntelligenceDiscoveryCandidate) -> IntelligenceContextView:
    return IntelligenceContextView(
        asset=ContextAssetIdentity(**candidate.asset.model_dump()),
        activity_context=ActivityContext(
            current_signal_count=2,
            previous_signal_count=1,
            change_description="Observed signal activity increased.",
        ),
        investor_context=InvestorContext(
            current_investor_count=2,
            previous_investor_count=1,
            new_investors=[uuid4()],
            returning_investors=[uuid4()],
        ),
        attention_context=AttentionContext(
            current_attention_count=2,
            historical_attention_count=1,
            change_description="Observed attention evidence increased.",
        ),
        thesis_context=ThesisContext(
            current_thesis_changes=1,
            historical_thesis_changes=0,
            direction_changes=["THESIS_CHANGED"],
        ),
        cross_investor_context=CrossInvestorContext(
            current_state="alignment=MIXED_DIRECTION; consensus=DIVERGENT",
            historical_state="alignment=ALIGNED_BULLISH; consensus=CONSENSUS_BULLISH",
        ),
        timeline_context=TimelineContext(
            first_observed_at=NOW - timedelta(days=10),
            latest_observed_at=NOW,
            current_window_start=NOW - timedelta(days=30),
            current_window_end=NOW,
            previous_window_start=NOW - timedelta(days=60),
            previous_window_end=NOW - timedelta(days=30),
        ),
        limitations=[],
    )


class _Discovery:
    def __init__(self, candidate):
        self.candidate = candidate

    def get_candidate_by_asset(self, asset_id):
        return (
            self.candidate if self.candidate and asset_id == self.candidate.asset.asset_id else None
        )

    def get_asset_identity(self, asset_id):
        if self.candidate is not None:
            return self.candidate.asset
        return DiscoveryAssetIdentity(
            asset_id=asset_id, name="Empty Asset", market="SH", symbol="601899"
        )

    def get_candidates(self, **kwargs):
        items = (self.candidate,) if self.candidate else ()
        return IntelligenceDiscoveryCandidateList(
            items=items, total=len(items), limit=kwargs.get("limit", 100), has_more=False
        )


class _Context:
    def __init__(self, context):
        self.context = context

    def get_asset_context(self, asset_id):
        return self.context

    def get_candidate_context(self, candidate):
        return self.context

    def batch_get_context(self, candidates=None, **kwargs):
        return (self.context,)


class _Pattern:
    def __init__(self, context):
        self.view = IntelligencePatternView(
            asset=PatternAssetIdentity(**context.asset.model_dump()),
            patterns=[
                IntelligencePatternEvidence(
                    type=IntelligencePatternType.MULTI_INVESTOR_EXPANSION,
                    description="test",
                    evidence="Observed activity from 2 Investors.",
                )
            ],
            data_quality=[
                PatternDataQuality(
                    type="INSUFFICIENT_HISTORY",
                    description="History is limited.",
                    evidence="Previous window is sparse.",
                )
            ],
            timeline=PatternTimeline(
                first_observed_at=context.timeline_context.first_observed_at,
                latest_observed_at=context.timeline_context.latest_observed_at,
            ),
            limitations=[],
        )

    def get_context_patterns(self, context):
        return self.view


def _values(asset_id):
    investor_id = uuid4()
    signal = SignalView(
        id=uuid4(),
        asset_id=asset_id,
        investor_id=investor_id,
        signal_type=SignalType.NEW_ATTENTION,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.LOW,
        source_type="AttentionOccurrence",
        source_id=uuid4(),
        created_at=NOW,
        observed_at=NOW - timedelta(days=10),
        metadata={},
    )
    event_id = uuid4()
    priority_id = uuid4()
    return {
        "signals": (signal,),
        "events": (
            SimpleNamespace(
                id=event_id,
                asset_id=asset_id,
                event_type=IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
                last_observed_at=NOW - timedelta(days=8),
            ),
        ),
        "priorities": (
            IntelligenceEventPriorityView(
                id=priority_id,
                event_id=event_id,
                priority_level=IntelligencePriorityLevel.HIGH,
                reason=IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION,
                evidence_count=1,
                created_at=NOW,
            ),
        ),
        "links": (),
        "thesis": (
            SimpleNamespace(
                id=uuid4(),
                investor_id=investor_id,
                current_event_id=uuid4(),
                effective_time=NOW - timedelta(days=7),
                change_type=ThesisChangeType.THESIS_CHANGED,
            ),
        ),
        "snapshots": (
            SimpleNamespace(
                id=uuid4(), window_end=NOW - timedelta(days=9), as_of=NOW - timedelta(days=9)
            ),
        ),
        "alignments": (),
        "consensus": (),
    }


def test_evolution_orders_fact_time_and_suppresses_duplicate_sources() -> None:
    asset_id = uuid4()
    candidate = _candidate(asset_id)
    context = _context(candidate)
    values = _values(asset_id)
    # The same alignment source is deliberately repeated; canonical source identity must dedupe it.
    snapshot_id = values["snapshots"][0].id
    alignment = SimpleNamespace(
        id=uuid4(),
        source_snapshot_id=snapshot_id,
        calculated_at=NOW,
        directional_alignment_state=DirectionalAlignmentState.MIXED_DIRECTION,
    )
    values["alignments"] = (alignment, alignment)
    service = IntelligenceEvolutionService(
        _Discovery(candidate),
        _Context(context),
        _Pattern(context),
        lambda: _Uow(values),
    )

    view = service.get_candidate_evolution(candidate)

    assert view.timeline
    assert [step.observed_at for step in view.timeline] == sorted(
        step.observed_at for step in view.timeline
    )
    assert (
        sum(step.step_type == EvolutionStepType.CROSS_INVESTOR_STATE for step in view.timeline) == 1
    )
    assert any(
        step.step_type == EvolutionStepType.INVESTOR_ATTENTION_ADDED for step in view.timeline
    )
    assert any(step.step_type == EvolutionStepType.THESIS_ACTIVITY for step in view.timeline)
    assert "MULTI_INVESTOR_EXPANSION" in view.current_state.patterns
    assert "INSUFFICIENT_HISTORY" in view.limitations[0] or any(
        "History" in item for item in view.limitations
    )


def test_evolution_contract_has_no_ranking_fields_and_empty_history_is_read_only() -> None:
    asset_id = uuid4()
    candidate = _candidate(asset_id)
    context = _context(candidate)
    service = IntelligenceEvolutionService(
        _Discovery(None),
        _Context(context),
        _Pattern(context),
        lambda: _Uow({}),
    )

    view = service.get_asset_evolution(asset_id)
    assert view.timeline == []
    assert not {
        "score",
        "rank",
        "ranking",
        "weight",
        "hotness",
        "importance",
        "recommendation",
        "prediction",
        "target_price",
        "confidence",
    }.intersection(view.model_dump())


def test_evolution_api_returns_traceable_projection() -> None:
    asset_id = uuid4()
    candidate = _candidate(asset_id)
    context = _context(candidate)
    service = IntelligenceEvolutionService(
        _Discovery(candidate),
        _Context(context),
        _Pattern(context),
        lambda: _Uow(_values(asset_id)),
    )
    app.dependency_overrides[get_intelligence_evolution_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/assets/{asset_id}/evolution")
        assert response.status_code == 200
        assert response.json()["asset"]["symbol"] == "601899"
    finally:
        app.dependency_overrides.pop(get_intelligence_evolution_service, None)
