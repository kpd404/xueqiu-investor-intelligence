import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator

ANALYSIS_POLICY_VERSION = "opinion-analysis-v2"
LEGACY_PROVIDER_ID = "legacy"


def utc_now() -> datetime:
    return datetime.now(UTC)


class AnalysisSpec(BaseModel):
    """Immutable identity of one deterministic analysis configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_version: str = Field(min_length=1, max_length=255)
    model_version: str = Field(min_length=1, max_length=255)
    prompt_version: str = Field(min_length=1, max_length=255)
    schema_version: str = Field(min_length=1, max_length=255)
    provider_id: str = Field(default=LEGACY_PROVIDER_ID, min_length=1, max_length=128)
    analysis_policy_version: str = Field(default="legacy:unspecified", min_length=1, max_length=255)

    @field_validator(
        "analysis_version",
        "model_version",
        "prompt_version",
        "schema_version",
        "provider_id",
        "analysis_policy_version",
    )
    @classmethod
    def normalize_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("analysis versions must not be blank")
        return normalized

    @classmethod
    def for_provider(
        cls,
        *,
        provider_id: str,
        model_version: str,
        prompt_version: str,
        schema_version: str,
        analysis_policy_version: str = ANALYSIS_POLICY_VERSION,
    ) -> "AnalysisSpec":
        """Build a stable identity from semantic analysis inputs only."""

        payload = {
            "analysis_policy_version": analysis_policy_version.strip(),
            "model": model_version.strip(),
            "prompt_version": prompt_version.strip(),
            "provider_id": provider_id.strip(),
            "schema_version": schema_version.strip(),
        }
        if not all(payload.values()):
            raise ValueError("analysis identity fields must not be blank")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(
            analysis_version=f"{payload['analysis_policy_version']}:{digest}",
            model_version=payload["model"],
            prompt_version=payload["prompt_version"],
            schema_version=payload["schema_version"],
            provider_id=payload["provider_id"],
            analysis_policy_version=payload["analysis_policy_version"],
        )

    @property
    def identity_payload(self) -> dict[str, str]:
        """Semantic fields used to identify one analysis configuration."""

        return {
            "analysis_policy_version": self.analysis_policy_version,
            "model": self.model_version,
            "prompt_version": self.prompt_version,
            "provider_id": self.provider_id,
            "schema_version": self.schema_version,
        }

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
    provider_metadata: dict[str, JsonValue] = Field(default_factory=dict)
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
