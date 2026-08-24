"""Layer-neutral data contracts shared across the pipeline."""

from contracts.collection import CollectionRequest
from contracts.enums import EventType, OpinionDirection
from contracts.opinion import (
    AssetOpinionExtraction,
    OpinionCreate,
    OpinionExtractionResult,
    OpinionProcessingResult,
    OpinionProcessingStatus,
    OpinionWriteResult,
    UnresolvedAsset,
)
from contracts.raw_event import RawEventDTO, RawEventView, RawEventWriteResult

__all__ = [
    "AssetOpinionExtraction",
    "CollectionRequest",
    "EventType",
    "OpinionCreate",
    "OpinionDirection",
    "OpinionExtractionResult",
    "OpinionProcessingResult",
    "OpinionProcessingStatus",
    "OpinionWriteResult",
    "RawEventDTO",
    "RawEventView",
    "RawEventWriteResult",
    "UnresolvedAsset",
]
