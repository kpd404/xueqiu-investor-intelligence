"""Investment-understanding contracts and processing components."""

from ai.comparators import (
    MockThesisComparator,
    OpenAICompatibleThesisComparator,
    ThesisComparator,
)
from ai.extractors import (
    MockOpinionExtractor,
    OpenAICompatibleOpinionExtractor,
    OpenAIOpinionExtractor,
    OpinionExtractor,
)
from ai.services import OpinionProcessingService

__all__ = [
    "MockOpinionExtractor",
    "MockThesisComparator",
    "OpenAIOpinionExtractor",
    "OpenAICompatibleOpinionExtractor",
    "OpenAICompatibleThesisComparator",
    "OpinionExtractor",
    "OpinionProcessingService",
    "ThesisComparator",
]
