"""Contracts for the read-side Intelligence Feed projection."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.intelligence_event import IntelligenceEventType
from contracts.intelligence_priority import IntelligencePriorityReason

THESIS_LIFECYCLE_CONTEXT_KEY = "_thesis_lifecycle"


def feed_display_context(context: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in context.items() if key != THESIS_LIFECYCLE_CONTEXT_KEY}


def preserve_thesis_lifecycle_context(
    previous: dict[str, object],
    display: dict[str, object],
) -> dict[str, object]:
    result = feed_display_context(display)
    if THESIS_LIFECYCLE_CONTEXT_KEY in previous:
        result[THESIS_LIFECYCLE_CONTEXT_KEY] = deepcopy(previous[THESIS_LIFECYCLE_CONTEXT_KEY])
    return result


@dataclass(frozen=True)
class ThesisSourceFact:
    raw_event_id: UUID
    published_time: datetime


class FeedState(StrEnum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    RESOLVED = "RESOLVED"


class FeedItemCreate(BaseModel):
    """One presentation item derived from one existing Priority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    priority_id: UUID
    asset_id: UUID
    event_type: IntelligenceEventType
    title: str = Field(min_length=1, max_length=255)
    context: dict[str, object] = Field(default_factory=dict)
    reason: IntelligencePriorityReason
    state: FeedState = FeedState.NEW
    observed_at: AwareDatetime
    created_at: AwareDatetime


class FeedItem(FeedItemCreate):
    id: UUID


class IntelligenceFeedGenerationResult(BaseModel):
    """Result of Feed dry-run or idempotent materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[FeedItemCreate, ...] = ()
    items: tuple[FeedItem, ...] = ()
    created_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    dry_run: bool

    @model_validator(mode="after")
    def validate_counts(self) -> IntelligenceFeedGenerationResult:
        if self.dry_run and self.items and len(self.items) != self.reused_count:
            raise ValueError("dry-run items must contain only reused FeedItems")
        return self


__all__ = ["FeedItem", "FeedItemCreate", "FeedState", "IntelligenceFeedGenerationResult"]
