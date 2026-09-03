from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.analysis import AnalysisSpec
from contracts.enums import OpinionDirection


class ThesisChangeType(StrEnum):
    """Versioned interpretation categories for an effective Opinion timeline.

    ``NEW_THESIS`` means the first observed thesis in the currently available
    production-effective Opinion history for an Investor x Asset. It does not
    claim that the investor formed that thesis for the first time.
    """

    NEW_THESIS = "NEW_THESIS"
    THESIS_UNCHANGED = "THESIS_UNCHANGED"
    THESIS_REINFORCED = "THESIS_REINFORCED"
    THESIS_EXTENDED = "THESIS_EXTENDED"
    THESIS_CHANGED = "THESIS_CHANGED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ThesisComparisonSpec(BaseModel):
    """Provider-neutral identity for one thesis comparison configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    comparison_version: str = Field(min_length=1, max_length=255)
    provider_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=255)
    prompt_version: str = Field(min_length=1, max_length=255)
    schema_version: str = Field(min_length=1, max_length=255)
    comparison_policy_version: str = Field(min_length=1, max_length=255)

    @classmethod
    def from_analysis_spec(cls, spec: AnalysisSpec) -> "ThesisComparisonSpec":
        return cls(
            comparison_version=spec.analysis_version,
            provider_id=spec.provider_id,
            model_version=spec.model_version,
            prompt_version=spec.prompt_version,
            schema_version=spec.schema_version,
            comparison_policy_version=spec.analysis_policy_version,
        )


class ThesisOpinionView(BaseModel):
    """One effective Opinion plus its attribution-safe source text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opinion_id: UUID
    event_id: UUID
    investor_id: UUID
    asset_id: UUID
    analysis_version: str = Field(min_length=1, max_length=255)
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    thesis: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    time_horizon: str | None = Field(default=None, max_length=64)
    published_time: AwareDatetime
    generated_time: AwareDatetime
    current_author_text: str


class ThesisComparisonInput(BaseModel):
    """Input permitted for comparing two effective Opinions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    asset_name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    previous: ThesisOpinionView | None = None
    current: ThesisOpinionView

    @model_validator(mode="after")
    def validate_pair_identity(self) -> "ThesisComparisonInput":
        if self.current.asset_id != self.asset_id:
            raise ValueError("current Opinion must belong to the comparison asset")
        if self.previous is not None:
            if self.previous.asset_id != self.asset_id:
                raise ValueError("previous Opinion must belong to the comparison asset")
            if self.previous.investor_id != self.current.investor_id:
                raise ValueError("Opinion pair must belong to one investor")
            if self.previous.published_time > self.current.published_time:
                raise ValueError("previous Opinion must not be after current Opinion")
        return self


class ThesisComparisonResult(BaseModel):
    """Structured comparator output; no persistence or identity fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    change_type: ThesisChangeType
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=2000)
    evidence: tuple[str, ...] = ()


@runtime_checkable
class ThesisComparator(Protocol):
    """Language-understanding port for comparing two effective Opinions."""

    @property
    def comparison_spec(self) -> ThesisComparisonSpec: ...

    async def compare(self, input_data: ThesisComparisonInput) -> ThesisComparisonResult: ...


class ThesisChangeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID
    previous_opinion_id: UUID | None = None
    current_opinion_id: UUID
    previous_event_id: UUID | None = None
    current_event_id: UUID
    effective_time: AwareDatetime
    change_type: ThesisChangeType
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=2000)
    evidence: tuple[str, ...] = ()
    opinion_analysis_version: str = Field(min_length=1, max_length=255)
    comparison_version: str = Field(min_length=1, max_length=255)
    calculated_at: AwareDatetime
    input_identity: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_provenance(self) -> "ThesisChangeCreate":
        if self.previous_opinion_id is None and self.previous_event_id is not None:
            raise ValueError("previous_event_id requires previous_opinion_id")
        if self.previous_opinion_id is not None and self.previous_event_id is None:
            raise ValueError("previous_opinion_id requires previous_event_id")
        return self


class ThesisChangeView(ThesisChangeCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID


class ThesisChangeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    thesis_change_id: UUID
    investor_id: UUID
    asset_id: UUID
    previous_opinion_id: UUID | None
    current_opinion_id: UUID
    change_type: ThesisChangeType
    confidence: float = Field(ge=0, le=1)
    comparison_version: str = Field(min_length=1, max_length=255)
    effective_time: AwareDatetime
    created: bool
