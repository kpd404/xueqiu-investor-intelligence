import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from collectors.xueqiu import XueqiuFeedAdapter
from collectors.xueqiu.contracts import FollowingFeedBatch
from contracts import EventType, FeedCollectionRequest, FeedPostItem, FeedPostKind
from database.models import Investor, RawEvent
from ingestion import FeedIngestionService

OBSERVED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)


def make_item(
    source_event_id: str,
    author_id: str,
    *,
    post_kind: FeedPostKind = FeedPostKind.ORIGINAL,
    event_type: EventType = EventType.POST,
    content: str | None = None,
    published_time: datetime | None = None,
) -> FeedPostItem:
    raw_data: dict[str, object] = {
        "user": {"id": author_id, "screen_name": f"screen-{author_id}"},
        "source_event_id": source_event_id,
    }
    if post_kind is FeedPostKind.REPOST:
        raw_data.update(
            {
                "retweet_status_id": "original-status",
                "retweeted_status": {
                    "id": "original-status",
                    "text": "原帖内容，不应进入 RawEvent.content",
                },
            }
        )
    return FeedPostItem(
        source_event_id=source_event_id,
        author_id=author_id,
        event_type=event_type,
        post_kind=post_kind,
        url=f"https://xueqiu.com/{author_id}/{source_event_id}",
        published_time=published_time or OBSERVED_AT,
        content=content or f"当前作者文本-{source_event_id}",
        raw_data=raw_data,
    )


def seed_three_posts() -> list[FeedPostItem]:
    return [
        make_item("event-a", "author-a"),
        make_item(
            "event-b",
            "author-a",
            post_kind=FeedPostKind.REPOST,
            content="我的评论",
            published_time=OBSERVED_AT + timedelta(minutes=1),
        ),
        make_item(
            "event-c",
            "author-b",
            post_kind=FeedPostKind.COLUMN,
            event_type=EventType.ARTICLE,
            published_time=OBSERVED_AT + timedelta(minutes=2),
        ),
    ]


def test_following_feed_ingestion_creates_investors_and_raw_events(db_session: Session) -> None:
    items = seed_three_posts()
    service = FeedIngestionService(db_session)

    first = asyncio.run(service.ingest(items))

    assert first.created_investor_count == 2
    assert first.reused_investor_count == 0
    assert first.inserted_event_count == 3
    assert first.duplicate_event_count == 0
    assert db_session.scalar(select(func.count()).select_from(Investor)) == 2
    assert db_session.scalar(select(func.count()).select_from(RawEvent)) == 3

    stored_repost = db_session.scalar(
        select(RawEvent).where(RawEvent.raw_data["source_event_id"].as_string() == "event-b")
    )
    assert stored_repost is not None
    assert stored_repost.content == "我的评论"
    assert stored_repost.raw_data["source_event_id"] == "event-b"
    assert stored_repost.raw_data["post_kind"] == FeedPostKind.REPOST.value
    assert stored_repost.raw_data["retweeted_status"]["text"] == (
        "原帖内容，不应进入 RawEvent.content"
    )

    stored_column = db_session.scalar(
        select(RawEvent).where(RawEvent.raw_data["source_event_id"].as_string() == "event-c")
    )
    assert stored_column is not None
    assert stored_column.event_type is EventType.ARTICLE
    assert stored_column.raw_data["post_kind"] == FeedPostKind.COLUMN.value


def test_repeated_following_feed_ingestion_is_idempotent(db_session: Session) -> None:
    items = seed_three_posts()
    service = FeedIngestionService(db_session)

    asyncio.run(service.ingest(items))
    second = asyncio.run(service.ingest(items))

    assert second.created_investor_count == 0
    assert second.reused_investor_count == 2
    assert second.inserted_event_count == 0
    assert second.duplicate_event_count == 3
    assert db_session.scalar(select(func.count()).select_from(Investor)) == 2
    assert db_session.scalar(select(func.count()).select_from(RawEvent)) == 3


def test_existing_investor_is_reused(db_session: Session) -> None:
    existing = Investor(
        name="Existing Investor",
        platform="xueqiu",
        platform_user_id="author-a",
    )
    db_session.add(existing)
    db_session.commit()

    result = asyncio.run(
        FeedIngestionService(db_session).ingest([make_item("event-a", "author-a")])
    )

    assert result.created_investor_count == 0
    assert result.reused_investor_count == 1
    assert db_session.scalar(select(func.count()).select_from(Investor)) == 1


class FixtureFollowingBrowser:
    def __init__(self, items: tuple[FeedPostItem, ...]) -> None:
        self._batch = FollowingFeedBatch(items=items, observed_at=OBSERVED_AT)

    async def fetch_following_feed_batches(
        self, request: FeedCollectionRequest
    ) -> tuple[FollowingFeedBatch, ...]:
        return (self._batch,)


def test_allowlist_skips_items_without_creating_investors(db_session: Session) -> None:
    items = (make_item("allowed-event", "allowed"), make_item("skipped-event", "skipped"))
    adapter = XueqiuFeedAdapter(FixtureFollowingBrowser(items))
    request = FeedCollectionRequest(max_batches=1, only_author_ids=("allowed",))

    result = asyncio.run(FeedIngestionService(db_session).ingest_feed(adapter, request))

    assert result.created_investor_count == 1
    assert result.inserted_event_count == 1
    assert db_session.scalar(select(func.count()).select_from(Investor)) == 1
    assert db_session.scalar(select(func.count()).select_from(RawEvent)) == 1
    assert (
        db_session.scalar(
            select(Investor.platform_user_id).where(Investor.platform_user_id == "skipped")
        )
        is None
    )


def test_unknown_post_kind_is_persisted_without_crashing(db_session: Session) -> None:
    item = make_item("unknown-event", "unknown", post_kind=FeedPostKind.UNKNOWN)

    result = asyncio.run(FeedIngestionService(db_session).ingest([item]))

    assert result.inserted_event_count == 1
    stored = db_session.scalar(
        select(RawEvent).where(RawEvent.raw_data["source_event_id"].as_string() == "unknown-event")
    )
    assert stored is not None
    assert stored.raw_data["post_kind"] == FeedPostKind.UNKNOWN.value
