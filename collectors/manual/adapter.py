from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from pydantic import JsonValue

from contracts import CollectionRequest, EventType, RawEventDTO


@dataclass(frozen=True, slots=True)
class ManualImportAdapter:
    """Normalize one user-supplied observation without persistence concerns."""

    content: str
    published_time: datetime
    url: str
    event_type: EventType = EventType.POST
    raw_data: Mapping[str, JsonValue] = field(default_factory=dict)

    source: ClassVar[str] = "manual"

    async def collect(self, request: CollectionRequest) -> AsyncIterator[RawEventDTO]:
        raw_data = dict(self.raw_data)
        raw_data.setdefault("platform_user_id", request.platform_user_id)
        if request.homepage_url is not None:
            raw_data.setdefault("homepage_url", request.homepage_url)

        yield RawEventDTO.build(
            investor_id=request.investor_id,
            event_type=self.event_type,
            source=self.source,
            url=self.url,
            published_time=self.published_time,
            content=self.content,
            raw_data=raw_data,
        )
