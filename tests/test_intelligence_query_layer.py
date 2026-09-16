from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_intelligence_query_service
from backend.app.main import app
from contracts import (
    InvestorIntelligenceView as ExistingInvestorIntelligenceView,
)
from intelligence.queries.asset_view import build_asset_intelligence_view
from intelligence.queries.investor_view import build_investor_intelligence_view
from intelligence.queries.signal_view import build_signal_candidate_views
from intelligence.schemas.intelligence import (
    AssetIntelligenceView,
    IntelligenceSearchEntity,
    InvestorIntelligenceView,
    SignalCandidateType,
)
from intelligence.services.combined_asset_intelligence import CombinedAssetNotFoundError
from intelligence.services.investor_intelligence import (
    InvestorIntelligenceInvestorNotFoundError,
)
from tests.test_intelligence_read_api import _fixture_views
from tests.test_investor_intelligence_api import _view as fixture_investor_view


def test_asset_query_projection_preserves_existing_evidence() -> None:
    source = _fixture_views()[0]

    view = build_asset_intelligence_view(source)

    assert isinstance(view, AssetIntelligenceView)
    assert view.asset_id == source.asset_id
    assert (view.asset_name, view.market, view.symbol) == (
        source.asset_name,
        source.market,
        source.symbol,
    )
    assert view.cross_investor.attention_investors == (
        source.attention_summary.attention_investor_count
    )
    assert view.data_quality.completeness.value == "UNKNOWN"
    assert "score" not in view.model_dump()
    assert "ranking" not in view.model_dump()


def test_investor_query_projection_exposes_breadth_and_data_boundary() -> None:
    source: ExistingInvestorIntelligenceView = fixture_investor_view()

    view = build_investor_intelligence_view(source)

    assert isinstance(view, InvestorIntelligenceView)
    assert view.investor_name == "人生是历练"
    assert view.attention_summary.total_attention_assets == source.attention_asset_count
    assert view.opinion_summary.total_opinion_assets == source.opinion_asset_count
    assert view.data_quality.completeness.value == "UNKNOWN"
    assert view.data_quality.absence_inference_supported is False


def test_signal_projection_is_pure_and_uses_existing_event_types() -> None:
    source = _fixture_views()[2]

    candidates = build_signal_candidate_views(source)

    assert all(candidate.asset_id == source.asset_id for candidate in candidates)
    assert SignalCandidateType.NEW_ATTENTION in {
        candidate.candidate_type for candidate in candidates
    }
    assert all("score" not in candidate.model_dump() for candidate in candidates)


class _StubQueryService:
    def __init__(self) -> None:
        self.asset_view = build_asset_intelligence_view(_fixture_views()[0])
        self.investor_view = build_investor_intelligence_view(fixture_investor_view())

    def get_asset_view(self, asset_id, window_start=None, window_end=None):
        if asset_id != self.asset_view.asset_id:
            raise CombinedAssetNotFoundError("missing")
        return self.asset_view

    def get_investor_view(self, investor_id, window_start=None, window_end=None):
        if investor_id != self.investor_view.investor_id:
            raise InvestorIntelligenceInvestorNotFoundError("missing")
        return self.investor_view

    def search(self, query):
        return (
            IntelligenceSearchEntity(
                entity_type="asset",
                entity_id=self.asset_view.asset_id,
                name=self.asset_view.asset_name,
                market=self.asset_view.market,
                symbol=self.asset_view.symbol,
            ),
            IntelligenceSearchEntity(
                entity_type="investor",
                entity_id=self.investor_view.investor_id,
                name=self.investor_view.investor_name,
            ),
        )


def test_query_api_exposes_investor_asset_and_search_paths() -> None:
    service = _StubQueryService()
    app.dependency_overrides[get_intelligence_query_service] = lambda: service
    try:
        with TestClient(app) as client:
            investor = client.get(
                f"/api/intelligence/investors/{service.investor_view.investor_id}"
            )
            asset = client.get(f"/api/intelligence/assets/{service.asset_view.asset_id}")
            search = client.get("/api/intelligence/search?q=山东黄金")

        assert investor.status_code == 200
        assert investor.json()["completeness"] == "UNKNOWN"
        assert asset.status_code == 200
        assert asset.json()["asset_id"] == str(service.asset_view.asset_id)
        assert search.status_code == 200
        assert search.json()["query"] == "山东黄金"
        assert {item["entity_type"] for item in search.json()["items"]} == {
            "asset",
            "investor",
        }
    finally:
        app.dependency_overrides.pop(get_intelligence_query_service, None)


def test_query_api_search_rejects_blank_text() -> None:
    service = _StubQueryService()
    app.dependency_overrides[get_intelligence_query_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/intelligence/search?q=%20%20")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_intelligence_query_service, None)


def test_query_api_openapi_describes_read_only_boundary() -> None:
    service = _StubQueryService()
    app.dependency_overrides[get_intelligence_query_service] = lambda: service
    try:
        with TestClient(app) as client:
            paths = client.get("/openapi.json").json()["paths"]
        assert "/api/intelligence/investors/{investor_id}" in paths
        assert "/api/intelligence/assets/{asset_id}" in paths
        assert "/api/intelligence/search" in paths
        descriptions = " ".join(
            operation.get("description", "")
            for path in paths.values()
            for operation in path.values()
            if isinstance(operation, dict)
        ).lower()
        assert "read-only" in descriptions
        assert "unknown" in descriptions
        assert "score" in descriptions
    finally:
        app.dependency_overrides.pop(get_intelligence_query_service, None)
