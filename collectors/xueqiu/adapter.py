from collections.abc import AsyncIterator
from datetime import UTC, datetime

from collectors.xueqiu.browser import XueqiuPageDataSource
from collectors.xueqiu.errors import NoContent
from collectors.xueqiu.parser import XueqiuPostParser
from contracts import CollectionRequest, RawEventDTO


class XueqiuAdapter:
    source = "xueqiu"

    def __init__(
        self,
        browser: XueqiuPageDataSource,
        parser: XueqiuPostParser | None = None,
        *,
        default_limit: int = 5,
    ) -> None:
        self._browser = browser
        self._parser = parser or XueqiuPostParser()
        self._default_limit = default_limit

    async def collect(self, request: CollectionRequest) -> AsyncIterator[RawEventDTO]:
        payloads = await self._browser.fetch_status_payloads(request)
        posts = self._parser.parse_payloads(
            payloads,
            expected_user_id=request.platform_user_id,
            now=request.requested_at,
        )
        filtered = [post for post in posts if self._within_window(post.published_time, request)]
        limit = request.limit or self._default_limit
        selected = filtered[:limit]
        if not selected:
            raise NoContent("no original Xueqiu posts matched this collection request")

        for post in selected:
            yield RawEventDTO.build(
                investor_id=request.investor_id,
                event_type=post.event_type,
                source=self.source,
                url=post.url,
                published_time=post.published_time,
                content=post.content,
                raw_data=post.raw_data,
            )

    @staticmethod
    def _within_window(published_time: datetime, request: CollectionRequest) -> bool:
        normalized = published_time.astimezone(UTC)
        if request.since is not None and normalized < request.since.astimezone(UTC):
            return False
        return request.until is None or normalized <= request.until.astimezone(UTC)
