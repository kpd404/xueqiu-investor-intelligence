from collections import Counter
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_investor_intelligence_product_service
from backend.app.main import app
from contracts import (
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceView,
    OpinionDirection,
    OpinionTimelineEntry,
    ThesisChangeType,
    ThesisChangeView,
)
from intelligence.investor_product.schemas import InvestorIntelligenceView
from intelligence.investor_product.service import InvestorIntelligenceProductService
from intelligence.investor_read_scope import (
    InvestorIntelligenceReadScope,
    InvestorIntelligenceReadScopeLoader,
    InvestorIntelligenceReadScopeNotFoundError,
    InvestorReadIdentity,
)
from intelligence.read_scope import AssetReadIdentity

NOW = datetime(2026, 9, 19, tzinfo=UTC)
FORBIDDEN_KEYS = {
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


def _attention(
    investor_id: UUID,
    asset_id: UUID,
    *,
    published_time: datetime,
    event_id: UUID | None = None,
    occurrence_id: UUID | None = None,
    evidence_type: AttentionEvidenceType = AttentionEvidenceType.EXPLICIT_MENTION,
) -> AttentionOccurrenceView:
    event_id = event_id or uuid4()
    return AttentionOccurrenceView(
        id=occurrence_id or uuid4(),
        investor_id=investor_id,
        asset_id=asset_id,
        event_id=event_id,
        published_time=published_time,
        evidence_types=(evidence_type,),
        evidence=(
            AttentionEvidence(
                evidence_type=evidence_type,
                matched_by="test",
                reference="fixture",
            ),
        ),
        analysis_id=None,
        opinion_id=None,
        attention_policy_version="attention-occurrence-v1",
        calculated_at=published_time,
    )


def _opinion(
    investor_id: UUID,
    asset_id: UUID,
    *,
    published_time: datetime,
    direction: OpinionDirection,
    opinion_id: UUID | None = None,
    event_id: UUID | None = None,
) -> OpinionTimelineEntry:
    return OpinionTimelineEntry(
        opinion_id=opinion_id or uuid4(),
        event_id=event_id or uuid4(),
        investor_id=investor_id,
        asset_id=asset_id,
        direction=direction,
        strength=60,
        confidence=0.7,
        published_time=published_time,
        generated_time=published_time + timedelta(minutes=1),
    )


def _thesis(
    investor_id: UUID,
    asset_id: UUID,
    *,
    effective_time: datetime,
    change_type: ThesisChangeType,
) -> ThesisChangeView:
    previous_opinion_id = None if change_type is ThesisChangeType.NEW_THESIS else uuid4()
    previous_event_id = None if previous_opinion_id is None else uuid4()
    return ThesisChangeView(
        id=uuid4(),
        investor_id=investor_id,
        asset_id=asset_id,
        previous_opinion_id=previous_opinion_id,
        current_opinion_id=uuid4(),
        previous_event_id=previous_event_id,
        current_event_id=uuid4(),
        effective_time=effective_time,
        change_type=change_type,
        confidence=0.7,
        summary="Persisted ThesisChange fixture",
        evidence=("raw evidence",),
        opinion_analysis_version="test-analysis",
        comparison_version="test-comparison",
        calculated_at=effective_time,
        input_identity=str(uuid4()),
    )


def _scope() -> InvestorIntelligenceReadScope:
    investor_id = uuid4()
    asset_hk = uuid4()
    asset_sh = uuid4()
    attention_old = _attention(
        investor_id,
        asset_hk,
        published_time=NOW - timedelta(days=4),
        event_id=uuid4(),
    )
    attention_latest = _attention(
        investor_id,
        asset_hk,
        published_time=NOW - timedelta(days=1),
        event_id=attention_old.event_id,
    )
    attention_only = _attention(
        investor_id,
        asset_sh,
        published_time=NOW - timedelta(days=2),
        evidence_type=AttentionEvidenceType.REPOST,
    )
    opinion_old = _opinion(
        investor_id,
        asset_hk,
        published_time=NOW - timedelta(days=3),
        direction=OpinionDirection.BULLISH,
    )
    opinion_latest = _opinion(
        investor_id,
        asset_hk,
        published_time=NOW - timedelta(days=1),
        direction=OpinionDirection.BEARISH,
    )
    changes = (
        _thesis(
            investor_id,
            asset_hk,
            effective_time=NOW - timedelta(days=2),
            change_type=ThesisChangeType.THESIS_CHANGED,
        ),
        _thesis(
            investor_id,
            asset_hk,
            effective_time=NOW - timedelta(days=1),
            change_type=ThesisChangeType.THESIS_REINFORCED,
        ),
    )
    return InvestorIntelligenceReadScope(
        investor=InvestorReadIdentity(
            investor_id=investor_id,
            name="Test Investor",
            platform="xueqiu",
            platform_user_id="test-investor",
        ),
        window_start=NOW - timedelta(days=30),
        window_end=NOW,
        attention_occurrences=(attention_latest, attention_old, attention_only),
        opinions=(opinion_latest, opinion_old),
        thesis_changes=changes,
        assets=(
            AssetReadIdentity(asset_hk, "山东黄金", "HK", "01787"),
            AssetReadIdentity(asset_sh, "山东黄金", "SH", "600547"),
        ),
    )


class _Loader:
    def __init__(self, scope: InvestorIntelligenceReadScope):
        self.scope = scope
        self.calls = 0

    def load(self, investor_id: UUID, *, as_of=None):
        self.calls += 1
        if investor_id != self.scope.investor.investor_id:
            raise InvestorIntelligenceReadScopeNotFoundError(str(investor_id))
        return self.scope


def _service(scope: InvestorIntelligenceReadScope):
    loader = _Loader(scope)
    return InvestorIntelligenceProductService(loader), loader


def test_investor_product_contract_composes_facts_without_forbidden_fields():
    scope = _scope()
    service, loader = _service(scope)

    view = service.get_investor_view(scope.investor.investor_id)

    assert isinstance(view, InvestorIntelligenceView)
    assert loader.calls == 1
    assert view.summary.observed_asset_count == 2
    assert view.summary.opinion_asset_count == 1
    assert len(view.coverage.attention_only_assets) == 1
    assert view.summary.attention_occurrence_count == 3
    assert view.summary.opinion_count == 2
    assert view.summary.thesis_change_count == 2
    assert view.traceability_summary.attention_occurrence_ref_count == 3
    assert all(item.traceability.attention_occurrence_ids for item in view.asset_views)
    assert not FORBIDDEN_KEYS.intersection(set(_walk_keys(view.model_dump())))


def test_latest_direction_is_latest_persisted_opinion_and_attention_only_is_not_interpreted():
    scope = _scope()
    view = _service(scope)[0].get_investor_view(scope.investor.investor_id)
    hong_kong = next(item for item in view.asset_views if item.asset.market == "HK")
    mainland = next(item for item in view.asset_views if item.asset.market == "SH")

    assert hong_kong.opinion.latest_direction is OpinionDirection.BEARISH
    assert hong_kong.opinion.opinion_count == 2
    assert mainland.relationship.attention_only is True
    assert mainland.opinion.latest_direction is None


def test_existing_investor_with_attention_but_no_opinion_returns_valid_view():
    scope = _scope()
    scope = scope.__class__(
        investor=scope.investor,
        window_start=scope.window_start,
        window_end=scope.window_end,
        attention_occurrences=scope.attention_occurrences,
        opinions=(),
        thesis_changes=(),
        assets=scope.assets,
    )

    view = _service(scope)[0].get_investor_view(scope.investor.investor_id)

    assert view.summary.observed_asset_count == 2
    assert view.summary.opinion_asset_count == 0
    assert view.summary.opinion_count == 0
    assert len(view.coverage.attention_only_assets) == 2
    assert all(item.opinion.latest_direction is None for item in view.asset_views)


@pytest.mark.parametrize(
    "change_type",
    tuple(ThesisChangeType),
)
def test_product_preserves_each_persisted_thesis_change_type(change_type):
    scope = _scope()
    thesis = _thesis(
        scope.investor.investor_id,
        scope.assets[0].asset_id,
        effective_time=NOW,
        change_type=change_type,
    )
    scope = scope.__class__(
        investor=scope.investor,
        window_start=scope.window_start,
        window_end=scope.window_end,
        attention_occurrences=scope.attention_occurrences,
        opinions=scope.opinions,
        thesis_changes=(thesis,),
        assets=scope.assets,
    )

    view = _service(scope)[0].get_investor_view(scope.investor.investor_id)

    assert view.asset_views[0].thesis.latest_change_type == change_type.value


def test_activity_is_fact_time_ordered_and_semantically_deduped():
    scope = _scope()
    duplicate_opinion = scope.opinions[0]
    scope = scope.__class__(
        investor=scope.investor,
        window_start=scope.window_start,
        window_end=scope.window_end,
        attention_occurrences=scope.attention_occurrences,
        opinions=(*scope.opinions, duplicate_opinion),
        thesis_changes=scope.thesis_changes,
        assets=scope.assets,
    )

    view = _service(scope)[0].get_investor_view(scope.investor.investor_id)

    assert list(view.recent_activity) == sorted(
        view.recent_activity,
        key=lambda item: (item.observed_at, item.event_type, item.asset.asset_id.int),
    )
    opinion_refs = [
        item
        for item in view.recent_activity
        if item.event_type == "OPINION_RECORDED"
        and item.source_refs[0][1] == duplicate_opinion.opinion_id
    ]
    assert len(opinion_refs) == 1
    assert {item.event_type for item in view.recent_activity} == {
        "ATTENTION_OBSERVED",
        "OPINION_RECORDED",
        "THESIS_CHANGE_OBSERVED",
    }


class _CountingReader:
    def __init__(self, counts: Counter, key: str, values=()):
        self.counts = counts
        self.key = key
        self.values = tuple(values)

    def list_effective_by_investor(self, *args, **kwargs):
        self.counts[self.key] += 1
        return list(self.values)

    def list_effective_timeline_by_investor(self, *args, **kwargs):
        self.counts[self.key] += 1
        return list(self.values)


class _CountingInvestors:
    def __init__(self, counts: Counter, investor):
        self.counts = counts
        self.investor = investor

    def get(self, investor_id):
        self.counts["investor"] += 1
        return self.investor


class _CountingAssets:
    def __init__(self, counts: Counter, assets):
        self.counts = counts
        self.assets = assets
        self.received_ids = None

    def list_by_ids(self, asset_ids):
        self.counts["assets"] += 1
        self.received_ids = asset_ids
        return self.assets


class _ReadUow:
    def __init__(self, scope: InvestorIntelligenceReadScope, counts: Counter):
        investor = SimpleNamespace(
            id=scope.investor.investor_id,
            name=scope.investor.name,
            platform=scope.investor.platform,
            platform_user_id=scope.investor.platform_user_id,
        )
        assets = tuple(
            SimpleNamespace(
                id=item.asset_id,
                name=item.name,
                market=item.market,
                symbol=item.symbol,
            )
            for item in scope.assets
        )
        self.investors = _CountingInvestors(counts, investor)
        self.attention_occurrences = _CountingReader(
            counts, "attention", scope.attention_occurrences
        )
        self.opinions = _CountingReader(counts, "opinions", scope.opinions)
        self.thesis_changes = _CountingReader(counts, "thesis", scope.thesis_changes)
        self.assets = _CountingAssets(counts, assets)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def test_shared_investor_scope_is_bounded_and_loads_assets_once():
    scope = _scope()
    counts = Counter()
    uow = _ReadUow(scope, counts)
    loader = InvestorIntelligenceReadScopeLoader(lambda: uow, now_factory=lambda: NOW)

    loaded = loader.load(scope.investor.investor_id)

    assert loaded.investor == scope.investor
    assert counts == {"investor": 1, "attention": 1, "opinions": 1, "thesis": 1, "assets": 1}
    assert uow.assets.received_ids == tuple(
        sorted((item.asset_id for item in scope.assets), key=lambda value: value.int)
    )


def test_scope_rejects_cross_investor_or_cross_listing_artifacts():
    scope = _scope()
    foreign_attention = scope.attention_occurrences[0].model_copy(update={"investor_id": uuid4()})
    with pytest.raises(ValueError, match="another Investor"):
        scope.__class__(
            investor=scope.investor,
            window_start=scope.window_start,
            window_end=scope.window_end,
            attention_occurrences=(foreign_attention,),
            opinions=scope.opinions,
            thesis_changes=scope.thesis_changes,
            assets=scope.assets,
        )

    foreign_asset_opinion = scope.opinions[0].model_copy(update={"asset_id": uuid4()})
    with pytest.raises(ValueError, match="missing Asset identity"):
        scope.__class__(
            investor=scope.investor,
            window_start=scope.window_start,
            window_end=scope.window_end,
            attention_occurrences=scope.attention_occurrences,
            opinions=(foreign_asset_opinion,),
            thesis_changes=scope.thesis_changes,
            assets=scope.assets,
        )


def test_product_api_is_read_only_and_unknown_investor_is_404():
    scope = _scope()
    service, _ = _service(scope)
    app.dependency_overrides[get_investor_intelligence_product_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/investors/{scope.investor.investor_id}/view")
            missing = client.get(f"/api/intelligence/investors/{uuid4()}/view")
        assert response.status_code == 200
        assert response.json()["investor"]["name"] == "Test Investor"
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_investor_intelligence_product_service, None)

    paths = set(app.openapi()["paths"])
    assert "/api/intelligence/investors/{investor_id}/view" in paths
