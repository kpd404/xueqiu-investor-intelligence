from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_combined_asset_intelligence_service
from backend.app.main import app
from contracts import (
    AttentionEvidenceType,
    CombinedAssetAttentionSummary,
    CombinedAssetDataQuality,
    CombinedAssetIntelligenceView,
    CombinedAssetInvestorView,
    CombinedAssetTimelineEvent,
    CombinedAssetTimelineEventType,
    CombinedAttentionOpinionRelation,
    ObservedAttentionCompleteness,
    ObservedAttentionObservation,
    ObservedAttentionSequence,
    OpinionDirection,
)
from database.unit_of_work import SqlAlchemyObservedAttentionUnitOfWork
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetNotFoundError,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=10)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _investor_view(
    investor_id: int,
    name: str,
    *,
    attention_count: int = 0,
    opinion_count: int = 0,
    missing: int = 0,
    relation: CombinedAttentionOpinionRelation = (
        CombinedAttentionOpinionRelation.ATTENTION_WITHOUT_OPINION
    ),
) -> CombinedAssetInvestorView:
    return CombinedAssetInvestorView(
        investor_id=_uuid(investor_id),
        investor_name=name,
        first_attention_time=START if attention_count else None,
        latest_attention_time=START + timedelta(days=1) if attention_count else None,
        attention_occurrence_count=attention_count,
        attention_evidence_types=(
            (AttentionEvidenceType.EXPLICIT_MENTION,) if attention_count else ()
        ),
        first_attention_raw_event_id=_uuid(investor_id + 1000) if attention_count else None,
        opinion_count=opinion_count,
        first_opinion_time=START if opinion_count else None,
        latest_opinion_time=START + timedelta(days=2) if opinion_count else None,
        latest_observed_direction=OpinionDirection.BULLISH if opinion_count else None,
        latest_observed_confidence=0.8 if opinion_count else None,
        thesis_change_count=max(0, opinion_count - missing),
        latest_thesis_change_type=None,
        reversal_count=0,
        changed_count=0,
        extended_count=0,
        missing_thesis_comparison_count=missing,
        attention_opinion_relation=relation,
    )


def _attention_observation(
    investor_id: int,
    name: str,
    occurrence_id: int,
    raw_event_id: int,
    published_time: datetime,
    *,
    lag_days: float | None = None,
) -> ObservedAttentionObservation:
    return ObservedAttentionObservation(
        investor_id=_uuid(investor_id),
        investor_name=name,
        attention_occurrence_id=_uuid(occurrence_id),
        raw_event_id=_uuid(raw_event_id),
        published_time=published_time,
        evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
        lag_seconds=lag_days * 86400 if lag_days is not None else None,
        lag_hours=lag_days * 24 if lag_days is not None else None,
        lag_days=lag_days,
    )


def _attention_event(
    investor_id: int,
    name: str,
    occurrence_id: int,
    raw_event_id: int,
    published_time: datetime,
) -> CombinedAssetTimelineEvent:
    return CombinedAssetTimelineEvent(
        published_time=published_time,
        investor_id=_uuid(investor_id),
        investor_name=name,
        event_type=CombinedAssetTimelineEventType.ATTENTION_FIRST_OBSERVED,
        evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
        attention_occurrence_id=_uuid(occurrence_id),
        raw_event_id=_uuid(raw_event_id),
    )


