from typing import Protocol, runtime_checkable

from contracts import CurrentAuthorEventView, OpinionExtractionResult


@runtime_checkable
class OpinionExtractor(Protocol):
    """Language-understanding port with no persistence responsibilities."""

    async def extract(self, event: CurrentAuthorEventView) -> OpinionExtractionResult: ...
