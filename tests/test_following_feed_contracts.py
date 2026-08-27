from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from collectors.xueqiu.contracts import FollowingFeedBatch
from collectors.xueqiu.errors import ParseFailed
from collectors.xueqiu.parser import XueqiuFollowingFeedParser
from contracts import (
    EventType,
    FeedCollectionRequest,
    FeedPostItem,
    FeedPostKind,
)

OBSERVED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)


def make_feed_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": 1001,
        "created_at": 1787817600000,
        "text": "<p>当前状态文本</p>",
        "description": "当前状态摘要",
        "target": "/100/1001",
        "type": "2",
        "user_id": 100,
        "user": {"id": 100, "screen_name": "fixture-user"},
        "retweet_status_id": 0,
        "retweeted_status": None,
        "is_column": False,
        "truncated": False,
        "longTextForIOS": False,
        "image_info_list": None,
    }
    item.update(overrides)
    return item


def make_feed_post(**overrides: object) -> FeedPostItem:
    values: dict[str, object] = {
        "source_event_id": "1001",
        "author_id": "100",
        "event_type": EventType.POST,
        "post_kind": FeedPostKind.ORIGINAL,
        "url": "https://xueqiu.com/100/1001",
        "published_time": OBSERVED_AT,
        "content": "当前状态文本",
    }
    values.update(overrides)
    return FeedPostItem(**values)


def test_feed_collection_request_uses_batches_not_pages() -> None:
    request = FeedCollectionRequest(
        max_batches=3,
        since=datetime(2026, 8, 26, tzinfo=UTC),
        until=OBSERVED_AT,
        only_author_ids=["100", "100", "200"],
    )

    assert request.max_batches == 3
    assert request.only_author_ids == ("100", "200")

    with pytest.raises(ValidationError):
        FeedCollectionRequest(max_pages=3)  # type: ignore[call-arg]


def test_feed_post_item_normalizes_numeric_source_event_id() -> None:
    post = make_feed_post(source_event_id=1001, author_id=100)

    assert post.source_event_id == "1001"
    assert post.author_id == "100"
    assert post.author_user_id == "100"
    assert post.model_dump_json()


def test_following_feed_batch_validates_cursors_and_observation_time() -> None:
    batch = FollowingFeedBatch(
        items=[make_feed_post()],
        next_id=2002,
        next_max_id=2003,
        observed_at=OBSERVED_AT,
        batch_sequence=1,
    )

    assert isinstance(batch.items, tuple)
    assert batch.next_id == "2002"
    assert batch.next_max_id == "2003"

    with pytest.raises(ValidationError):
        FollowingFeedBatch(items=[], observed_at=datetime(2026, 8, 27, 8, 0))


def test_following_parser_reads_only_home_timeline_and_preserves_repost_provenance() -> None:
    payload = {
        "home_timeline": [
            make_feed_item(
                id=9001,
                text="<p>当前作者评论</p>",
                retweet_status_id=8001,
                retweeted_status={
                    "id": 8001,
                    "user": {"id": 800, "screen_name": "original-user"},
                    "text": "<p>被转发原文</p>",
                },
            )
        ],
        "list": [make_feed_item(id=9999, text="不应从其他容器发现")],
        "next_id": 9000,
        "next_max_id": 8999,
    }

    batch = XueqiuFollowingFeedParser().parse_payload(
        payload,
        observed_at=OBSERVED_AT,
    )

    assert len(batch.items) == 1
    post = batch.items[0]
    assert post.source_event_id == "9001"
    assert post.post_kind is FeedPostKind.REPOST
    assert post.content == "当前作者评论"
    assert "被转发原文" not in post.content
    assert post.raw_data["retweet_status_id"] == 8001
    assert post.raw_data["retweeted_status"]["id"] == 8001  # type: ignore[index]
    assert batch.next_max_id == "8999"

    with pytest.raises(ParseFailed):
        XueqiuFollowingFeedParser().parse_payload(
            {"list": [make_feed_item()]},
            observed_at=OBSERVED_AT,
        )


@pytest.mark.parametrize(
    ("overrides", "expected_kind", "expected_event_type"),
    [
        (
            {"retweet_status_id": 0, "retweeted_status": None},
            FeedPostKind.ORIGINAL,
            EventType.POST,
        ),
        (
            {
                "retweet_status_id": 7001,
                "retweeted_status": {"id": 7001, "text": "原文"},
            },
            FeedPostKind.REPOST,
            EventType.POST,
        ),
        (
            {"is_column": True, "retweet_status_id": 0, "retweeted_status": None},
            FeedPostKind.COLUMN,
            EventType.ARTICLE,
        ),
        (
            {"retweet_status_id": None, "retweeted_status": None},
            FeedPostKind.UNKNOWN,
            EventType.POST,
        ),
    ],
)
def test_following_parser_classifies_post_kinds(
    overrides: dict[str, object],
    expected_kind: FeedPostKind,
    expected_event_type: EventType,
) -> None:
    batch = XueqiuFollowingFeedParser().parse_payload(
        {"home_timeline": [make_feed_item(**overrides)]},
        observed_at=OBSERVED_AT,
    )

    assert batch.items[0].post_kind is expected_kind
    assert batch.items[0].event_type is expected_event_type
