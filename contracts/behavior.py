"""Provider-neutral contracts for Investor Behavior Snapshot aggregation."""

import json
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

BEHAVIOR_SNAPSHOT_POLICY_VERSION = "investor-behavior-snapshot-v1"


def utc_now() -> datetime:
    return datetime.now(UTC)


class InvestorBehaviorSnapshotCreate(BaseModel):
    """Immutable derived metrics for one Investor and fact-time window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    as_of: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime

    attention_asset_count: int = Field(ge=0)
    attention_occurrence_count: int = Field(ge=0)
    new_attention_count: int = Field(ge=0)

    opinion_count: int = Field(ge=0)
    bullish_count: int = Field(ge=0)
    bearish_count: int = Field(ge=0)

    thesis_change_count: int = Field(ge=0)
    thesis_reinforced_count: int = Field(ge=0)
    thesis_changed_count: int = Field(ge=0)

    portfolio_action_count: int = Field(ge=0)
    position_increased_count: int = Field(ge=0)
    position_decreased_count: int = Field(ge=0)

    positive_alignment_count: int = Field(ge=0)
    negative_alignment_count: int = Field(ge=0)

    behavior_policy_version: str = Field(
        default=BEHAVIOR_SNAPSHOT_POLICY_VERSION,
        min_length=1,
        max_length=64,
    )
    calculated_at: AwareDatetime = Field(default_factory=utc_now)
    input_identity: str = Field(min_length=1, max_length=512)

    @field_validator("as_of", "window_start", "window_end", "calculated_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_window_and_identity(self) -> Self:
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if self.as_of < self.window_end:
            raise ValueError("as_of must be on or after window_end")
        expected = json.dumps(
            {
                "behavior_policy_version": self.behavior_policy_version,
                "investor_id": str(self.investor_id),
                "window_end": self.window_end.isoformat(),
                "window_start": self.window_start.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if self.input_identity != expected:
            raise ValueError("input_identity does not match behavior snapshot identity")
        return self


class InvestorBehaviorSnapshotView(InvestorBehaviorSnapshotCreate):
    id: UUID


class InvestorBehaviorSnapshotResult(BaseModel):
    """Calculation result returned by the Behavior Snapshot service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    investor_id: UUID
    window_start: AwareDatetime
    window_end: AwareDatetime
    behavior_policy_version: str = Field(min_length=1, max_length=64)
    created: bool


__all__ = [
    "BEHAVIOR_SNAPSHOT_POLICY_VERSION",
    "InvestorBehaviorSnapshotCreate",
    "InvestorBehaviorSnapshotResult",
    "InvestorBehaviorSnapshotView",
]
