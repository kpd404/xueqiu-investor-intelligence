from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_intelligence_discovery_service
from backend.app.main import app
from contracts import (
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
)
from intelligence.discovery.service import IntelligenceDiscoveryService

NOW = datetime(2026, 9, 17, tzinfo=UTC)


class _Reader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _Uow:
    def __init__(self, values):
        self.intelligence_feed_items = _Reader(values["feeds"])
        self.intelligence_event_priorities = _Reader(values["priorities"])
        self.intelligence_events = _Reader(values["events"])
        self.intelligence_event_evidence = _Reader(values["links"])
        self.signals = _Reader(values["signals"])
        self.assets = _Reader(values["assets"])
        self.commit_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.commit_called = True


def _make_dataset():
    asset_one = uuid4()
    asset_two = uuid4()
    investor_one = uuid4()
    investor_two = uuid4()
    assets = (
        SimpleNamespace(id=asset_one, name="资产一", market="SH", symbol="600001"),
        SimpleNamespace(id=asset_two, name="资产二", market="HK", symbol="00001"),
    )
    events = []
    priorities = []
    feeds = []
    links = []
    signals = []
    event_types = (
        IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
        IntelligenceEventType.INVESTOR_VIEW_CHANGE,
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        IntelligenceEventType.CONSENSUS_STATE_CHANGE,
    )
    priority_reasons = (
        IntelligencePriorityReason.MULTI_INVESTOR_ATTENTION,
        IntelligencePriorityReason.THESIS_ACCELERATION,
        IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
        IntelligencePriorityReason.CONSENSUS_STATE_CHANGE,
    )
    for index, (event_type, reason) in enumerate(zip(event_types, priority_reasons, strict=True)):
        event_id = uuid4()
        priority_id = uuid4()
        feed_id = uuid4()
        signal_id = uuid4()
        observed_at = NOW + timedelta(minutes=index)
        investor_id = investor_two if index == 0 else investor_one
        events.append(
            IntelligenceEventView(
                id=event_id,
                asset_id=asset_one,
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
                reason=reason,
                evidence_count=1,
                created_at=observed_at,
            )
        )
        signals.append(
            SignalView(
                id=signal_id,
                asset_id=asset_one,
                investor_id=investor_id,
                signal_type=SignalType.THESIS_CHANGE,
                state=SignalState.ACTIVE,
                severity=SignalSeverity.MEDIUM,
                source_type="test",
                source_id=uuid4(),
                created_at=observed_at,
                observed_at=observed_at,
                metadata={},
            )
        )
        links.append(
            IntelligenceEventEvidenceView(id=uuid4(), event_id=event_id, signal_id=signal_id)
        )
        feeds.append(
            FeedItem(
                id=feed_id,
                priority_id=priority_id,
                asset_id=asset_one,
                event_type=event_type,
                title="test",
                context={},
                reason=reason,
                state=FeedState.ACTIVE,
                observed_at=observed_at,
                created_at=observed_at,
            )
        )

    event_id = uuid4()
    priority_id = uuid4()
    observed_at = NOW - timedelta(minutes=1)
    signal_id = uuid4()
    events.append(
        IntelligenceEventView(
            id=event_id,
            asset_id=asset_two,
            event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
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
            priority_level=IntelligencePriorityLevel.LOW,
            reason=IntelligencePriorityReason.THESIS_ACCELERATION,
            evidence_count=1,
            created_at=observed_at,
        )
    )
    signals.append(
        SignalView(
            id=signal_id,
            asset_id=asset_two,
            investor_id=investor_one,
            signal_type=SignalType.THESIS_CHANGE,
            state=SignalState.ACTIVE,
            severity=SignalSeverity.LOW,
            source_type="test",
            source_id=uuid4(),
            created_at=observed_at,
            observed_at=observed_at,
            metadata={},
        )
    )
    links.append(IntelligenceEventEvidenceView(id=uuid4(), event_id=event_id, signal_id=signal_id))
    feeds.append(
        FeedItem(
            id=uuid4(),
            priority_id=priority_id,
            asset_id=asset_two,
            event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
            title="test",
            context={},
            reason=IntelligencePriorityReason.THESIS_ACCELERATION,
            state=FeedState.ACTIVE,
            observed_at=observed_at,
            created_at=observed_at,
        )
    )
    return {
        "assets": assets,
        "events": tuple(events),
        "priorities": tuple(priorities),
        "feeds": tuple(feeds),
        "links": tuple(links),
        "signals": tuple(signals),
        "asset_one": asset_one,
        "asset_two": asset_two,
    }


