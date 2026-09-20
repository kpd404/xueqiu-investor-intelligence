"""Operational execution and freshness contracts."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class OperationalRefreshTrigger(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"


class OperationalRefreshStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"
    SKIPPED_ALREADY_RUNNING = "SKIPPED_ALREADY_RUNNING"


class OperationalFreshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class OperationalStatusLevel(StrEnum):
    HEALTHY = "HEALTHY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    SOURCE_LIMITED = "SOURCE_LIMITED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class OperationalRefreshRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trigger: OperationalRefreshTrigger
    started_at: AwareDatetime


class OperationalRefreshRunView(OperationalRefreshRunCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    finished_at: AwareDatetime | None = None
    status: OperationalRefreshStatus
    failure_stage: str | None = None
    failure_code: str | None = None
    summary_json: dict[str, object] | None = None
    created_at: AwareDatetime


class OperationalStatusView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: OperationalStatusLevel
    freshness: OperationalFreshness
    freshness_age_seconds: float | None = Field(default=None, ge=0)
    last_refresh_started_at: datetime | None = None
    last_refresh_finished_at: datetime | None = None
    last_successful_refresh_at: datetime | None = None
    latest_status: OperationalRefreshStatus | None = None
    latest_trigger: OperationalRefreshTrigger | None = None
    latest_failure_stage: str | None = None
    latest_failure_code: str | None = None
    next_expected_refresh_at: datetime | None = None
    cdp_requirement: str = "AUTHENTICATED_EDGE_CDP_REQUIRED"


__all__ = [
    "OperationalFreshness",
    "OperationalRefreshRunCreate",
    "OperationalRefreshRunView",
    "OperationalRefreshStatus",
    "OperationalRefreshTrigger",
    "OperationalStatusLevel",
    "OperationalStatusView",
]
