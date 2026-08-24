from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from contracts import CollectionRequest, RawEventDTO


@runtime_checkable
class SourceAdapter(Protocol):
    """Port implemented by every source-specific collection adapter."""

    source: str

    def collect(self, request: CollectionRequest) -> AsyncIterator[RawEventDTO]: ...
