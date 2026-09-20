"""HTTP/read contracts for the Intelligence Feed Query Layer."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts import (
    FeedState,
    IntelligenceEventType,
    IntelligencePriorityLevel,
    IntelligencePriorityReason,
)


class FeedAssetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class FeedInvestorIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    name: str = Field(min_length=1, max_length=255)


class IntelligenceFeedResponse(BaseModel):
    """One user-consumable FeedItem projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    priority_id: UUID
    asset: FeedAssetIdentity
    event_type: IntelligenceEventType
    priority_level: IntelligencePriorityLevel
    reason: IntelligencePriorityReason
    title: str
    context: dict[str, object] = Field(default_factory=dict)
    investors: tuple[FeedInvestorIdentity, ...] = ()
    state: FeedState
    observed_at: AwareDatetime
    created_at: AwareDatetime


class IntelligenceFeedListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[IntelligenceFeedResponse, ...] = ()
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool


__all__ = [
    "FeedAssetIdentity",
    "FeedInvestorIdentity",
    "IntelligenceFeedListResponse",
    "IntelligenceFeedResponse",
]