def _view(
    asset_id: int,
    name: str,
    market: str,
    symbol: str,
    investors: tuple[CombinedAssetInvestorView, ...],
    *,
    sequence: ObservedAttentionSequence | None = None,
    attention_count: int = 0,
    attention_occurrences: int = 0,
    missing: int = 0,
    events: tuple[CombinedAssetTimelineEvent, ...] = (),
) -> CombinedAssetIntelligenceView:
    earliest = events[0].published_time if events else None
    latest = events[-1].published_time if events else None
    return CombinedAssetIntelligenceView(
        asset_id=_uuid(asset_id),
        asset_name=name,
        market=market,
        symbol=symbol,
        window_start=START,
        window_end=END,
        completeness=ObservedAttentionCompleteness.UNKNOWN,
        attention_summary=CombinedAssetAttentionSummary(
            attention_investor_count=attention_count,
            attention_occurrence_count=attention_occurrences,
            earliest_observed_time=earliest,
            earliest_observed_investor_id=(
                investors[0].investor_id if investors and attention_count else None
            ),
            earliest_observed_investor_name=(
                investors[0].investor_name if investors and attention_count else None
            ),
            observed_span_days=(
                (latest - earliest).total_seconds() / 86400
                if earliest is not None and latest is not None
                else None
            ),
            observed_span_hours=(
                (latest - earliest).total_seconds() / 3600
                if earliest is not None and latest is not None
                else None
            ),
            observed_span_seconds=(
                (latest - earliest).total_seconds()
                if earliest is not None and latest is not None
                else None
            ),
        ),
        observed_attention_sequence=sequence,
        investor_views=investors,
        data_quality=CombinedAssetDataQuality(
            missing_thesis_comparison_count=missing,
            cross_investor_evidence_available=False,
            unresolved_semantic_limitations=(
                "HISTORICAL_COMPLETENESS_UNKNOWN",
                "ABSENCE_INFERENCE_UNSUPPORTED",
                *(("MISSING_THESIS_COMPARISON",) if missing else ()),
                "CROSS_INVESTOR_LINEAGE_UNAVAILABLE",
            ),
        ),
        event_timeline=events,
    )


def _fixture_views() -> tuple[CombinedAssetIntelligenceView, ...]:
    sequence_names = (
        ("笨笨的投资者2", 11),
        ("沈阳城", 12),
        ("Captain-Nemo船长", 13),
        ("看好股市的新人", 14),
    )
    observations = tuple(
        _attention_observation(
            investor_id,
            name,
            100 + index,
            200 + index,
            START + timedelta(days=index * 2),
            lag_days=index * 2 if index else None,
        )
        for index, (name, investor_id) in enumerate(sequence_names)
    )
    sequence = ObservedAttentionSequence(
        asset_id=_uuid(1),
        asset_name="招商轮船",
        market="SH",
        symbol="601872",
        window_start=START,
        window_end=END,
        investor_count=4,
        occurrence_count=5,
        first_observed=observations[0],
        later_observations=observations[1:],
    )
    招商 = _view(
        1,
        "招商轮船",
        "SH",
        "601872",
        tuple(
            _investor_view(investor_id, name, attention_count=1)
            for name, investor_id in sequence_names
        ),
        sequence=sequence,
        attention_count=4,
        attention_occurrences=5,
        events=tuple(
            _attention_event(
                investor_id,
                name,
                100 + index,
                200 + index,
                START + timedelta(days=index * 2),
            )
            for index, (name, investor_id) in enumerate(sequence_names)
        ),
    )
    山东_hk = _view(
        2,
        "山东黄金",
        "HK",
        "01787",
        (
            _investor_view(21, "人生是历练", attention_count=2, opinion_count=2),
            _investor_view(22, "沈阳城", attention_count=2, opinion_count=1),
        ),
        attention_count=2,
        attention_occurrences=4,
    )
    山东_sh = _view(
        3,
        "山东黄金",
        "SH",
        "600547",
        (_investor_view(23, "人生是历练", attention_count=1, opinion_count=1),),
        attention_count=1,
        attention_occurrences=1,
    )
    大唐 = _view(
        4,
        "大唐发电",
        "HK",
        "00991",
        (
            _investor_view(
                24,
                "爱投资的小人书",
                attention_count=17,
                opinion_count=14,
                missing=1,
                relation=CombinedAttentionOpinionRelation.OPINION_AT_FIRST_ATTENTION,
            ),
        ),
        attention_count=1,
        attention_occurrences=17,
        missing=1,
    )
    return (山东_sh, 大唐, 招商, 山东_hk)


