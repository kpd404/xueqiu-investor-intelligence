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


class DiscoveryEvidenceSummary(BaseModel):
    """Observable event and priority context, without score or rank semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_types: tuple[IntelligenceEventType, ...] = ()
    priority_reasons: tuple[IntelligencePriorityReason, ...] = ()
    latest_observed_at: AwareDatetime


class IntelligenceDiscoveryCandidate(BaseModel):
    """One deterministic, Asset-grouped Discovery projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The V0 projection has one candidate per Asset, so the stable candidate
    # identity is the Asset identity itself. There is no persisted candidate.
    candidate_id: UUID
    asset_id: UUID
    asset_identity: DiscoveryAssetIdentity
    activity_summary: DiscoveryActivitySummary
    evidence_summary: DiscoveryEvidenceSummary
    discovery_reasons: tuple[str, ...] = ()


class IntelligenceDiscoveryListResponse(BaseModel):
    """Paginated read response for the Discovery API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[IntelligenceDiscoveryCandidate, ...] = ()
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool


__all__ = [
    "DiscoveryActivitySummary",
    "DiscoveryAssetIdentity",
    "DiscoveryEvidenceSummary",
    "IntelligenceDiscoveryCandidate",
    "IntelligenceDiscoveryListResponse",
]
