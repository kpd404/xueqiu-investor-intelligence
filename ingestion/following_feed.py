from collections.abc import AsyncIterable, Iterable, Mapping
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from contracts import FeedCollectionRequest, FeedPostItem, RawEventDTO, RawEventWriteResult
from database.repositories import InvestorRepository, RawEventRepository


class FeedItemSource(Protocol):
    def collect(self, request: FeedCollectionRequest) -> AsyncIterable[FeedPostItem]: ...


class FeedIngestionResult(BaseModel):
    """Persistence result without exposing SQLAlchemy entities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_ids: tuple[UUID, ...]
    created_investor_ids: tuple[UUID, ...]
    reused_investor_ids: tuple[UUID, ...]
    event_results: tuple[RawEventWriteResult, ...]

    @property
    def created_investor_count(self) -> int:
        return len(self.created_investor_ids)

    @property
    def reused_investor_count(self) -> int:
        return len(self.reused_investor_ids)

    @property
    def inserted_event_count(self) -> int:
        return sum(result.created for result in self.event_results)

    @property
    def duplicate_event_count(self) -> int:
        return len(self.event_results) - self.inserted_event_count

    @property
    def event_ids(self) -> tuple[UUID, ...]:
        return tuple(result.event_id for result in self.event_results)


class FeedIngestionService:
    """Map source-neutral feed items to Investors and append-only RawEvents."""

    source = "xueqiu"

    def __init__(
        self,
        session: Session,
        *,
        investor_repository: InvestorRepository | None = None,
        raw_event_repository: RawEventRepository | None = None,
    ) -> None:
        self._session = session
        self._investors = investor_repository or InvestorRepository(session)
        self._raw_events = raw_event_repository or RawEventRepository(session)

    async def ingest(
        self,
        items: AsyncIterable[FeedPostItem] | Iterable[FeedPostItem],
        *,
        only_author_ids: Iterable[str] = (),
    ) -> FeedIngestionResult:
        allowlist = frozenset(author_id.strip() for author_id in only_author_ids)
        investor_ids: list[UUID] = []
        created_investor_ids: list[UUID] = []
        reused_investor_ids: list[UUID] = []
        event_results: list[RawEventWriteResult] = []
        seen_investors: set[UUID] = set()

        async def persist(item: FeedPostItem) -> None:
            if allowlist and item.author_id not in allowlist:
                return
            investor, created = self._investors.get_or_create(
                platform=self.source,
                platform_user_id=item.author_id,
                name=self._author_name(item),
            )
            result = self._persist_item(item, investor.id)
            event_results.append(result)
            if investor.id in seen_investors:
                return
            seen_investors.add(investor.id)
            investor_ids.append(investor.id)
            (created_investor_ids if created else reused_investor_ids).append(investor.id)

        if hasattr(items, "__aiter__"):
            async for item in items:  # type: ignore[union-attr]
                await persist(item)
        else:
            for item in items:
                await persist(item)

        return FeedIngestionResult(
            investor_ids=tuple(investor_ids),
            created_investor_ids=tuple(created_investor_ids),
            reused_investor_ids=tuple(reused_investor_ids),
            event_results=tuple(event_results),
        )

    async def ingest_feed(
        self, adapter: FeedItemSource, request: FeedCollectionRequest
    ) -> FeedIngestionResult:
        return await self.ingest(adapter.collect(request), only_author_ids=request.only_author_ids)

    def _persist_item(self, item: FeedPostItem, investor_id: UUID) -> RawEventWriteResult:
        dto = RawEventDTO.build(
            investor_id=investor_id,
            event_type=item.event_type,
            source=self.source,
            url=item.url or f"https://xueqiu.com/{item.author_id}/{item.source_event_id}",
            published_time=item.published_time,
            content=item.content,
            raw_data=self._raw_data(item),
        )
        try:
            result = self._raw_events.add_if_absent(dto)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return result

    @staticmethod
    def _raw_data(item: FeedPostItem) -> dict[str, object]:
        raw_data = dict(item.raw_data)
        raw_data["source_event_id"] = item.source_event_id
        raw_data["author_id"] = item.author_id
        raw_data["event_type"] = item.event_type.value
        raw_data["post_kind"] = item.post_kind.value
        return raw_data

    @staticmethod
    def _author_name(item: FeedPostItem) -> str:
        for key in ("screen_name", "author_name", "user_name"):
            value = item.raw_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:255]
        user = item.raw_data.get("user")
        if isinstance(user, Mapping):
            value = user.get("screen_name")
            if isinstance(value, str) and value.strip():
                return value.strip()[:255]
        return item.author_id[:255]