class _StubCombinedService:
    def __init__(self, views: tuple[CombinedAssetIntelligenceView, ...]):
        self.views = views
        self.calls: list[tuple[str, object]] = []
        self.write_calls = 0

    def list_asset_views(
        self,
        window_start=None,
        window_end=None,
        *,
        min_attention_investors=None,
        min_opinion_investors=None,
    ):
        self.calls.append(
            (
                "list",
                (window_start, window_end, min_attention_investors, min_opinion_investors),
            )
        )
        if window_start is not None and window_end is not None and window_start > window_end:
            raise ValueError("window_start must not be after window_end")
        return tuple(
            view
            for view in self.views
            if (
                min_attention_investors is None
                or view.attention_summary.attention_investor_count >= min_attention_investors
            )
            and (
                min_opinion_investors is None
                or sum(item.opinion_count > 0 for item in view.investor_views)
                >= min_opinion_investors
            )
        )

    def get_asset_view(self, asset_id, window_start=None, window_end=None):
        self.calls.append(("detail", (asset_id, window_start, window_end)))
        if window_start is not None and window_end is not None and window_start > window_end:
            raise ValueError("window_start must not be after window_end")
        known = next((view for view in self.views if view.asset_id == asset_id), None)
        if known is None:
            raise CombinedAssetNotFoundError(f"asset not found: {asset_id}")
        if window_start is not None and window_start.year == 2000:
            return None
        return known


@pytest.fixture
def api_service():
    service = _StubCombinedService(_fixture_views())
    app.dependency_overrides[get_combined_asset_intelligence_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_combined_asset_intelligence_service, None)


@pytest.fixture
def api_client(api_service):
    with TestClient(app) as client:
        yield client


def test_openapi_and_docs_expose_the_three_intelligence_paths(api_client: TestClient) -> None:
    assert api_client.get("/docs").status_code == 200
    openapi = api_client.get("/openapi.json").json()
    paths = openapi["paths"]
    assert "/api/v1/intelligence/assets" in paths
    assert "/api/v1/intelligence/assets/{asset_id}" in paths
    assert "/api/v1/intelligence/assets/{asset_id}/timeline" in paths
    description = openapi["info"]["description"]
    assert "UNKNOWN" in description
    assert "causality" in description
    assert "absence" in description


