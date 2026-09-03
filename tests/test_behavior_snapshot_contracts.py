from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import BEHAVIOR_SNAPSHOT_POLICY_VERSION, InvestorBehaviorSnapshotCreate


def _identity(investor_id, start: datetime, end: datetime, policy: str) -> str:
    import json

    return json.dumps(
        {
            "behavior_policy_version": policy,
            "investor_id": str(investor_id),
            "window_end": end.isoformat(),
            "window_start": start.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
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


def test_behavior_snapshot_rejects_non_canonical_identity() -> None:
    with pytest.raises(ValidationError, match="input_identity"):
        _snapshot(input_identity="not-canonical")


def test_behavior_snapshot_metrics_cannot_be_negative() -> None:
    with pytest.raises(ValidationError, match="attention_asset_count"):
        _snapshot(attention_asset_count=-1)
