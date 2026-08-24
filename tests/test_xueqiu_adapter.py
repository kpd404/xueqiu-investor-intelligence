import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from collectors.xueqiu import NoContent, XueqiuAdapter
from contracts import CollectionRequest, RawEventDTO

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "xueqiu" / "status_response.json"


class FixtureBrowser:
    async def fetch_status_payloads(self, request: CollectionRequest) -> list[dict[str, object]]:
        return [json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))]


async def collect_all(adapter: XueqiuAdapter, request: CollectionRequest) -> list[RawEventDTO]:
    return [event async for event in adapter.collect(request)]


def test_collection_window_excludes_posts_outside_since() -> None:
    request = CollectionRequest(
        investor_id=uuid4(),
        platform_user_id="700001",
        homepage_url="https://xueqiu.com/u/700001",
        since=datetime(2026, 8, 24, 7, 0, tzinfo=UTC),
        limit=5,
    )

    with pytest.raises(NoContent):
        asyncio.run(collect_all(XueqiuAdapter(FixtureBrowser()), request))


def test_collection_window_includes_post_at_or_before_until() -> None:
    request = CollectionRequest(
        investor_id=uuid4(),
        platform_user_id="700001",
        homepage_url="https://xueqiu.com/u/700001",
        until=datetime(2026, 8, 24, 6, 18, tzinfo=UTC),
        limit=1,
    )

    events = asyncio.run(collect_all(XueqiuAdapter(FixtureBrowser()), request))

    assert len(events) == 1
    assert events[0].published_time == request.until