def test_asset_list_is_lightweight_stable_and_paginated(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/intelligence/assets?limit=2&offset=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert payload["has_more"] is True
    assert len(payload["items"]) == 2
    assert all("event_timeline" not in item for item in payload["items"])
    labels = [(item["asset_name"], item["market"], item["symbol"]) for item in payload["items"]]
    assert labels == sorted(labels)


def test_asset_list_filters_are_query_filters(api_client: TestClient, api_service) -> None:
    response = api_client.get(
        "/api/v1/intelligence/assets?market=hk&min_attention_investors=2&min_opinion_investors=1"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["market"] == "HK"
    assert api_service.calls[-1][0] == "list"
    assert api_service.calls[-1][1][2:] == (2, 1)


def test_detail_returns_combined_view_and_preserves_sequence(api_client: TestClient) -> None:
    response = api_client.get(f"/api/v1/intelligence/assets/{_uuid(1)}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_name"] == "招商轮船"
    assert payload["market"] == "SH"
    assert payload["symbol"] == "601872"
    assert payload["completeness"] == "UNKNOWN"
    assert [
        payload["observed_attention_sequence"]["first_observed"]["investor_name"],
        *[
            item["investor_name"]
            for item in payload["observed_attention_sequence"]["later_observations"]
        ],
    ] == ["笨笨的投资者2", "沈阳城", "Captain-Nemo船长", "看好股市的新人"]
    assert "investor_views" in payload
    assert "data_quality" in payload


def test_timeline_returns_events_and_provenance(api_client: TestClient) -> None:
    response = api_client.get(f"/api/v1/intelligence/assets/{_uuid(1)}/timeline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"][0]["event_type"] == "ATTENTION_FIRST_OBSERVED"
    assert payload["events"][0]["attention_occurrence_id"] is not None
    assert payload["events"][0]["raw_event_id"] is not None
    times = [item["published_time"] for item in payload["events"]]
    assert times == sorted(times)


def test_error_semantics_and_nullable_missing_data(api_client: TestClient) -> None:
    unknown = api_client.get(f"/api/v1/intelligence/assets/{_uuid(999)}")
    no_evidence = api_client.get(
        f"/api/v1/intelligence/assets/{_uuid(2)}"
        "?window_start=2000-01-01T00:00:00Z&window_end=2000-01-02T00:00:00Z"
    )
    missing = api_client.get(f"/api/v1/intelligence/assets/{_uuid(4)}")

    assert unknown.status_code == 404
    assert no_evidence.status_code == 404
    assert missing.status_code == 200
    assert missing.json()["consensus"] is None
    assert missing.json()["data_quality"]["missing_thesis_comparison_count"] == 1
    assert (
        "MISSING_THESIS_COMPARISON"
        in missing.json()["data_quality"]["unresolved_semantic_limitations"]
    )


def test_invalid_filters_and_window_return_422(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/intelligence/assets?limit=101").status_code == 422
    assert api_client.get("/api/v1/intelligence/assets?offset=-1").status_code == 422
    assert (
        api_client.get("/api/v1/intelligence/assets?min_attention_investors=-1").status_code == 422
    )
    assert (
        api_client.get(
            "/api/v1/intelligence/assets"
            "?window_start=2026-01-03T00:00:00Z&window_end=2026-01-02T00:00:00Z"
        ).status_code
        == 422
    )


def test_ah_listings_have_distinct_http_resources(api_client: TestClient) -> None:
    hk = api_client.get(f"/api/v1/intelligence/assets/{_uuid(2)}")
    sh = api_client.get(f"/api/v1/intelligence/assets/{_uuid(3)}")

    assert hk.status_code == 200
    assert sh.status_code == 200
    assert hk.json()["asset_id"] != sh.json()["asset_id"]
    assert (hk.json()["market"], hk.json()["symbol"]) == ("HK", "01787")
    assert (sh.json()["market"], sh.json()["symbol"]) == ("SH", "600547")


def test_get_requests_do_not_commit_and_read_uow_rolls_back() -> None:
    service = _StubCombinedService(_fixture_views())
    app.dependency_overrides[get_combined_asset_intelligence_service] = lambda: service
    try:
        with TestClient(app) as client:
            assert client.get(f"/api/v1/intelligence/assets/{_uuid(1)}").status_code == 200
            assert client.get("/api/v1/intelligence/assets").status_code == 200
        assert service.write_calls == 0
    finally:
        app.dependency_overrides.pop(get_combined_asset_intelligence_service, None)

    class SessionSpy:
        def __init__(self):
            self.rollback_count = 0
            self.close_count = 0

        def rollback(self):
            self.rollback_count += 1

        def close(self):
            self.close_count += 1

    session = SessionSpy()
    unit_of_work = SqlAlchemyObservedAttentionUnitOfWork(lambda: session)
    with unit_of_work:
        assert hasattr(unit_of_work, "attention_occurrences")
    assert session.rollback_count == 1
    assert session.close_count == 1
    assert not hasattr(unit_of_work, "commit")


def test_unexpected_service_error_is_sanitized_to_500() -> None:
    class FailingService:
        def list_asset_views(self, *args, **kwargs):
            raise RuntimeError("internal database detail")

    app.dependency_overrides[get_combined_asset_intelligence_service] = lambda: FailingService()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/intelligence/assets")
    finally:
        app.dependency_overrides.pop(get_combined_asset_intelligence_service, None)

    assert response.status_code == 500
    assert response.json()["detail"] == "intelligence read unavailable"
