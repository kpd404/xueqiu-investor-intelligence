from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.analysis import AnalysisSpec
from contracts.intelligence import AssetIntelligenceSnapshot
from contracts.opinion import OpinionProcessingStatus, UnresolvedAsset
from contracts.state import StateUpdateResult


class ProcessRawEventCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    model_version: str | None = Field(default=None, min_length=1, max_length=255)
    analysis_spec: AnalysisSpec | None = None
    as_of: AwareDatetime

    @model_validator(mode="before")
    @classmethod
    def normalize_analysis_spec(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        spec = normalized.get("analysis_spec")
        model_version = normalized.get("model_version")
        if spec is None and model_version is not None:
            normalized["analysis_spec"] = AnalysisSpec.from_model_version(str(model_version))
        elif isinstance(spec, AnalysisSpec) and model_version is None:
            normalized["model_version"] = spec.model_version
        elif isinstance(spec, dict) and model_version is None:
            normalized["model_version"] = spec.get("model_version")
        return normalized

    @model_validator(mode="after")
    def validate_analysis_spec(self) -> "ProcessRawEventCommand":
        if self.analysis_spec is None:
            raise ValueError("analysis_spec or model_version is required")
        if (
            self.model_version is not None
            and self.model_version != self.analysis_spec.model_version
        ):
            raise ValueError("model_version must match analysis_spec.model_version")
        return self

    @property
    def resolved_analysis_spec(self) -> AnalysisSpec:
        if self.analysis_spec is None:
            raise ValueError("analysis_spec is required")
        return self.analysis_spec


class CoreProcessingFailureCode(StrEnum):
    RAW_EVENT_NOT_FOUND = "RAW_EVENT_NOT_FOUND"
    STATE_UPDATE_FAILED = "STATE_UPDATE_FAILED"
    INTELLIGENCE_CALCULATION_FAILED = "INTELLIGENCE_CALCULATION_FAILED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class ProcessingOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_SUCCEEDED = "PARTIALLY_SUCCEEDED"
    RETRYABLE_FAILED = "RETRYABLE_FAILED"
    PERMANENTLY_FAILED = "PERMANENTLY_FAILED"


class ProcessingStage(StrEnum):
    ANALYSIS = "ANALYSIS"
    STATE_UPDATE = "STATE_UPDATE"
    INTELLIGENCE = "INTELLIGENCE"


class RawEventNotFoundError(LookupError):
    """Stable cross-layer error for a missing immutable fact."""


class AnalysisProcessingError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class CoreProcessingWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: CoreProcessingFailureCode
    message: str = Field(min_length=1)
    stage: ProcessingStage
    retryable: bool
    opinion_id: UUID | None = None
    asset_id: UUID | None = None


class CoreProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    model_version: str
    analysis_spec: AnalysisSpec
    as_of: AwareDatetime
    opinion_processing_status: OpinionProcessingStatus
    opinion_ids: tuple[UUID, ...]
    state_updates: tuple[StateUpdateResult, ...]
    affected_asset_ids: tuple[UUID, ...]
    asset_intelligence_snapshots: tuple[AssetIntelligenceSnapshot, ...]
    unresolved_assets: tuple[UnresolvedAsset, ...]
    warnings: tuple[CoreProcessingWarning, ...]
    outcome: ProcessingOutcome
