from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_investor_intelligence_service
from backend.app.main import app
from contracts import (
    AttentionEvidenceType,
    DirectionalAlignmentState,
    InvestorAssetIntelligenceSummary,
    InvestorIntelligenceDataQuality,
    InvestorIntelligenceView,
    InvestorOverlapSummary,
    ObservedAttentionCompleteness,
    OpinionCoverageState,
    OpinionDirection,
)
from intelligence.services.investor_intelligence import (
    InvestorIntelligenceInvestorNotFoundError,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
END = START + timedelta(days=10)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _view() -> InvestorIntelligenceView:
    asset = InvestorAssetIntelligenceSummary(
        asset_id=_uuid(1),
        asset_name="山东黄金",
        market="HK",
        symbol="01787",
        attention_occurrence_count=2,
        first_attention_time=START,
        latest_attention_time=START + timedelta(days=1),
        attention_evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
        opinion_count=2,
        first_opinion_time=START,
        latest_opinion_time=START + timedelta(days=2),
        latest_observed_direction=OpinionDirection.BULLISH,
        thesis_change_count=2,
        changed_count=1,
        extended_count=0,
        reversal_count=1,
        missing_thesis_comparison_count=0,
        attention_investor_count=2,
        opinion_investor_count=2,
        shared_attention_investor_count=1,
        shared_opinion_investor_count=1,
        latest_evidence_time=START + timedelta(days=2),
        alignment=DirectionalAlignmentState.MIXED_DIRECTION,
        consensus=None,
    )
    return InvestorIntelligenceView(
        investor_id=_uuid(10),
        investor_name="人生是历练",
        window_start=START,
        window_end=END,
        completeness=ObservedAttentionCompleteness.UNKNOWN,
        first_observed_evidence_time=START,
        latest_observed_evidence_time=START + timedelta(days=2),
        attention_asset_count=1,
        opinion_asset_count=1,
        repeated_opinion_asset_count=1,
        thesis_changed_asset_count=1,
        direction_reversal_asset_count=1,
        shared_attention_asset_count=1,
        shared_opinion_asset_count=1,
        asset_views=(asset,),
        overlap_summaries=(
            InvestorOverlapSummary(
                other_investor_id=_uuid(11),
                other_investor_name="沈阳城",
                shared_attention_asset_count=1,
                shared_opinion_asset_count=1,
            ),
        ),
        data_quality=InvestorIntelligenceDataQuality(
            completeness=ObservedAttentionCompleteness.UNKNOWN,
            opinion_coverage=OpinionCoverageState.COMPLETE,
            missing_thesis_comparison_count=0,
            cross_investor_lineage_available=True,
            limitations=(
                "HISTORICAL_COMPLETENESS_UNKNOWN",
                "ABSENCE_INFERENCE_UNSUPPORTED",
                "COLLECTION_PROVENANCE_UNAVAILABLE",
                "LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY",
            ),
        ),
    )


class _StubInvestorService:
    def __init__(self):
        self.view = _view()
        self.calls: list[tuple[datetime | None, datetime | None, int | None, int | None]] = []
        self.write_calls = 0

    def list_investor_views(
        self,
        window_start=None,
        window_end=None,
        *,
        min_attention_assets=None,
        min_opinion_assets=None,
    ):
        self.calls.append((window_start, window_end, min_attention_assets, min_opinion_assets))
        if window_start is not None and window_end is not None and window_start > window_end:
            raise ValueError("invalid window")
        if (
            min_attention_assets is not None
            and self.view.attention_asset_count < min_attention_assets
        ) or (
            min_opinion_assets is not None and self.view.opinion_asset_count < min_opinion_assets
        ):
            return ()
        return (self.view,)

    def get_investor_view(self, investor_id, window_start=None, window_end=None):
        self.calls.append((window_start, window_end, None, None))
        if investor_id != self.view.investor_id:
            raise InvestorIntelligenceInvestorNotFoundError("missing")
        if window_start is not None and window_end is not None and window_start > window_end:
            raise ValueError("invalid window")
        return self.view


def _client(stub: _StubInvestorService):
    app.dependency_overrides[get_investor_intelligence_service] = lambda: stub
    return TestClient(app)


def test_investor_openapi_and_http_shapes():
    stub = _StubInvestorService()
    client = _client(stub)
    try:
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        paths = openapi.json()["paths"]
        assert "/api/v1/intelligence/investors" in paths
        assert "/api/v1/intelligence/investors/{investor_id}" in paths
        descriptions = " ".join(
            operation.get("description", "")
            for path in paths.values()
            for operation in path.values()
            if isinstance(operation, dict)
        ).lower()
        for value in ("observed", "unknown", "absence", "holdings", "influence"):
            assert value in descriptions

        listing = client.get("/api/v1/intelligence/investors")
        detail = client.get(f"/api/v1/intelligence/investors/{_uuid(10)}")
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["investor_name"] == "人生是历练"
        assert detail.status_code == 200
        assert detail.json()["completeness"] == "UNKNOWN"
        assert detail.json()["asset_views"][0]["market"] == "HK"
        assert detail.json()["data_quality"]["absence_inference_supported"] is False
    finally:
        app.dependency_overrides.pop(get_investor_intelligence_service, None)


def test_investor_api_filters_and_errors_are_thin():
    stub = _StubInvestorService()
    client = _client(stub)
    try:
        filtered = client.get(
            "/api/v1/intelligence/investors?min_attention_assets=1&min_opinion_assets=1"
        )
        assert filtered.status_code == 200
        assert stub.calls[-1][2:] == (1, 1)
        assert (
            client.get("/api/v1/intelligence/investors?min_attention_assets=-1").status_code == 422
        )
        assert (
            client.get(
                "/api/v1/intelligence/investors"
                "?window_start=2026-01-03T00:00:00Z&window_end=2026-01-02T00:00:00Z"
            ).status_code
            == 422
        )
        assert client.get(f"/api/v1/intelligence/investors/{_uuid(999)}").status_code == 404
        assert stub.write_calls == 0
    finally:
        app.dependency_overrides.pop(get_investor_intelligence_service, None)
