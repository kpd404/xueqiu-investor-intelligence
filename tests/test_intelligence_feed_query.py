from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_intelligence_feed_query_service
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
from intelligence.feed.query import IntelligenceFeedQueryService
from intelligence.schemas.feed import (
    FeedAssetIdentity,
    IntelligenceFeedListResponse,
    IntelligenceFeedResponse,
)

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def _fixtures():
    asset_id = uuid4()
    investor_id = uuid4()
    signal_id = uuid4()
    event_id = uuid4()
    priority_id = uuid4()
    feed_id = uuid4()
    return {
        "asset_id": asset_id,
        "investor_id": investor_id,
        "signal": SignalView(
            id=signal_id,
            asset_id=asset_id,
            investor_id=investor_id,
            signal_type=SignalType.THESIS_CHANGE,
            state=SignalState.ACTIVE,
            severity=SignalSeverity.MEDIUM,
            source_type="ThesisChange",
            source_id=uuid4(),
            created_at=NOW,
            observed_at=NOW,
            metadata={},
        ),
        "event": IntelligenceEventView(
            id=event_id,
            asset_id=asset_id,
            event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
            state=IntelligenceEventState.ACTIVE,
            first_observed_at=NOW,
            last_observed_at=NOW,
            metadata={"signal_count": 1},
        ),
        "priority": IntelligenceEventPriorityView(
            id=priority_id,
            event_id=event_id,
            priority_level=IntelligencePriorityLevel.MEDIUM,
            reason=IntelligencePriorityReason.THESIS_ACCELERATION,
            evidence_count=1,
            created_at=NOW,
        ),
        "link": IntelligenceEventEvidenceView(
            id=uuid4(),
            event_id=event_id,
            signal_id=signal_id,
        ),
        "feed": FeedItem(
            id=feed_id,
            priority_id=priority_id,
            asset_id=asset_id,
            event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
            title="Multiple thesis changes were observed",
            context={"investor_count": 1, "signal_count": 1, "source_count": 1},
            reason=IntelligencePriorityReason.THESIS_ACCELERATION,
            state=FeedState.NEW,
            observed_at=NOW,
            created_at=NOW,
        ),
    }


class _Reader:
    def __init__(self, values):
        self.values = tuple(values)

    def list(self):
        return self.values


class _Uow:
    def __init__(self, values):
        self.intelligence_feed_items = _Reader((values["feed"],))
        self.intelligence_event_priorities = _Reader((values["priority"],))
        self.intelligence_events = _Reader((values["event"],))
        self.intelligence_event_evidence = _Reader((values["link"],))
        self.signals = _Reader((values["signal"],))
        self.assets = _Reader(
            (
                type(
                    "Asset",
                    (),
                    {
                        "id": values["asset_id"],
                        "name": "测试资产",
                        "market": "SH",
                        "symbol": "600000",
                    },
                )(),
            )
        )
        self.investors = _Reader(
            (type("Investor", (), {"id": values["investor_id"], "name": "Investor A"})(),)
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def test_feed_query_filters_and_descending_projection() -> None:
    values = _fixtures()
    service = IntelligenceFeedQueryService(lambda: _Uow(values))

    result = service.list_feed(
        limit=10,
        investor_id=values["investor_id"],
        priority_level=IntelligencePriorityLevel.MEDIUM,
        event_type=IntelligenceEventType.INVESTOR_VIEW_CHANGE,
    )

    assert result.total == 1
    assert result.items[0].priority_id == values["priority"].id
    assert result.items[0].asset.market == "SH"
    assert result.items[0].context["signal_count"] == 1
    assert result.items[0].investors[0].name == "Investor A"


def test_feed_query_supports_recent_state_filter() -> None:
    values = _fixtures()
    service = IntelligenceFeedQueryService(lambda: _Uow(values))

    result = service.list_feed(
        limit=10,
        state=FeedState.NEW,
        since=NOW - timedelta(minutes=1),
    )

    assert result.total == 1


def test_feed_api_exposes_general_asset_and_investor_paths() -> None:
    item = IntelligenceFeedResponse(
        id=uuid4(),
        priority_id=uuid4(),
        asset=FeedAssetIdentity(asset_id=uuid4(), name="测试资产", market="SH", symbol="600000"),
        event_type=IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
        priority_level=IntelligencePriorityLevel.LOW,
        reason=IntelligencePriorityReason.CROSS_INVESTOR_DISCOVERY,
        title="Cross-investor attention was observed",
        context={"investor_count": 2, "signal_count": 2, "source_count": 2},
        state=FeedState.NEW,
        observed_at=NOW,
        created_at=NOW,
    )
    page = IntelligenceFeedListResponse(items=(item,), total=1, limit=50, has_more=False)

    class Stub:
        def list_feed(self, **kwargs):
            return page

        def get_asset_feed(self, *args, **kwargs):
            return page

        def get_investor_feed(self, *args, **kwargs):
            return page

    app.dependency_overrides[get_intelligence_feed_query_service] = lambda: Stub()
    try:
        with TestClient(app) as client:
            general = client.get("/api/intelligence/feed?limit=10")
            asset = client.get(f"/api/intelligence/assets/{item.asset.asset_id}/feed")
            investor = client.get(f"/api/intelligence/investors/{uuid4()}/feed")
        assert general.status_code == 200
        assert asset.status_code == 200
        assert investor.status_code == 200
        assert general.json()["items"][0]["priority_level"] == "LOW"
    finally:
        app.dependency_overrides.pop(get_intelligence_feed_query_service, None)
