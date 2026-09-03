from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    AnalysisSpec,
    OpinionDirection,
    ThesisChangeCreate,
    ThesisChangeType,
    ThesisComparisonInput,
    ThesisComparisonResult,
    ThesisComparisonSpec,
    ThesisOpinionView,
)


def _opinion(*, published_time: datetime, asset_id, investor_id) -> ThesisOpinionView:
    return ThesisOpinionView(
        opinion_id=uuid4(),
        event_id=uuid4(),
        investor_id=investor_id,
        asset_id=asset_id,
        analysis_version="active-analysis",
        asset_name="Test Asset",
        market="SH",
        symbol="000001",
        direction=OpinionDirection.BULLISH,
        strength=70,
        confidence=0.8,
        thesis=("cash flow",),
        catalysts=(),
        risks=(),
        time_horizon=None,
        published_time=published_time,
        generated_time=published_time + timedelta(hours=1),
        current_author_text="author text",
    )


def test_comparison_spec_is_independent_from_opinion_analysis_identity() -> None:
    source = AnalysisSpec.for_provider(
        provider_id="provider-a",
        model_version="model-a",
        prompt_version="thesis-comparison-v1",
        schema_version="thesis-comparison-result-v1",
        analysis_policy_version="thesis-comparison-policy-v1",
    )

    spec = ThesisComparisonSpec.from_analysis_spec(source)

    assert spec.comparison_version == source.analysis_version
    assert spec.comparison_policy_version == "thesis-comparison-policy-v1"
    assert spec.prompt_version != "opinion-extraction-v5"


@pytest.mark.parametrize("change_type", list(ThesisChangeType))
def test_all_v0_change_types_are_structured(change_type: ThesisChangeType) -> None:
    result = ThesisComparisonResult(
        change_type=change_type,
        confidence=0.5,
        summary="structured result",
        evidence=(),
    )

    assert result.change_type is change_type


def test_comparison_input_rejects_cross_investor_or_future_predecessor() -> None:
    asset_id = uuid4()
    investor_id = uuid4()
    current = _opinion(
        published_time=datetime(2026, 9, 2, tzinfo=UTC),
        asset_id=asset_id,
        investor_id=investor_id,
    )
    future = _opinion(
        published_time=datetime(2026, 9, 3, tzinfo=UTC),
        asset_id=asset_id,
        investor_id=investor_id,
    )

    with pytest.raises(ValidationError):
        ThesisComparisonInput(
            asset_id=asset_id,
            asset_name="Test Asset",
            market="SH",
            symbol="000001",
            previous=future,
            current=current,
        )

    with pytest.raises(ValidationError):
        ThesisComparisonInput(
            asset_id=asset_id,
            asset_name="Test Asset",
            market="SH",
            symbol="000001",
            previous=_opinion(
                published_time=datetime(2026, 9, 1, tzinfo=UTC),
                asset_id=asset_id,
                investor_id=uuid4(),
            ),
            current=current,
        )


def test_first_thesis_artifact_requires_no_previous_identity() -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    investor_id = uuid4()
    asset_id = uuid4()
    command = ThesisChangeCreate(
        investor_id=investor_id,
        asset_id=asset_id,
        current_opinion_id=uuid4(),
        current_event_id=uuid4(),
        effective_time=now,
        change_type=ThesisChangeType.NEW_THESIS,
        confidence=0.8,
        summary="first",
        opinion_analysis_version="active-v5",
        comparison_version="comparison-v1",
        calculated_at=now,
        input_identity='{"comparison_version":"comparison-v1","current_opinion_id":"x","previous_opinion_id":"NONE"}',
    )

    assert command.previous_opinion_id is None
    assert command.previous_event_id is None