def test_discovery_contract_has_activity_and_evidence_without_ranking_fields() -> None:
    values = _make_dataset()
    uow = _Uow(values)
    result = IntelligenceDiscoveryService(lambda: uow).get_candidates(limit=10)

    assert result.total == 2
    candidate = result.items[0]
    assert candidate.candidate_id == candidate.asset.asset_id
    assert candidate.activity_summary.model_dump() == {
        "investor_count": 2,
        "signal_count": 4,
        "event_count": 4,
        "feed_count": 4,
    }
    assert candidate.event_summary.event_types == tuple(
        sorted(
            (
                IntelligenceEventType.ASSET_ACTIVITY_SPIKE,
                IntelligenceEventType.CONSENSUS_STATE_CHANGE,
                IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
                IntelligenceEventType.INVESTOR_VIEW_CHANGE,
            ),
            key=lambda value: value.value,
        )
    )
    assert set(candidate.discovery_reasons) == {
        "MULTI_INVESTOR_ACTIVITY",
        "THESIS_ACTIVITY",
        "CROSS_INVESTOR_ACTIVITY",
        "CONSENSUS_ACTIVITY",
    }
    assert candidate.timeline.first_observed_at == NOW
    assert candidate.timeline.latest_observed_at == NOW + timedelta(minutes=3)
    assert not {"score", "rank", "weight", "ranking", "recommendation"}.intersection(
        candidate.model_dump()
    )


def test_discovery_filters_by_asset_and_event_type() -> None:
    values = _make_dataset()
    service = IntelligenceDiscoveryService(lambda: _Uow(values))

    asset_result = service.get_candidates(limit=10, asset_id=values["asset_two"])
    event_result = service.get_candidates(
        limit=10,
        asset_id=values["asset_one"],
        event_type=IntelligenceEventType.CONSENSUS_STATE_CHANGE,
    )

    assert asset_result.total == 1
    assert asset_result.items[0].asset.asset_id == values["asset_two"]
    assert event_result.total == 1
    assert event_result.items[0].activity_summary.event_count == 1
    assert event_result.items[0].discovery_reasons == ["CONSENSUS_ACTIVITY"]


def test_new_feed_items_are_not_implicitly_active() -> None:
    values = _make_dataset()
    values["feeds"] = tuple(
        feed.model_copy(update={"state": FeedState.NEW}) for feed in values["feeds"]
    )

    result = IntelligenceDiscoveryService(lambda: _Uow(values)).get_candidates(limit=10)

    assert result.total == 0
    assert result.items == ()


def test_discovery_traceability_rejects_missing_signal() -> None:
    values = _make_dataset()
    values["signals"] = values["signals"][:-1]

    with pytest.raises(ValueError, match="Signal not found"):
        IntelligenceDiscoveryService(lambda: _Uow(values)).get_candidates(limit=10)


def test_discovery_is_read_only_and_asset_not_found_is_explicit() -> None:
    values = _make_dataset()
    uow = _Uow(values)
    service = IntelligenceDiscoveryService(lambda: uow)

    with pytest.raises(LookupError):
        service.get_candidate_by_asset(uuid4())
    assert uow.commit_called is False


def test_discovery_api_exposes_filterable_read_only_projection() -> None:
    values = _make_dataset()

    class Stub:
        def get_candidates(self, **kwargs):
            return IntelligenceDiscoveryService(lambda: _Uow(values)).get_candidates(**kwargs)

    app.dependency_overrides[get_intelligence_discovery_service] = lambda: Stub()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/intelligence/discovery",
                params={
                    "limit": 10,
                    "asset_id": str(values["asset_two"]),
                    "event_type": "INVESTOR_VIEW_CHANGE",
                },
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["asset"]["symbol"] == "00001"
        assert "score" not in payload["items"][0]
    finally:
        app.dependency_overrides.pop(get_intelligence_discovery_service, None)
