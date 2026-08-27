from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from collectors.xueqiu.browser import XueqiuFollowingFeedDataSource, XueqiuPageDataSource
from collectors.xueqiu.contracts import FollowingFeedBatch
from collectors.xueqiu.errors import NoContent
from collectors.xueqiu.parser import XueqiuPostParser
from contracts import CollectionRequest, FeedCollectionRequest, FeedPostItem, RawEventDTO


class XueqiuFeedAdapter:
    """Expose Following Feed items without persistence or business processing."""

    source = "xueqiu"

    def __init__(self, browser: XueqiuFollowingFeedDataSource) -> None:
        self._browser = browser

    async def collect(self, request: FeedCollectionRequest) -> AsyncIterator[FeedPostItem]:
        batches = await self._browser.fetch_following_feed_batches(request)
        async for item in self.collect_batches(batches, request):
            yield item

    async def collect_batches(
        self,
        batches: Sequence[FollowingFeedBatch],
        request: FeedCollectionRequest,
    ) -> AsyncIterator[FeedPostItem]:
        """Consume already captured batches without performing another browser call."""

        seen_source_event_ids: set[str] = set()
        for batch in batches[: request.max_batches]:
            for item in batch.items:
                if item.source_event_id in seen_source_event_ids:
                    continue
                if request.only_author_ids and item.author_id not in request.only_author_ids:
                    continue
                if not self._within_window(item.published_time, request):
                    continue
                seen_source_event_ids.add(item.source_event_id)
                yield item

    @staticmethod
    def _within_window(published_time: datetime, request: FeedCollectionRequest) -> bool:
        normalized = published_time.astimezone(UTC)
        if request.since is not None and normalized < request.since.astimezone(UTC):
            return False
        return request.until is None or normalized <= request.until.astimezone(UTC)


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
