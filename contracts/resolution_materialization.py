from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.analysis import EventAnalysisStatus
from contracts.asset_resolution import AssetResolutionStatus

ResolutionEntrySource = Literal["EXTRACTED_OPINION", "DIRECT_UNRESOLVED_HINT"]


class CurrentAnalysisResolutionEntry(BaseModel):
    """One query-time resolution result from an immutable Analysis payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_kind: ResolutionEntrySource
    source_mention_index: int = Field(ge=0)
    extracted_name: str = Field(min_length=1, max_length=255)
    extracted_market: str | None = Field(default=None, max_length=32)
    extracted_symbol: str | None = Field(default=None, max_length=64)
    outcome: AssetResolutionStatus
    asset_id: UUID | None = None
    resolved_market: str | None = Field(default=None, max_length=32)
    resolved_symbol: str | None = Field(default=None, max_length=64)
    resolution_basis: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=255)
    candidate_asset_ids: tuple[UUID, ...] = ()
    existing_opinion_id: UUID | None = None
    materializable: bool = False
    materialization_blocked_reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> "CurrentAnalysisResolutionEntry":
        if self.outcome is AssetResolutionStatus.RESOLVED and self.asset_id is None:
            raise ValueError("resolved entry must include asset_id")
        if self.outcome is not AssetResolutionStatus.RESOLVED:
            if self.asset_id is not None:
                raise ValueError("non-resolved entry cannot include asset_id")
            if self.existing_opinion_id is not None:
                raise ValueError("non-resolved entry cannot include existing_opinion_id")
            if self.materializable:
                raise ValueError("non-resolved entry cannot be materializable")
        if self.materializable:
            if self.source_kind != "EXTRACTED_OPINION":
                raise ValueError("direct unresolved hints cannot be materialized")
            if self.existing_opinion_id is not None:
                raise ValueError("existing Opinion cannot be materialized")
        if len(set(self.candidate_asset_ids)) != len(self.candidate_asset_ids):
            raise ValueError("candidate_asset_ids must be unique")
        return self


class CurrentAnalysisResolution(BaseModel):
    """Current deterministic resolution projection over one immutable Analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: UUID
    event_id: UUID
    persisted_analysis_status: EventAnalysisStatus
    extracted_opinion_count: int = Field(ge=0)
    direct_unresolved_hint_count: int = Field(ge=0)
    currently_resolved_count: int = Field(ge=0)
    currently_unresolved_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    ambiguous_count: int = Field(ge=0)
    existing_opinion_count: int = Field(ge=0)
    materializable_opinion_count: int = Field(ge=0)
    entries: tuple[CurrentAnalysisResolutionEntry, ...] = ()


class OpinionMaterializationPlan(BaseModel):
    """Read-only plan for materializing missing Opinions from resolved extractions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: UUID
    event_id: UUID
    persisted_analysis_status: EventAnalysisStatus
    projection: CurrentAnalysisResolution
    materializable_entry_indexes: tuple[int, ...] = ()
    already_materialized_opinion_ids: tuple[UUID, ...] = ()
    calculated_at: AwareDatetime
