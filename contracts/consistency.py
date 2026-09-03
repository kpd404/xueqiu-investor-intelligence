"""Provider-neutral contracts for Opinion × Portfolio Action consistency."""

import json
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from contracts.enums import OpinionDirection
from contracts.portfolio import PortfolioActionType

CONSISTENCY_POLICY_VERSION = "opinion-action-consistency-v1"


def utc_now() -> datetime:
    return datetime.now(UTC)


class ConsistencyType(StrEnum):
    POSITIVE_ALIGNMENT = "POSITIVE_ALIGNMENT"
    NEGATIVE_ALIGNMENT = "NEGATIVE_ALIGNMENT"
    NO_DIRECTION = "NO_DIRECTION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class OpinionActionConsistencyCreate(BaseModel):
    """Persisted derived consistency artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID
    opinion_id: UUID
    opinion_direction: OpinionDirection | None
    portfolio_action_id: UUID
    action_type: PortfolioActionType
    consistency_type: ConsistencyType
    confidence: float = Field(ge=0, le=1)
    evidence: dict[str, JsonValue] = Field(default_factory=dict)
    effective_time: AwareDatetime
    calculated_at: AwareDatetime = Field(default_factory=utc_now)
    opinion_analysis_version: str = Field(min_length=1, max_length=255)
    consistency_policy_version: str = Field(
        default=CONSISTENCY_POLICY_VERSION,
        min_length=1,
        max_length=64,
    )
    input_identity: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_input_identity(self) -> "OpinionActionConsistencyCreate":
        expected = json.dumps(
            {
                "opinion_id": str(self.opinion_id),
                "portfolio_action_id": str(self.portfolio_action_id),
                "consistency_policy_version": self.consistency_policy_version,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if self.input_identity != expected:
            raise ValueError("input_identity does not match the consistency identity")
        return self


class OpinionActionConsistencyView(OpinionActionConsistencyCreate):
    id: UUID


class OpinionActionConsistencyResult(BaseModel):
    """Result of evaluating all eligible actions for one Investor × Asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID
    artifact_ids: tuple[UUID, ...]
    unmatched_action_ids: tuple[UUID, ...] = ()
    created_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    calculated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_counts(self) -> "OpinionActionConsistencyResult":
        if self.created_count + self.reused_count != len(self.artifact_ids):
            raise ValueError("consistency counts must match artifact IDs")
        return self


# Domain-facing aliases keep the artifact name discoverable while retaining the
# explicit Opinion × Action contract vocabulary in the canonical definitions.
InvestorActionConsistencyCreate = OpinionActionConsistencyCreate
InvestorActionConsistencyView = OpinionActionConsistencyView
InvestorActionConsistencyResult = OpinionActionConsistencyResult


__all__ = [
    "CONSISTENCY_POLICY_VERSION",
    "ConsistencyType",
    "OpinionActionConsistencyCreate",
    "OpinionActionConsistencyResult",
    "OpinionActionConsistencyView",
    "InvestorActionConsistencyCreate",
    "InvestorActionConsistencyView",
    "InvestorActionConsistencyResult",
]
