from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_intelligence_pattern_service
from backend.app.main import app
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
from intelligence.patterns.rules import detect_data_quality, detect_patterns
from intelligence.patterns.schemas import (
    IntelligencePatternType,
    IntelligencePatternView,
    PatternAssetIdentity,
    PatternTimeline,
)
from intelligence.patterns.service import IntelligencePatternService

NOW = datetime(2026, 9, 17, tzinfo=UTC)


def _context(
    *,
    current_signals=5,
    previous_signals=2,
    current_investors=4,
    previous_investors=2,
    current_attention=3,
    previous_attention=1,
    current_thesis=1,
    current_state="alignment=MIXED_DIRECTION; consensus=DIVERGENT",
    historical_state="alignment=ALIGNED_BULLISH; consensus=CONSENSUS_BULLISH",
    first=NOW - timedelta(days=40),
):
    return IntelligenceContextView(
        asset=ContextAssetIdentity(asset_id=uuid4(), name="测试资产", market="SH", symbol="600000"),
        activity_context=ActivityContext(
            current_signal_count=current_signals,
            previous_signal_count=previous_signals,
            change_description="test",
        ),
        investor_context=InvestorContext(
            current_investor_count=current_investors,
            previous_investor_count=previous_investors,
            new_investors=[uuid4()],
            returning_investors=[uuid4()] if previous_investors else [],
        ),
        attention_context=AttentionContext(
            current_attention_count=current_attention,
            historical_attention_count=previous_attention,
            change_description="test",
        ),
        thesis_context=ThesisContext(
            current_thesis_changes=current_thesis,
            historical_thesis_changes=1,
            direction_changes=["THESIS_CHANGED"],
        ),
        cross_investor_context=CrossInvestorContext(
            current_state=current_state,
            historical_state=historical_state,
        ),
        timeline_context=TimelineContext(
            first_observed_at=first,
            latest_observed_at=NOW,
            current_window_start=NOW - timedelta(days=30),
            current_window_end=NOW,
            previous_window_start=NOW - timedelta(days=60),
            previous_window_end=NOW - timedelta(days=30),
        ),
        limitations=[],
    )


class _ContextStub:
    def __init__(self, context):
        self.context = context
        self.calls = 0

    def get_asset_context(self, asset_id):
        self.calls += 1
        return self.context

    def get_candidate_context(self, candidate):
        self.calls += 1
        return self.context

    def batch_get_context(self, candidates=None, **kwargs):
        self.calls += 1
        return (self.context,)


def test_pattern_enum_and_each_primary_rule() -> None:
    context = _context()
    patterns = detect_patterns(context, multi_investor_threshold=3)
    types = {item.type for item in patterns}

    assert {
        IntelligencePatternType.ACCELERATING_ACTIVITY,
        IntelligencePatternType.MULTI_INVESTOR_EXPANSION,
        IntelligencePatternType.RETURNING_ATTENTION,
        IntelligencePatternType.THESIS_TRANSITION,
        IntelligencePatternType.CONSENSUS_FRAGMENTATION,
    } <= types
    assert IntelligencePatternType.CONSENSUS_FORMATION not in types


def test_zero_previous_window_does_not_infer_new_discovery_or_acceleration() -> None:
    context = _context(
        current_signals=1,
        previous_signals=0,
        current_investors=1,
        previous_investors=0,
        current_attention=1,
        previous_attention=0,
        current_thesis=0,
        current_state="alignment=ALIGNED_BULLISH; consensus=CONSENSUS_BULLISH",
        historical_state="alignment=INSUFFICIENT_EVIDENCE; consensus=INSUFFICIENT_EVIDENCE",
        first=NOW - timedelta(days=5),
    )
    types = {item.type for item in detect_patterns(context, multi_investor_threshold=3)}

    assert IntelligencePatternType.NEW_DISCOVERY not in types
    assert IntelligencePatternType.ACCELERATING_ACTIVITY not in types
    assert IntelligencePatternType.CONSENSUS_FORMATION in types
    assert IntelligencePatternType.INSUFFICIENT_HISTORY not in types
    assert any(item.type.value == "INSUFFICIENT_HISTORY" for item in detect_data_quality(context))


def test_thesis_transition_requires_material_existing_thesis_semantic() -> None:
    non_material = _context(current_thesis=3)
    non_material = non_material.model_copy(
        update={
            "thesis_context": ThesisContext(
                current_thesis_changes=3,
                historical_thesis_changes=0,
                direction_changes=[
                    "NEW_THESIS",
                    "THESIS_UNCHANGED",
                    "INSUFFICIENT_EVIDENCE",
                ],
            )
        }
    )
    material = non_material.model_copy(
        update={
            "thesis_context": ThesisContext(
                current_thesis_changes=1,
                historical_thesis_changes=0,
                direction_changes=["THESIS_CHANGED"],
            )
        }
    )

    assert IntelligencePatternType.THESIS_TRANSITION not in {
        item.type for item in detect_patterns(non_material, multi_investor_threshold=3)
    }
    assert IntelligencePatternType.THESIS_TRANSITION in {
        item.type for item in detect_patterns(material, multi_investor_threshold=3)
    }


def test_pattern_service_is_read_only_and_threshold_is_configurable() -> None:
    context = _context(current_investors=3)
    stub = _ContextStub(context)
    service = IntelligencePatternService(stub, multi_investor_threshold=4)

    view = service.get_asset_patterns(context.asset.asset_id)

    assert all(
        item.type != IntelligencePatternType.MULTI_INVESTOR_EXPANSION for item in view.patterns
    )
    assert stub.calls == 1
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


def test_pattern_api_is_read_only_projection() -> None:
    context = _context()
    service = IntelligencePatternService(_ContextStub(context))
    app.dependency_overrides[get_intelligence_pattern_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/intelligence/assets/{context.asset.asset_id}/patterns")
        assert response.status_code == 200
        payload = response.json()
        assert payload["asset"]["symbol"] == "600000"
        assert "score" not in payload
    finally:
        app.dependency_overrides.pop(get_intelligence_pattern_service, None)


def test_pattern_contract_has_no_persistence_identity() -> None:
    view = IntelligencePatternView(
        asset=PatternAssetIdentity(asset_id=uuid4(), name="测试资产", market="SH", symbol="600000"),
        patterns=[],
        timeline=PatternTimeline(),
        limitations=["history insufficient"],
    )

    assert view.patterns == []
    assert view.timeline.first_observed_at is None
