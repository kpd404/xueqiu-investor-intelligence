from typing import Protocol, runtime_checkable

from contracts import OpinionExtractionResult, RawEventView


@runtime_checkable
class OpinionExtractor(Protocol):
    """Language-understanding port with no persistence responsibilities."""

    async def extract(self, event: RawEventView) -> OpinionExtractionResult: ...
