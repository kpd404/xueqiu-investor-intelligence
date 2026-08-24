import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from collectors.xueqiu.errors import ParseFailed
from collectors.xueqiu.parser import XueqiuPostParser, parse_xueqiu_time

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "xueqiu" / "status_response.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parser_extracts_only_target_investor_original_posts() -> None:
    posts = XueqiuPostParser().parse_payloads(
        [load_fixture()],
        expected_user_id="700001",
        now=datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
    )

    assert len(posts) == 1
    post = posts[0]
    assert post.source_event_id == "880000000001"
    assert post.user_id == "700001"
    assert post.url == "https://xueqiu.com/700001/880000000001"
    assert post.published_time == datetime(2026, 8, 24, 6, 18, tzinfo=UTC)
    assert post.content == "示例投资者的原创公开帖子。\n第二行内容。"
    assert post.raw_data["source_event_id"] == "880000000001"
    assert post.raw_data["is_original"] is True


@pytest.mark.parametrize(
    ("value", "reference", "expected"),
    [
        (
            "2026-08-24 14:18",
            datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 6, 18, tzinfo=UTC),
        ),
        (
            "2026年8月24日 14:18",
            datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 6, 18, tzinfo=UTC),
        ),
        (
            "今天 14:18",
            datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 6, 18, tzinfo=UTC),
        ),
        (
            "昨天 23:30",
            datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
            datetime(2026, 8, 23, 15, 30, tzinfo=UTC),
        ),
        (
            "08-23 23:30",
            datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
            datetime(2026, 8, 23, 15, 30, tzinfo=UTC),
        ),
    ],
)
def test_display_times_are_timezone_aware_and_normalized(
    value: str,
    reference: datetime,
    expected: datetime,
) -> None:
    assert parse_xueqiu_time(value, now=reference) == expected


def test_epoch_milliseconds_are_normalized_to_utc() -> None:
    assert parse_xueqiu_time(1787552280000) == datetime(2026, 8, 24, 6, 18, tzinfo=UTC)


def test_unknown_time_format_is_rejected() -> None:
    with pytest.raises(ParseFailed):
        parse_xueqiu_time("某个时间")
