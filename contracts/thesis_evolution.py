"""Contracts for the query-time Thesis Evolution V0 read model."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.enums import OpinionDirection
from contracts.thesis_change import ThesisChangeType


class ThesisEvolutionCompleteness(StrEnum):
    """Historical completeness of the observed source profile."""

    UNKNOWN = "UNKNOWN"


class ThesisComparisonStatus(StrEnum):
    """Read-model status of the comparison expected for an Opinion."""

    INITIAL_OPINION = "INITIAL_OPINION"
    COMPARISON_AVAILABLE = "COMPARISON_AVAILABLE"
    MISSING_THESIS_COMPARISON = "MISSING_THESIS_COMPARISON"


class ThesisEvolutionDirectionTransition(StrEnum):
    """Deterministic direction transition with strong directions normalized."""

    INITIAL_DIRECTION = "INITIAL_DIRECTION"
    SAME_DIRECTION = "SAME_DIRECTION"
    BULLISH_TO_BEARISH = "BULLISH_TO_BEARISH"
    BEARISH_TO_BULLISH = "BEARISH_TO_BULLISH"
    TO_NEUTRAL = "TO_NEUTRAL"
    FROM_NEUTRAL = "FROM_NEUTRAL"
    OTHER = "OTHER"


class ThesisEvolutionOpinionView(BaseModel):
    """Effective Opinion plus the analysis identity needed for provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opinion_id: UUID
    raw_event_id: UUID
    event_analysis_id: UUID
    investor_id: UUID
    asset_id: UUID
    analysis_version: str = Field(min_length=1, max_length=255)
    published_time: AwareDatetime
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)


class ThesisEvolutionEntry(BaseModel):
    """One Opinion entry with independent direction and thesis semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opinion_id: UUID
    raw_event_id: UUID
    event_analysis_id: UUID
    published_time: AwareDatetime
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)
    thesis_change_id: UUID | None = None
    thesis_change_type: ThesisChangeType | None = None
    thesis_change_time: AwareDatetime | None = None
    thesis_comparison_status: ThesisComparisonStatus
    predecessor_opinion_id: UUID | None = None
    direction_transition: ThesisEvolutionDirectionTransition
    temporal_gap_from_previous: float | None = Field(default=None, ge=0)
    temporal_gap_from_previous_hours: float | None = Field(default=None, ge=0)
    temporal_gap_from_previous_days: float | None = Field(default=None, ge=0)


class ThesisEvolutionTimeline(BaseModel):
    """Observed Investor × Asset Opinion/Thesis timeline for one query window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None
    completeness: ThesisEvolutionCompleteness = ThesisEvolutionCompleteness.UNKNOWN
    opinion_count: int = Field(ge=1)
    thesis_change_count: int = Field(ge=0)
    missing_thesis_change_count: int = Field(ge=0)
    first_opinion_time: AwareDatetime
    latest_opinion_time: AwareDatetime
    entries: tuple[ThesisEvolutionEntry, ...] = Field(min_length=1)
    changed_count: int = Field(ge=0)
    extended_count: int = Field(ge=0)
    reinforced_count: int = Field(ge=0)
    reversal_count: int = Field(ge=0)
    same_direction_change_count: int = Field(ge=0)
    first_attention_time: AwareDatetime | None = None
    attention_to_first_opinion_lag: float | None = None
    attention_to_first_opinion_lag_hours: float | None = None
    attention_to_first_opinion_lag_days: float | None = None

    @model_validator(mode="after")
    def validate_timeline(self) -> "ThesisEvolutionTimeline":
        if self.window_start is not None and self.window_end is not None:
            if self.window_start > self.window_end:
                raise ValueError("window_start must be earlier than or equal to window_end")
        if self.opinion_count != len(self.entries):
            raise ValueError("opinion_count must match entries")
        if self.thesis_change_count != sum(
            item.thesis_change_id is not None for item in self.entries
        ):
            raise ValueError("thesis_change_count must match entries with ThesisChange")
        if self.missing_thesis_change_count != sum(
            item.thesis_comparison_status is ThesisComparisonStatus.MISSING_THESIS_COMPARISON
            for item in self.entries
        ):
            raise ValueError("missing_thesis_change_count must match missing comparison entries")
        if self.first_opinion_time != self.entries[0].published_time:
            raise ValueError("first_opinion_time must match the first entry")
        if self.latest_opinion_time != self.entries[-1].published_time:
            raise ValueError("latest_opinion_time must match the last entry")
        if any(
            left.published_time > right.published_time
            for left, right in zip(self.entries, self.entries[1:], strict=False)
        ):
            raise ValueError("entries must be ordered by published_time")
        return self


__all__ = [
    "ThesisEvolutionCompleteness",
    "ThesisEvolutionDirectionTransition",
    "ThesisEvolutionEntry",
    "ThesisEvolutionOpinionView",
    "ThesisEvolutionTimeline",
    "ThesisComparisonStatus",
]
