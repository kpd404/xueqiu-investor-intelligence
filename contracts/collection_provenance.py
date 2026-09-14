"""Source-independent collection provenance contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class CollectionMode(StrEnum):
    """Generic acquisition context shared by source adapters."""

    FEED = "FEED"
    ENTITY_HISTORY = "ENTITY_HISTORY"
    MANUAL_IMPORT = "MANUAL_IMPORT"
    UNKNOWN = "UNKNOWN"


class CollectionTransport(StrEnum):
    """Transport used to obtain a collection observation."""

    BROWSER_CDP = "BROWSER_CDP"
    BROWSER_SESSION = "BROWSER_SESSION"
    HTTP = "HTTP"
    FILE = "FILE"
    UNKNOWN = "UNKNOWN"


class CollectionRunStatus(StrEnum):
    """Lifecycle outcome of a collection run."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class CollectionCoverageStatus(StrEnum):
    """Historical coverage claim, independent from run execution outcome."""

    UNKNOWN = "UNKNOWN"
    COMPLETE = "COMPLETE"


class CollectionIngestDisposition(StrEnum):
    """Whether this run inserted or reused the RawEvent fact."""

    INSERTED = "INSERTED"
    REUSED_EXISTING = "REUSED_EXISTING"


class CollectionRunCreate(BaseModel):
    """Command for creating one collection run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=64)
    adapter_name: str = Field(min_length=1, max_length=128)
    collection_mode: CollectionMode = CollectionMode.UNKNOWN
    transport: CollectionTransport = CollectionTransport.UNKNOWN
    started_at: AwareDatetime = Field(default_factory=utc_now)
    ended_at: AwareDatetime | None = None
    run_status: CollectionRunStatus = CollectionRunStatus.RUNNING
    stop_reason: str | None = Field(default=None, max_length=128)
    coverage_status: CollectionCoverageStatus = CollectionCoverageStatus.UNKNOWN
    requested_window_start: AwareDatetime | None = None
    requested_window_end: AwareDatetime | None = None
    scope_type: str | None = Field(default=None, max_length=128)
    scope_key: str | None = Field(default=None, max_length=255)
    collector_version: str | None = Field(default=None, max_length=128)
    parameters_json: dict[str, JsonValue] | None = None
    summary_json: dict[str, JsonValue] | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_times(self) -> CollectionRunCreate:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must be on or after started_at")
        if (
            self.requested_window_start is not None
            and self.requested_window_end is not None
            and self.requested_window_start > self.requested_window_end
        ):
            raise ValueError("requested collection window is invalid")
        return self


class CollectionRunView(CollectionRunCreate):
    """Read model for one mutable-lifecycle, immutable-history run."""

    id: UUID


class CollectionObservationCreate(BaseModel):
    """Command for attaching one observation to a collection run and RawEvent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection_run_id: UUID
    raw_event_id: UUID
    observed_at: AwareDatetime = Field(default_factory=utc_now)
    ingest_disposition: CollectionIngestDisposition
    observation_sequence: int | None = Field(default=None, ge=0)
    source_page: str | None = Field(default=None, max_length=2048)
    source_context_json: dict[str, JsonValue] | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)


class CollectionObservationView(CollectionObservationCreate):
    """Read model for one run-to-RawEvent provenance edge."""

    id: UUID


class CollectionObservationProvenance(BaseModel):
    """Observation read model enriched with its CollectionRun identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection_observation_id: UUID
    collection_run_id: UUID
    raw_event_id: UUID
    observed_at: AwareDatetime
    ingest_disposition: CollectionIngestDisposition
    observation_sequence: int | None = None
    source_page: str | None = None
    source_context_json: dict[str, JsonValue] | None = None
    source: str
    adapter_name: str
    collection_mode: CollectionMode
    transport: CollectionTransport
    run_status: CollectionRunStatus
    stop_reason: str | None
    coverage_status: CollectionCoverageStatus


class RawEventCollectionProvenance(BaseModel):
    """Traceable collection provenance for one immutable RawEvent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_event_id: UUID
    provenance_available: bool
    observations: tuple[CollectionObservationProvenance, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> RawEventCollectionProvenance:
        if self.provenance_available != bool(self.observations):
            raise ValueError("provenance_available must match observations")
        return self


class CollectionProvenanceCoverageBucket(BaseModel):
    """Coverage counts for one source/mode/run-coverage combination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    collection_mode: CollectionMode
    coverage_status: CollectionCoverageStatus
    raw_event_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)


class CollectionProvenanceCoverage(BaseModel):
    """Read-only provenance coverage audit result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_raw_events: int = Field(ge=0)
    with_provenance: int = Field(ge=0)
    without_provenance: int = Field(ge=0)
    provenance_coverage_percent: float = Field(ge=0, le=100)
    collection_run_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    buckets: tuple[CollectionProvenanceCoverageBucket, ...] = ()

    @model_validator(mode="after")
    def validate_counts(self) -> CollectionProvenanceCoverage:
        if self.with_provenance + self.without_provenance != self.total_raw_events:
            raise ValueError("provenance counts must reconcile to RawEvent total")
        expected_percent = (
            0.0
            if self.total_raw_events == 0
            else self.with_provenance / self.total_raw_events * 100
        )
        if abs(self.provenance_coverage_percent - expected_percent) > 0.000001:
            raise ValueError("provenance coverage percent does not match counts")
        return self


__all__ = [
    "CollectionCoverageStatus",
    "CollectionIngestDisposition",
    "CollectionMode",
    "CollectionObservationCreate",
    "CollectionObservationProvenance",
    "CollectionObservationView",
    "CollectionProvenanceCoverage",
    "CollectionProvenanceCoverageBucket",
    "CollectionRunCreate",
    "CollectionRunStatus",
    "CollectionRunView",
    "CollectionTransport",
    "RawEventCollectionProvenance",
]
