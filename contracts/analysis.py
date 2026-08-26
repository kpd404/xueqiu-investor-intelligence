from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class AnalysisSpec(BaseModel):
    """Immutable identity of one deterministic analysis configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_version: str = Field(min_length=1, max_length=255)
    model_version: str = Field(min_length=1, max_length=255)
    prompt_version: str = Field(min_length=1, max_length=255)
    schema_version: str = Field(min_length=1, max_length=255)

    @field_validator("analysis_version", "model_version", "prompt_version", "schema_version")
    @classmethod
    def normalize_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("analysis versions must not be blank")
        return normalized

    @classmethod
    def from_model_version(cls, model_version: str) -> "AnalysisSpec":
        """Build a legacy-compatible spec for pre-1F callers."""

        normalized = model_version.strip()
        if not normalized:
            raise ValueError("model_version must not be blank")
        return cls(
            analysis_version=f"legacy:{normalized}",
            model_version=normalized,
            prompt_version="legacy:unspecified",
            schema_version="opinion-schema-v1",
        )


class EventAnalysisStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NO_OPINION = "NO_OPINION"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    FAILED = "FAILED"


class EventAnalysisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    spec: AnalysisSpec
    status: EventAnalysisStatus
    investment_related: bool
    generated_time: AwareDatetime
    calculated_at: AwareDatetime = Field(default_factory=utc_now)
    confidence: float = Field(ge=0, le=1)
    structured_output: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=255)


class EventAnalysisView(EventAnalysisCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID


class StateChangeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID
    transition_type: str = Field(min_length=1, max_length=64)
    effective_time: AwareDatetime
    calculated_at: AwareDatetime = Field(default_factory=utc_now)
    before: dict[str, Any] | None
    after: dict[str, Any]
    triggering_opinion_id: UUID
    source_event_ids: tuple[UUID, ...]
    state_policy_version: str = Field(min_length=1, max_length=64)


class StateChangeView(StateChangeCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
