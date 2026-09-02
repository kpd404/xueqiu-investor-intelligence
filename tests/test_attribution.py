from datetime import UTC, datetime
from uuid import uuid4

from contracts import (
    CurrentAuthorEventView,
    EventType,
    RawEventView,
    current_author_analysis_view,
    current_author_text,
)


def test_non_repost_content_is_current_author_text() -> None:
    content = "作者自己的文本 //@这不是一条转发"

    assert current_author_text(content, {}) == content


def test_repost_content_stops_before_quoted_marker() -> None:
    content = "作者自己的文本//@原作者:被转发的证券观点"

    assert current_author_text(content, {"post_kind": "REPOST"}) == "作者自己的文本"


def test_nested_repost_marker_is_not_scanned_as_current_author_text() -> None:
    content = "回复作者:赞同//@原作者:腾讯继续看多"

    assert (
        current_author_text(
            content,
            {"retweeted_status": {"id": "nested-1"}},
        )
        == "回复作者:赞同"
    )


def test_current_author_analysis_view_is_minimal_and_frozen() -> None:
    event = RawEventView(
        id=uuid4(),
        investor_id=uuid4(),
        event_type=EventType.POST,
        source="xueqiu",
        url="https://example.test/event",
        published_time=datetime(2026, 9, 1, tzinfo=UTC),
        content="我继续看好腾讯//@原作者:腾讯继续看空",
        raw_data={
            "post_kind": "REPOST",
            "retweeted_status": {"id": "nested-1", "text": "腾讯继续看空"},
        },
        hash="a" * 64,
        collected_time=datetime(2026, 9, 1, tzinfo=UTC),
    )

    view = current_author_analysis_view(event)

    assert isinstance(view, CurrentAuthorEventView)
    assert view.content == "我继续看好腾讯"
    assert view.event_type is EventType.POST
    assert view.source == "xueqiu"
    assert view.published_time == event.published_time
    assert "id" not in view.model_dump()
    assert "raw_data" not in view.model_dump()
