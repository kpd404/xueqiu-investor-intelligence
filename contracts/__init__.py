"""Layer-neutral data contracts shared across the pipeline."""

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
    CoreProcessingFailureCode,
    CoreProcessingResult,
    CoreProcessingWarning,
    ProcessRawEventCommand,
)
from contracts.raw_event import RawEventDTO, RawEventView, RawEventWriteResult
from contracts.state import (
    InvestorAssetStateSnapshot,
    OpinionTimelineEntry,
    StateReduction,
    StateTransitionType,
    StateUpdateResult,
)

__all__ = [
    "AssetOpinionExtraction",
    "AssetIntelligenceSnapshot",
    "AttentionLevel",
    "CollectionRequest",
    "ConsensusDirection",
    "CoreProcessingFailureCode",
    "CoreProcessingResult",
    "CoreProcessingWarning",
    "ProcessRawEventCommand",
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
    "RawEventDTO",
    "RawEventView",
    "RawEventWriteResult",
    "StateReduction",
    "StateTransitionType",
    "StateUpdateResult",
    "InvestorAssetStateSnapshot",
    "UnresolvedAsset",
]
