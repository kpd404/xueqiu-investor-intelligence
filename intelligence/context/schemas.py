"""Contracts for fact-time Intelligence Context comparisons."""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ContextAssetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class ActivityContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_signal_count: int = Field(ge=0)
    previous_signal_count: int = Field(ge=0)
    change_description: str = Field(min_length=1)


class InvestorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_investor_count: int = Field(ge=0)
    previous_investor_count: int = Field(ge=0)
    new_investors: list[UUID] = Field(default_factory=list)
    returning_investors: list[UUID] = Field(default_factory=list)


class AttentionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_attention_count: int = Field(ge=0)
    historical_attention_count: int = Field(ge=0)
    change_description: str = Field(min_length=1)


class ThesisContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_thesis_changes: int = Field(ge=0)
    historical_thesis_changes: int = Field(ge=0)
    direction_changes: list[str] = Field(default_factory=list)


class CrossInvestorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_state: str | None = None
    historical_state: str | None = None


class TimelineContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    first_observed_at: AwareDatetime | None = None
    latest_observed_at: AwareDatetime | None = None
    current_window_start: AwareDatetime
    current_window_end: AwareDatetime
    previous_window_start: AwareDatetime
    previous_window_end: AwareDatetime


class IntelligenceContextView(BaseModel):
    """Fact-only current/previous comparison for one Asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset: ContextAssetIdentity
    activity_context: ActivityContext
    investor_context: InvestorContext
    attention_context: AttentionContext
    thesis_context: ThesisContext
    cross_investor_context: CrossInvestorContext
    timeline_context: TimelineContext
    limitations: list[str] = Field(default_factory=list)


__all__ = [
    "ActivityContext",
    "AttentionContext",
    "ContextAssetIdentity",
    "CrossInvestorContext",
    "IntelligenceContextView",
    "InvestorContext",
    "ThesisContext",
    "TimelineContext",
]
