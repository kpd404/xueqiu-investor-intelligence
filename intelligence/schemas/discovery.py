"""Read-only contracts for deterministic Intelligence Discovery candidates."""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts import IntelligenceEventType, IntelligencePriorityReason


class DiscoveryAssetIdentity(BaseModel):
    """Listing-level identity used by a discovery candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class DiscoveryActivitySummary(BaseModel):
    """Counts of the distinct evidence chain behind one Asset candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_count: int = Field(ge=0)
    signal_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    feed_count: int = Field(ge=0)


class DiscoveryEventSummary(BaseModel):
    """Observable event and priority context, without ranking semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_types: tuple[IntelligenceEventType, ...] = ()
    priority_reasons: tuple[IntelligencePriorityReason, ...] = ()


class DiscoveryTimeline(BaseModel):
    """Fact-time bounds of the ACTIVE FeedItems behind a candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    first_observed_at: AwareDatetime
    latest_observed_at: AwareDatetime


class IntelligenceDiscoveryCandidate(BaseModel):
    """One deterministic, Asset-grouped Discovery V1 projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # One candidate exists per Asset in this non-persisted projection.
    candidate_id: UUID
    asset: DiscoveryAssetIdentity
    activity_summary: DiscoveryActivitySummary
    event_summary: DiscoveryEventSummary
    timeline: DiscoveryTimeline
    discovery_reasons: list[str] = Field(default_factory=list)


class IntelligenceDiscoveryCandidateList(BaseModel):
    """Paginated read response for the Discovery API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[IntelligenceDiscoveryCandidate, ...] = ()
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool


# Compatibility names retained for existing V0 callers.
DiscoveryEvidenceSummary = DiscoveryEventSummary
IntelligenceDiscoveryListResponse = IntelligenceDiscoveryCandidateList


__all__ = [
    "DiscoveryActivitySummary",
    "DiscoveryAssetIdentity",
    "DiscoveryEventSummary",
    "DiscoveryEvidenceSummary",
    "DiscoveryTimeline",
    "IntelligenceDiscoveryCandidate",
    "IntelligenceDiscoveryCandidateList",
    "IntelligenceDiscoveryListResponse",
]
