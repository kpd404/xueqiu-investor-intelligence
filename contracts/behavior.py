"""Provider-neutral contracts for Investor Behavior Snapshot aggregation."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.attention import PRODUCTION_ATTENTION_POLICY_VERSION

BEHAVIOR_SNAPSHOT_POLICY_VERSION = "investor-behavior-snapshot-v1"


def utc_now() -> datetime:
    return datetime.now(UTC)


def build_behavior_snapshot_input_identity(
    *,
    investor_id: UUID,
    window_start: datetime,
    window_end: datetime,
    behavior_policy_version: str,
    active_analysis_version: str,
    thesis_comparison_version: str | None,
    consistency_policy_version: str | None,
    attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
    attention_occurrence_ids: tuple[UUID, ...] = (),
    attention_first_dependencies: tuple[tuple[UUID, UUID, datetime], ...] = (),
    opinion_ids: tuple[UUID, ...] = (),
    thesis_change_ids: tuple[UUID, ...] = (),
    portfolio_action_ids: tuple[UUID, ...] = (),
    consistency_ids: tuple[UUID, ...] = (),
) -> str:
    """Return a stable fingerprint for one exact aggregation input set."""

    payload = {
        "active_analysis_version": active_analysis_version,
        "attention_occurrence_ids": [
            str(value) for value in sorted(attention_occurrence_ids, key=str)
        ],
        "attention_first_dependencies": [
            {
                "asset_id": str(asset_id),
                "occurrence_id": str(occurrence_id),
                "published_time": published_time.astimezone(UTC).isoformat(),
            }
            for asset_id, occurrence_id, published_time in sorted(
                attention_first_dependencies,
                key=lambda value: (str(value[0]), str(value[1]), value[2].isoformat()),
            )
        ],
        "attention_policy_version": attention_policy_version,
        "behavior_policy_version": behavior_policy_version,
        "consistency_ids": [str(value) for value in sorted(consistency_ids, key=str)],
        "consistency_policy_version": consistency_policy_version,
        "investor_id": str(investor_id),
        "opinion_ids": [str(value) for value in sorted(opinion_ids, key=str)],
        "opinion_analysis_version": active_analysis_version,
        "portfolio_action_ids": [str(value) for value in sorted(portfolio_action_ids, key=str)],
        "thesis_change_ids": [str(value) for value in sorted(thesis_change_ids, key=str)],
        "thesis_comparison_version": thesis_comparison_version,
        "window_end": window_end.astimezone(UTC).isoformat(),
        "window_start": window_start.astimezone(UTC).isoformat(),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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

    active_analysis_version: str = Field(default="legacy:unspecified", min_length=1, max_length=255)
    thesis_comparison_version: str | None = Field(default=None, max_length=255)
    consistency_policy_version: str | None = Field(default=None, max_length=64)
    attention_policy_version: str = Field(
        default=PRODUCTION_ATTENTION_POLICY_VERSION,
        min_length=1,
        max_length=64,
    )
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
    "build_behavior_snapshot_input_identity",
    "InvestorBehaviorSnapshotCreate",
    "InvestorBehaviorSnapshotResult",
    "InvestorBehaviorSnapshotView",
]
