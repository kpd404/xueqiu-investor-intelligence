"""Layer-neutral data contracts shared across the pipeline."""

from contracts.analysis import (
    AnalysisSpec,
    EventAnalysisCreate,
    EventAnalysisStatus,
    EventAnalysisView,
    StateChangeCreate,
    StateChangeView,
)
from contracts.collection import CollectionRequest
from contracts.enums import (
    AttentionLevel,
    ConsensusDirection,
    EventType,
    OpinionDirection,
    PositionStatus,
)
from contracts.intelligence import (
    AssetIntelligenceSnapshot,
    InvestorStateAggregationInput,
    InvestorStateContribution,
)
from contracts.opinion import (
    AssetOpinionExtraction,
    OpinionCreate,
    OpinionExtractionResult,
    OpinionProcessingResult,
    OpinionProcessingStatus,
    OpinionWriteResult,
    UnresolvedAsset,
)
from contracts.processing import (
    AnalysisProcessingError,
    CoreProcessingFailureCode,
    CoreProcessingResult,
    CoreProcessingWarning,
    ProcessingOutcome,
    ProcessingStage,
    ProcessRawEventCommand,
    RawEventNotFoundError,
)
from contracts.raw_event import RawEventDTO, RawEventView, RawEventWriteResult
from contracts.state import (
    STATE_POLICY_VERSION,
    InvestorAssetStateSnapshot,
    OpinionTimelineEntry,
    StateReduction,
    StateTransitionType,
    StateUpdateResult,
)

__all__ = [
    "AnalysisProcessingError",
    "AnalysisSpec",
    "AssetOpinionExtraction",
    "AssetIntelligenceSnapshot",
    "AttentionLevel",
    "CollectionRequest",
    "ConsensusDirection",
    "CoreProcessingFailureCode",
    "CoreProcessingResult",
    "CoreProcessingWarning",
    "EventAnalysisCreate",
    "EventAnalysisStatus",
    "EventAnalysisView",
    "EventType",
    "OpinionCreate",
    "OpinionDirection",
    "OpinionExtractionResult",
    "OpinionProcessingResult",
    "OpinionProcessingStatus",
    "OpinionTimelineEntry",
    "OpinionWriteResult",
    "PositionStatus",
    "InvestorStateAggregationInput",
    "InvestorStateContribution",
    "ProcessRawEventCommand",
    "ProcessingOutcome",
    "ProcessingStage",
    "RawEventDTO",
    "RawEventNotFoundError",
    "RawEventView",
    "RawEventWriteResult",
    "STATE_POLICY_VERSION",
    "StateChangeCreate",
    "StateChangeView",
    "StateReduction",
    "StateTransitionType",
    "StateUpdateResult",
    "InvestorAssetStateSnapshot",
    "UnresolvedAsset",
]
