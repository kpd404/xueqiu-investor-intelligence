"""Contracts for the query-time Observed Attention Propagation V0 read model.

These contracts describe temporal order inside the monitored sample only. They
do not assert history completeness, causality, influence, source, or absence.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.attention import AttentionEvidenceType
from contracts.enums import OpinionDirection
from contracts.thesis_change import ThesisChangeType


class ObservedAttentionCompleteness(StrEnum):
    """Completeness of the historical source profile for this read model."""

    UNKNOWN = "UNKNOWN"


class ObservedAttentionDirectionRelation(StrEnum):
    """Presence-safe comparison of the first effective Opinions."""

    SAME_DIRECTION = "SAME_DIRECTION"
    OPPOSITE_DIRECTION = "OPPOSITE_DIRECTION"
    NEUTRAL_OR_MIXED = "NEUTRAL_OR_MIXED"
    OPINION_MISSING = "OPINION_MISSING"


class ObservedAttentionTemporalRelation(StrEnum):
    """Whether an observation is later or timestamp-tied to the anchor."""

    OBSERVED_LATER = "OBSERVED_LATER"
    SIMULTANEOUS_OBSERVATION = "SIMULTANEOUS_OBSERVATION"


class ObservedAttentionObservation(BaseModel):
    """One effective AttentionOccurrence with traceable optional context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    investor_name: str = Field(min_length=1, max_length=255)
    attention_occurrence_id: UUID
    raw_event_id: UUID
    published_time: AwareDatetime
    evidence_types: tuple[AttentionEvidenceType, ...] = Field(min_length=1)
    lag_seconds: float | None = Field(default=None, ge=0)
    lag_hours: float | None = Field(default=None, ge=0)
    lag_days: float | None = Field(default=None, ge=0)
    first_effective_opinion_id: UUID | None = None
    first_opinion_time: AwareDatetime | None = None
    first_opinion_direction: OpinionDirection | None = None
    latest_thesis_change_type: ThesisChangeType | None = None
    latest_thesis_change_time: AwareDatetime | None = None


class ObservedAttentionSequence(BaseModel):
    """The monitored-sample first-observed order for one Asset and window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    window_start: AwareDatetime
    window_end: AwareDatetime
    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    investor_count: int = Field(ge=1)
    occurrence_count: int = Field(ge=1)
    first_observed: ObservedAttentionObservation
    later_observations: tuple[ObservedAttentionObservation, ...] = ()

    @model_validator(mode="after")
    def validate_sequence(self) -> "ObservedAttentionSequence":
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        observations = (self.first_observed, *self.later_observations)
        if self.investor_count != len(observations):
            raise ValueError("investor_count must match the distinct observation count")
        if self.occurrence_count < self.investor_count:
            raise ValueError("occurrence_count must include at least one occurrence per investor")
        investor_ids = [item.investor_id for item in observations]
        if len(set(investor_ids)) != len(investor_ids):
            raise ValueError("a sequence can contain only one first observation per investor")
        for item in observations:
            if not self.window_start <= item.published_time <= self.window_end:
                raise ValueError("observations must fall inside the requested window")
        if any(
            left.published_time > right.published_time
            for left, right in zip(observations, observations[1:], strict=False)
        ):
            raise ValueError("later observations must be ordered by published_time")
        return self


class ObservedAttentionEdge(BaseModel):
    """An anchor-to-later observation edge derived from a sequence.

    When temporal_relation is SIMULTANEOUS_OBSERVATION, the endpoint fields
    are a stable serialization of a timestamp tie, not a temporal or causal
    ordering.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    window_start: AwareDatetime
    window_end: AwareDatetime
    completeness: ObservedAttentionCompleteness = ObservedAttentionCompleteness.UNKNOWN
    earliest_observed_investor_id: UUID
    earliest_observed_investor_name: str = Field(min_length=1, max_length=255)
    later_observed_investor_id: UUID
    later_observed_investor_name: str = Field(min_length=1, max_length=255)
    earliest_time: AwareDatetime
    later_time: AwareDatetime
    lag_seconds: float = Field(ge=0)
    lag_hours: float = Field(ge=0)
    lag_days: float = Field(ge=0)
    earliest_evidence_types: tuple[AttentionEvidenceType, ...] = Field(min_length=1)
    later_evidence_types: tuple[AttentionEvidenceType, ...] = Field(min_length=1)
    direction_relation: ObservedAttentionDirectionRelation
    temporal_relation: ObservedAttentionTemporalRelation
    earliest_attention_occurrence_id: UUID
    later_attention_occurrence_id: UUID
    earliest_raw_event_id: UUID
    later_raw_event_id: UUID
    earliest_first_effective_opinion_id: UUID | None = None
    earliest_first_opinion_time: AwareDatetime | None = None
    earliest_first_opinion_direction: OpinionDirection | None = None
    later_first_effective_opinion_id: UUID | None = None
    later_first_opinion_time: AwareDatetime | None = None
    later_first_opinion_direction: OpinionDirection | None = None
    earliest_latest_thesis_change_type: ThesisChangeType | None = None
    earliest_latest_thesis_change_time: AwareDatetime | None = None
    later_latest_thesis_change_type: ThesisChangeType | None = None
    later_latest_thesis_change_time: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_edge(self) -> "ObservedAttentionEdge":
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if not self.window_start <= self.earliest_time <= self.window_end:
            raise ValueError("earliest_time must fall inside the requested window")
        if not self.window_start <= self.later_time <= self.window_end:
            raise ValueError("later_time must fall inside the requested window")
        if self.temporal_relation is ObservedAttentionTemporalRelation.SIMULTANEOUS_OBSERVATION:
            if self.earliest_time != self.later_time or self.lag_seconds != 0:
                raise ValueError("simultaneous observations must have equal times and zero lag")
        elif self.later_time <= self.earliest_time:
            raise ValueError("a later observation must have a strictly positive time lag")
        return self


__all__ = [
    "ObservedAttentionCompleteness",
    "ObservedAttentionDirectionRelation",
    "ObservedAttentionEdge",
    "ObservedAttentionObservation",
    "ObservedAttentionSequence",
    "ObservedAttentionTemporalRelation",
]
