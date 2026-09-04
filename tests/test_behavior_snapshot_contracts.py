from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    BEHAVIOR_SNAPSHOT_POLICY_VERSION,
    InvestorBehaviorSnapshotCreate,
    build_behavior_snapshot_input_identity,
)


def _identity(investor_id, start: datetime, end: datetime, policy: str) -> str:
    return build_behavior_snapshot_input_identity(
        investor_id=investor_id,
        window_start=start,
        window_end=end,
        behavior_policy_version=policy,
        active_analysis_version="legacy:unspecified",
        thesis_comparison_version=None,
        consistency_policy_version=None,
    )


def _snapshot(**overrides: object) -> InvestorBehaviorSnapshotCreate:
    investor_id = overrides.pop("investor_id", uuid4())
    start = overrides.pop("window_start", datetime(2026, 9, 1, tzinfo=UTC))
    end = overrides.pop("window_end", datetime(2026, 9, 7, tzinfo=UTC))
    policy = overrides.pop("behavior_policy_version", BEHAVIOR_SNAPSHOT_POLICY_VERSION)
    values: dict[str, object] = {
        "investor_id": investor_id,
        "as_of": end,
        "window_start": start,
        "window_end": end,
        "attention_asset_count": 0,
        "attention_occurrence_count": 0,
        "new_attention_count": 0,
        "opinion_count": 0,
        "bullish_count": 0,
        "bearish_count": 0,
        "thesis_change_count": 0,
        "thesis_reinforced_count": 0,
        "thesis_changed_count": 0,
        "portfolio_action_count": 0,
        "position_increased_count": 0,
        "position_decreased_count": 0,
        "positive_alignment_count": 0,
        "negative_alignment_count": 0,
        "behavior_policy_version": policy,
        "calculated_at": datetime(2026, 9, 7, 1, tzinfo=UTC),
        "input_identity": _identity(investor_id, start, end, policy),
    }
    values.update(overrides)
    return InvestorBehaviorSnapshotCreate(**values)


def test_behavior_snapshot_identity_is_deterministic() -> None:
    first = _snapshot()
    second = _snapshot(
        investor_id=first.investor_id,
        window_start=first.window_start,
        window_end=first.window_end,
        behavior_policy_version=first.behavior_policy_version,
        input_identity=first.input_identity,
    )

    assert first.input_identity == second.input_identity
    assert first.window_start.tzinfo is not None


def test_behavior_snapshot_rejects_reversed_window() -> None:
    start = datetime(2026, 9, 7, tzinfo=UTC)
    end = start - timedelta(days=1)

    with pytest.raises(ValidationError, match="window_start"):
        _snapshot(window_start=start, window_end=end, as_of=start)


def test_behavior_snapshot_accepts_deterministic_fingerprint() -> None:
    snapshot = _snapshot(input_identity="a" * 64)

    assert snapshot.input_identity == "a" * 64


def test_behavior_snapshot_metrics_cannot_be_negative() -> None:
    with pytest.raises(ValidationError, match="attention_asset_count"):
        _snapshot(attention_asset_count=-1)


def test_behavior_input_identity_changes_when_effective_inputs_change() -> None:
    investor_id = uuid4()
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 7, tzinfo=UTC)
    first_id = uuid4()
    second_id = uuid4()

    first = build_behavior_snapshot_input_identity(
        investor_id=investor_id,
        window_start=start,
        window_end=end,
        behavior_policy_version=BEHAVIOR_SNAPSHOT_POLICY_VERSION,
        active_analysis_version="analysis-v1",
        thesis_comparison_version="thesis-v1",
        consistency_policy_version="consistency-v1",
        opinion_ids=(first_id,),
    )
    same_inputs_different_order = build_behavior_snapshot_input_identity(
        investor_id=investor_id,
        window_start=start,
        window_end=end,
        behavior_policy_version=BEHAVIOR_SNAPSHOT_POLICY_VERSION,
        active_analysis_version="analysis-v1",
        thesis_comparison_version="thesis-v1",
        consistency_policy_version="consistency-v1",
        opinion_ids=(first_id,),
    )
    changed_inputs = build_behavior_snapshot_input_identity(
        investor_id=investor_id,
        window_start=start,
        window_end=end,
        behavior_policy_version=BEHAVIOR_SNAPSHOT_POLICY_VERSION,
        active_analysis_version="analysis-v1",
        thesis_comparison_version="thesis-v1",
        consistency_policy_version="consistency-v1",
        opinion_ids=(second_id,),
    )
    changed_policy = build_behavior_snapshot_input_identity(
        investor_id=investor_id,
        window_start=start,
        window_end=end,
        behavior_policy_version=BEHAVIOR_SNAPSHOT_POLICY_VERSION,
        active_analysis_version="analysis-v2",
        thesis_comparison_version="thesis-v1",
        consistency_policy_version="consistency-v1",
        opinion_ids=(first_id,),
    )
    changed_attention_policy = build_behavior_snapshot_input_identity(
        investor_id=investor_id,
        window_start=start,
        window_end=end,
        behavior_policy_version=BEHAVIOR_SNAPSHOT_POLICY_VERSION,
        active_analysis_version="analysis-v1",
        thesis_comparison_version="thesis-v1",
        consistency_policy_version="consistency-v1",
        attention_policy_version="attention-occurrence-v2",
        opinion_ids=(first_id,),
    )

    assert first == same_inputs_different_order
    assert first != changed_inputs
    assert first != changed_policy
    assert first != changed_attention_policy
