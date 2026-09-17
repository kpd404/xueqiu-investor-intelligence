from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.dependencies import get_intelligence_narrative_service
from backend.app.main import app
from contracts import IntelligenceEventType, IntelligencePriorityReason
from intelligence.narrative.schemas import IntelligenceNarrativeView
from intelligence.narrative.service import IntelligenceNarrativeService
from intelligence.schemas.discovery import (
    DiscoveryActivitySummary,
    DiscoveryAssetIdentity,
    DiscoveryEventSummary,
    DiscoveryTimeline,
    IntelligenceDiscoveryCandidate,
    IntelligenceDiscoveryCandidateList,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)


def _candidate() -> IntelligenceDiscoveryCandidate:
    asset_id = uuid4()
    return IntelligenceDiscoveryCandidate(
        candidate_id=asset_id,
        asset=DiscoveryAssetIdentity(
            asset_id=asset_id,
            name="紫金矿业",
            market="SH",
            symbol="601899",
        ),
        activity_summary=DiscoveryActivitySummary(
            investor_count=5,
            signal_count=27,
            event_count=4,
            feed_count=4,
        ),
        event_summary=DiscoveryEventSummary(
            event_types=(
                IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
                IntelligenceEventType.INVESTOR_VIEW_CHANGE,
                IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
                IntelligenceEventType.CONSENSUS_STATE_CHANGE,
            ),
            priority_reasons=(
                IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION,
                IntelligencePriorityReason.THESIS_ACCELERATION,
                IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
                IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
            ),
        ),
        timeline=DiscoveryTimeline(
            first_observed_at=NOW,
            latest_observed_at=NOW + timedelta(days=1),
        ),
        discovery_reasons=[
            "MULTI_INVESTOR_ACTIVITY",
            "THESIS_ACTIVITY",
            "CROSS_INVESTOR_ACTIVITY",
            "CONSENSUS_ACTIVITY",
        ],
    )


class _StubDiscovery:
    def __init__(self, candidate=None):
        self.candidate = candidate
        self.candidate_calls = 0
        self.identity_calls = 0
        self.list_calls = 0

    def get_candidate_by_asset(self, asset_id, **kwargs):
        self.candidate_calls += 1
        return self.candidate

    def get_asset_identity(self, asset_id):
        self.identity_calls += 1
        return DiscoveryAssetIdentity(
            asset_id=asset_id,
            name="中国海洋石油",
            market="HK",
            symbol="00883",
        )

    def get_candidates(self, **kwargs):
        self.list_calls += 1
        items = (self.candidate,) if self.candidate is not None else ()
        return IntelligenceDiscoveryCandidateList(
            items=items,
            total=len(items),
            limit=kwargs.get("limit", 100),
            has_more=False,
        )


def test_narrative_contract_rejects_forbidden_fields() -> None:
    narrative = IntelligenceNarrativeService(_StubDiscovery()).get_candidate_narrative(_candidate())

    assert not {
        "score",
        "ranking",
        "rank",
        "weight",
        "confidence",
        "recommendation",
        "buy",
        "sell",
        "target_price",
        "prediction",
    }.intersection(narrative.model_dump())
    with pytest.raises(ValidationError):
        IntelligenceNarrativeView.model_validate({**narrative.model_dump(), "score": 1})


def test_narrative_is_deterministic_and_fact_only() -> None:
    service = IntelligenceNarrativeService(_StubDiscovery())
    first = service.get_candidate_narrative(_candidate())
    second = service.get_candidate_narrative(
        _candidate().model_copy(update={"candidate_id": first.asset.asset_id})
    )
    rendered = " ".join(
        [
            first.headline,
            first.summary,
            first.attention_summary,
            first.thesis_summary,
            first.cross_investor_summary,
            first.consensus_summary,
            first.evidence_summary,
            first.timeline_summary,
            *first.limitations,
        ]
    ).lower()

    assert first.asset.name == "紫金矿业"
    assert "5" in first.summary
    assert "27" in first.summary
    assert "CONSENSUS_STATE_CHANGE" in first.consensus_summary
    assert first.timeline_summary.startswith("Observed time range:")
    assert first.limitations
    assert first.model_dump(exclude={"asset"}) == second.model_dump(exclude={"asset"})
    assert all(term not in rendered for term in ("buy", "sell", "recommendation", "prediction"))


def test_batch_generation_reads_discovery_once() -> None:
    discovery = _StubDiscovery(_candidate())
    narratives = IntelligenceNarrativeService(discovery).batch_generate()

    assert len(narratives) == 1
    assert discovery.list_calls == 1
    assert discovery.candidate_calls == 0


def test_empty_narrative_preserves_limitation_without_inference() -> None:
    discovery = _StubDiscovery(None)
    service = IntelligenceNarrativeService(discovery)
    narrative = service.get_asset_narrative(uuid4())

    assert "No ACTIVE FeedItem" in narrative.summary
    assert any("absence inference" in item for item in narrative.limitations)
    assert discovery.candidate_calls == 1
    assert discovery.identity_calls == 1


def test_narrative_api_is_read_only_and_traceable_to_candidate() -> None:
    candidate = _candidate()
    service = IntelligenceNarrativeService(_StubDiscovery(candidate))

    app.dependency_overrides[get_intelligence_narrative_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/assets/{candidate.asset.asset_id}/narrative")
        assert response.status_code == 200
        payload = response.json()
        assert payload["asset"]["symbol"] == "601899"
        assert "5" in payload["summary"]
        assert "score" not in payload
    finally:
        app.dependency_overrides.pop(get_intelligence_narrative_service, None)
