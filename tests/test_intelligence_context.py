from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_intelligence_context_service
from backend.app.main import app
from contracts import (
    ConsensusEvidenceState,
    DirectionalAlignmentState,
    FeedItem,
    FeedState,
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
from intelligence.context.service import IntelligenceContextService
from intelligence.schemas.discovery import (
    DiscoveryActivitySummary,
    DiscoveryAssetIdentity,
    DiscoveryEventSummary,
    DiscoveryTimeline,
    IntelligenceDiscoveryCandidate,
    IntelligenceDiscoveryCandidateList,
)

NOW = datetime(2026, 9, 17, 12, tzinfo=UTC)


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
        self.intelligence_feed_items = _Reader(values["feeds"])
        self.intelligence_event_priorities = _Reader(values["priorities"])
        self.intelligence_events = _Reader(values["events"])
        self.intelligence_event_evidence = _Reader(values["links"])
        self.signals = _Reader(values["signals"])
        self.assets = _Reader(values["assets"])
        self.thesis_changes = _ThesisReader(values["thesis"])
        self.cross_investor_asset_snapshots = _CrossReader(values["snapshots"])
        self.cross_investor_asset_alignments = _CrossReader(values["alignments"])
        self.cross_investor_consensus_evidences = _CrossReader(values["consensus"])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


class _Discovery:
    def __init__(self, candidate):
        self.candidate = candidate

    def get_candidate_by_asset(self, asset_id):
        if self.candidate is None:
            return None
        return self.candidate if asset_id == self.candidate.asset.asset_id else None

    def get_asset_identity(self, asset_id):
        if self.candidate is not None:
            return self.candidate.asset
        return DiscoveryAssetIdentity(
            asset_id=asset_id,
            name="Empty Asset",
            market="HK",
            symbol="00883",
        )

    def get_candidates(self, **kwargs):
        return IntelligenceDiscoveryCandidateList(
            items=(self.candidate,),
            total=1,
            limit=kwargs.get("limit", 100),
            has_more=False,
        )


def _fixture():
    asset_id = uuid4()
    investor_one = uuid4()
    investor_two = uuid4()
    asset = SimpleNamespace(id=asset_id, name="紫金矿业", market="SH", symbol="601899")
    definitions = [
        (NOW - timedelta(days=7), IntelligenceEventType.ASSET_ACTIVITY_SPIKE, 2),
        (NOW - timedelta(days=5), IntelligenceEventType.INVESTOR_VIEW_CHANGE, 1),
        (NOW - timedelta(days=38), IntelligenceEventType.CROSS_INVESTOR_DISCOVERY, 1),
    ]
    events = []
    priorities = []
    feeds = []
    signals = []
    links = []
    reasons = {
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE: (
            IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION
        ),
        IntelligenceEventType.INVESTOR_VIEW_CHANGE: IntelligencePriorityReason.THESIS_ACCELERATION,
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY: (
            IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY
        ),
    }
    investors_by_event = ((investor_one, investor_two), (investor_one,), (investor_one,))
    for (observed_at, event_type, evidence_count), investors in zip(
        definitions, investors_by_event, strict=True
    ):
        event_id = uuid4()
        priority_id = uuid4()
        events.append(
            IntelligenceEventView(
                id=event_id,
                asset_id=asset_id,
                event_type=event_type,
                state=IntelligenceEventState.ACTIVE,
                first_observed_at=observed_at,
                last_observed_at=observed_at,
                metadata={},
            )
        )
        priorities.append(
            IntelligenceEventPriorityView(
                id=priority_id,
                event_id=event_id,
                priority_level=IntelligencePriorityLevel.MEDIUM,
                reason=reasons[event_type],
                evidence_count=evidence_count,
                created_at=observed_at,
            )
        )
        feeds.append(
            FeedItem(
                id=uuid4(),
                priority_id=priority_id,
                asset_id=asset_id,
                event_type=event_type,
                title="test",
                context={},
                reason=reasons[event_type],
                state=FeedState.ACTIVE,
                observed_at=observed_at,
                created_at=observed_at,
            )
        )
        for investor_id in investors:
            signal = SignalView(
                id=uuid4(),
                asset_id=asset_id,
                investor_id=investor_id,
                signal_type=(
                    SignalType.NEW_ATTENTION
                    if event_type != IntelligenceEventType.INVESTOR_VIEW_CHANGE
                    else SignalType.THESIS_CHANGE
                ),
                state=SignalState.ACTIVE,
                severity=SignalSeverity.LOW,
                source_type="test",
                source_id=uuid4(),
                created_at=observed_at,
                observed_at=observed_at,
                metadata={},
            )
            signals.append(signal)
            links.append(
                IntelligenceEventEvidenceView(id=uuid4(), event_id=event_id, signal_id=signal.id)
            )

    thesis = [
        ThesisChangeView(
            id=uuid4(),
            investor_id=investor_one,
            asset_id=asset_id,
            previous_opinion_id=uuid4(),
            current_opinion_id=uuid4(),
            previous_event_id=uuid4(),
            current_event_id=uuid4(),
            effective_time=NOW - timedelta(days=6),
            change_type=ThesisChangeType.THESIS_CHANGED,
            confidence=0.5,
            summary="test",
            evidence=(),
            opinion_analysis_version="test-analysis",
            comparison_version="test-comparison",
            calculated_at=NOW,
            input_identity="current-thesis",
        ),
        ThesisChangeView(
            id=uuid4(),
            investor_id=investor_one,
            asset_id=asset_id,
            previous_opinion_id=uuid4(),
            current_opinion_id=uuid4(),
            previous_event_id=uuid4(),
            current_event_id=uuid4(),
            effective_time=NOW - timedelta(days=38),
            change_type=ThesisChangeType.THESIS_REINFORCED,
            confidence=0.5,
            summary="test",
            evidence=(),
            opinion_analysis_version="test-analysis",
            comparison_version="test-comparison",
            calculated_at=NOW,
            input_identity="previous-thesis",
        ),
    ]
    historical_snapshot_id = uuid4()
    current_snapshot_id = uuid4()
    snapshots = [
        SimpleNamespace(
            id=historical_snapshot_id,
            asset_id=asset_id,
            window_end=NOW - timedelta(days=38),
            as_of=NOW - timedelta(days=38),
        ),
        SimpleNamespace(
            id=current_snapshot_id,
            asset_id=asset_id,
            window_end=NOW - timedelta(days=5),
            as_of=NOW - timedelta(days=5),
        ),
    ]
    alignments = [
        SimpleNamespace(
            id=uuid4(),
            source_snapshot_id=historical_snapshot_id,
            calculated_at=NOW - timedelta(days=38),
            directional_alignment_state=DirectionalAlignmentState.ALIGNED_BULLISH,
        ),
        SimpleNamespace(
            id=uuid4(),
            source_snapshot_id=current_snapshot_id,
            calculated_at=NOW - timedelta(days=5),
            directional_alignment_state=DirectionalAlignmentState.MIXED_DIRECTION,
        ),
    ]
    consensus = [
        SimpleNamespace(
            id=uuid4(),
            source_snapshot_id=historical_snapshot_id,
            calculated_at=NOW - timedelta(days=38),
            consensus_state=ConsensusEvidenceState.CONSENSUS_BULLISH,
        ),
        SimpleNamespace(
            id=uuid4(),
            source_snapshot_id=current_snapshot_id,
            calculated_at=NOW - timedelta(days=5),
            consensus_state=ConsensusEvidenceState.DIVERGENT,
        ),
    ]
    candidate = IntelligenceDiscoveryCandidate(
        candidate_id=asset_id,
        asset=DiscoveryAssetIdentity(
            asset_id=asset_id, name="紫金矿业", market="SH", symbol="601899"
        ),
        activity_summary=DiscoveryActivitySummary(
            investor_count=2, signal_count=4, event_count=3, feed_count=3
        ),
        event_summary=DiscoveryEventSummary(),
        timeline=DiscoveryTimeline(
            first_observed_at=NOW - timedelta(days=38), latest_observed_at=NOW - timedelta(days=5)
        ),
        discovery_reasons=[],
    )
    values = {
        "assets": (asset,),
        "feeds": tuple(feeds),
        "events": tuple(events),
        "priorities": tuple(priorities),
        "signals": tuple(signals),
        "links": tuple(links),
        "thesis": tuple(thesis),
        "snapshots": tuple(snapshots),
        "alignments": tuple(alignments),
        "consensus": tuple(consensus),
    }
    return candidate, values


def test_context_comparison_calculates_explicit_windows_and_changes() -> None:
    candidate, values = _fixture()
    service = IntelligenceContextService(
        _Discovery(candidate),
        lambda: _Uow(values),
        context_window_days=30,
        now_factory=lambda: NOW,
    )

    view = service.get_candidate_context(candidate, as_of=NOW)

    assert view.activity_context.current_signal_count == 3
    assert view.activity_context.previous_signal_count == 1
    assert "increased from 1 to 3" in view.activity_context.change_description
    assert view.investor_context.current_investor_count == 2
    assert view.investor_context.previous_investor_count == 1
    assert len(view.investor_context.new_investors) == 1
    assert view.attention_context.current_attention_count == 2
    assert view.attention_context.historical_attention_count == 1
    assert view.thesis_context.current_thesis_changes == 1
    assert view.thesis_context.historical_thesis_changes == 1
    assert view.thesis_context.direction_changes == ["THESIS_CHANGED"]
    assert view.cross_investor_context.current_state == (
        "alignment=MIXED_DIRECTION; consensus=DIVERGENT"
    )
    assert view.cross_investor_context.historical_state == (
        "alignment=ALIGNED_BULLISH; consensus=CONSENSUS_BULLISH"
    )
    assert view.timeline_context.previous_window_end == NOW - timedelta(days=30)


def test_context_contract_forbids_ranking_fields() -> None:
    candidate, values = _fixture()
    view = IntelligenceContextService(
        lambda: _Discovery(candidate), lambda: _Uow(values)
    ).get_candidate_context(candidate, as_of=NOW)

    assert not {
        "score",
        "ranking",
        "rank",
        "weight",
        "hotness",
        "importance",
        "confidence",
        "recommendation",
        "buy",
        "sell",
        "target_price",
        "prediction",
    }.intersection(view.model_dump())


def test_context_empty_history_preserves_limitation() -> None:
    candidate, values = _fixture()
    values["feeds"] = ()
    values["events"] = ()
    values["priorities"] = ()
    values["signals"] = ()
    values["links"] = ()
    service = IntelligenceContextService(
        _Discovery(None),
        lambda: _Uow(values),
        now_factory=lambda: NOW,
    )

    view = service.get_asset_context(candidate.asset.asset_id, as_of=NOW)

    assert view.activity_context.current_signal_count == 0
    assert view.timeline_context.first_observed_at is None
    assert any("insufficient" in item.lower() for item in view.limitations)


def test_context_api_is_read_only_projection() -> None:
    candidate, values = _fixture()
    service = IntelligenceContextService(
        _Discovery(candidate), lambda: _Uow(values), now_factory=lambda: NOW
    )
    app.dependency_overrides[get_intelligence_context_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/assets/{candidate.asset.asset_id}/context")
        assert response.status_code == 200
        payload = response.json()
        assert payload["asset"]["symbol"] == "601899"
        assert "score" not in payload
    finally:
        app.dependency_overrides.pop(get_intelligence_context_service, None)
