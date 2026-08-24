import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from pydantic import JsonValue

from collectors.xueqiu.contracts import ParsedXueqiuPost
from collectors.xueqiu.errors import ParseFailed

XUEQIU_BASE_URL = "https://xueqiu.com"
XUEQIU_TIMEZONE = ZoneInfo("Asia/Shanghai")
STATUS_REQUIRED_FIELDS = {"id", "created_at"}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(value)
    lines = [" ".join(line.split()) for line in unescape("".join(extractor.parts)).splitlines()]
    return "\n".join(line for line in lines if line).strip()


def parse_xueqiu_time(value: object, *, now: datetime | None = None) -> datetime:
    if isinstance(value, bool):
        raise ParseFailed("boolean is not a valid Xueqiu timestamp")
    if isinstance(value, int | float):
        seconds = float(value) / 1000 if abs(float(value)) >= 100_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=UTC)

    if not isinstance(value, str) or not value.strip():
        raise ParseFailed("missing Xueqiu published time")

    text = value.strip()
    if text.isdigit():
        return parse_xueqiu_time(int(text), now=now)

    reference = now or datetime.now(UTC)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local_reference = reference.astimezone(XUEQIU_TIMEZONE)

    if text == "刚刚":
        return reference.astimezone(UTC)
    if match := re.fullmatch(r"(\d+)分钟前", text):
        return (reference - timedelta(minutes=int(match.group(1)))).astimezone(UTC)
    if match := re.fullmatch(r"(\d+)小时前", text):
        return (reference - timedelta(hours=int(match.group(1)))).astimezone(UTC)
    if match := re.fullmatch(r"今天\s+(\d{1,2}):(\d{2})", text):
        local = local_reference.replace(
            hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0
        )
        return local.astimezone(UTC)
    if match := re.fullmatch(r"昨天\s+(\d{1,2}):(\d{2})", text):
        local = (local_reference - timedelta(days=1)).replace(
            hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0
        )
        return local.astimezone(UTC)

    for pattern, format_string in (
        (r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}", "%Y-%m-%d %H:%M"),
        (r"\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}", "%Y年%m月%d日 %H:%M"),
    ):
        if re.fullmatch(pattern, text):
            return (
                datetime.strptime(text, format_string)
                .replace(tzinfo=XUEQIU_TIMEZONE)
                .astimezone(UTC)
            )

    if match := re.fullmatch(r"(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", text):
        local = datetime(
            local_reference.year,
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
            tzinfo=XUEQIU_TIMEZONE,
        )
        if local > local_reference + timedelta(days=1):
            local = local.replace(year=local.year - 1)
        return local.astimezone(UTC)

    raise ParseFailed(f"unsupported Xueqiu time format: {text}")


def extract_status_items(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    items: list[Mapping[str, object]] = []
    for value in payload.values():
        if not isinstance(value, list):
            continue
        for candidate in value:
            if not isinstance(candidate, Mapping):
                continue
            if STATUS_REQUIRED_FIELDS <= set(candidate) and (
                isinstance(candidate.get("text"), str)
                or isinstance(candidate.get("description"), str)
            ):
                items.append(candidate)
    return items


class XueqiuPostParser:
    def parse_payloads(
        self,
        payloads: Sequence[Mapping[str, object]],
        *,
        expected_user_id: str,
        now: datetime | None = None,
    ) -> list[ParsedXueqiuPost]:
        posts: list[ParsedXueqiuPost] = []
        seen_ids: set[str] = set()
        matching_items = 0

        for payload in payloads:
            for item in extract_status_items(payload):
                user_id = self._user_id(item)
                if user_id != expected_user_id:
                    continue
                matching_items += 1
                if self._is_repost(item):
                    continue
                try:
                    post = self._parse_item(item, user_id=user_id, now=now)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ParseFailed("invalid Xueqiu status payload") from exc
                if post.source_event_id not in seen_ids:
                    posts.append(post)
                    seen_ids.add(post.source_event_id)

        if matching_items and not posts:
            return []
        return sorted(
            posts, key=lambda post: (post.published_time, post.source_event_id), reverse=True
        )

    @staticmethod
    def _user_id(item: Mapping[str, object]) -> str | None:
        value = item.get("user_id")
        if value is None and isinstance(item.get("user"), Mapping):
            value = item["user"].get("id")  # type: ignore[index,union-attr]
        return str(value) if value is not None else None

    @staticmethod
    def _is_repost(item: Mapping[str, object]) -> bool:
        retweet_id = item.get("retweet_status_id")
        return retweet_id not in {None, 0, "0", ""} or item.get("retweeted_status") is not None

    @staticmethod
    def _parse_item(
        item: Mapping[str, object],
        *,
        user_id: str,
        now: datetime | None,
    ) -> ParsedXueqiuPost:
        source_event_id = str(item["id"])
        source_text = item.get("text") or item.get("description")
        if not isinstance(source_text, str):
            raise TypeError("status content is not text")
        content = html_to_text(source_text)
        if not content:
            raise ValueError("status content is blank")

        created_at = item.get("created_at")
        if created_at is None:
            created_at = item.get("timeBefore")
        published_time = parse_xueqiu_time(created_at, now=now)

        target = item.get("target")
        target_path = (
            target if isinstance(target, str) and target else f"/{user_id}/{source_event_id}"
        )
        url = urljoin(XUEQIU_BASE_URL, target_path)
        raw_data: dict[str, JsonValue] = {
            "source_event_id": source_event_id,
            "user_id": user_id,
            "created_at": item.get("created_at"),
            "time_before": item.get("timeBefore"),
            "target": target_path,
            "status_type": item.get("type"),
            "title": item.get("title"),
            "is_original": True,
        }
        return ParsedXueqiuPost(
            source_event_id=source_event_id,
            user_id=user_id,
            url=url,
            published_time=published_time,
            content=content,
            raw_data=raw_data,
        )
