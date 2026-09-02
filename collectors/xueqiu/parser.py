import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from pydantic import JsonValue

from collectors.xueqiu.contracts import FeedItemParseFailure, FollowingFeedBatch, ParsedXueqiuPost
from collectors.xueqiu.errors import ParseFailed
from contracts import EventType, FeedPostItem, FeedPostKind

XUEQIU_BASE_URL = "https://xueqiu.com"
XUEQIU_TIMEZONE = ZoneInfo("Asia/Shanghai")
STATUS_REQUIRED_FIELDS = {"id", "created_at"}
_ITEM_STRUCTURAL_FIELDS = (
    "id",
    "user_id",
    "user",
    "text",
    "description",
    "created_at",
    "timeBefore",
    "retweet_status_id",
    "retweeted_status",
    "is_column",
    "type",
    "target",
)


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


class XueqiuFollowingFeedParser:
    """Parse only the confirmed Following feed response container.

    This parser intentionally does not perform recursive status discovery. The
    browser/application layer must establish the Following UI context before
    handing a response here.
    """

    def parse_payload(
        self,
        payload: Mapping[str, object],
        *,
        observed_at: datetime | None = None,
        now: datetime | None = None,
        batch_sequence: int | None = None,
    ) -> FollowingFeedBatch:
        raw_items = payload.get("home_timeline")
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            raise ParseFailed("following feed payload is missing home_timeline")

        observed_time = observed_at or datetime.now(UTC)
        reference_time = now or observed_time
        items: list[FeedPostItem] = []
        item_failures: list[FeedItemParseFailure] = []
        for item_index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, Mapping):
                item_failures.append(
                    self._item_failure(item_index, raw_item, ParseFailed("item is not an object"))
                )
                continue
            try:
                items.append(self._parse_item(raw_item, now=reference_time))
            except Exception as exc:
                item_failures.append(self._item_failure(item_index, raw_item, exc))

        try:
            return FollowingFeedBatch(
                items=tuple(items),
                item_failures=tuple(item_failures),
                next_id=payload.get("next_id"),
                next_max_id=payload.get("next_max_id"),
                observed_at=observed_time,
                batch_sequence=batch_sequence,
            )
        except (TypeError, ValueError) as exc:
            raise ParseFailed("invalid Following feed batch cursor semantics") from exc

    def parse_batch(
        self,
        payload: Mapping[str, object],
        *,
        observed_at: datetime | None = None,
        now: datetime | None = None,
        batch_sequence: int | None = None,
    ) -> FollowingFeedBatch:
        """Alias that makes the response-batch boundary explicit to callers."""

        return self.parse_payload(
            payload,
            observed_at=observed_at,
            now=now,
            batch_sequence=batch_sequence,
        )

    @classmethod
    def _parse_item(
        cls,
        item: Mapping[str, object],
        *,
        now: datetime,
    ) -> FeedPostItem:
        source_event_id = cls._required_identifier(item.get("id"), "status id")
        author_id = cls._author_id(item)

        source_text = item.get("text")
        content = html_to_text(source_text) if isinstance(source_text, str) else ""
        if not content:
            description = item.get("description")
            content = html_to_text(description) if isinstance(description, str) else ""
        if not content:
            if source_text is None and not isinstance(item.get("description"), str):
                raise ParseFailed("following feed status has no top-level text")
            raise ParseFailed("following feed status has blank content")

        created_at = item.get("created_at")
        if created_at is None:
            created_at = item.get("timeBefore")
        published_time = parse_xueqiu_time(created_at, now=now)

        post_kind = cls._post_kind(item)
        event_type = EventType.ARTICLE if post_kind is FeedPostKind.COLUMN else EventType.POST
        target = item.get("target")
        target_path = (
            target if isinstance(target, str) and target else f"/{author_id}/{source_event_id}"
        )

        raw_data = dict(item)
        raw_data["source_event_id"] = source_event_id
        raw_data["post_kind"] = post_kind.value
        raw_data["event_type"] = event_type.value

        return FeedPostItem(
            source_event_id=source_event_id,
            author_id=author_id,
            event_type=event_type,
            post_kind=post_kind,
            url=urljoin(XUEQIU_BASE_URL, target_path),
            published_time=published_time,
            content=content,
            raw_data=raw_data,
        )

    @classmethod
    def _item_failure(
        cls,
        item_index: int,
        item: object,
        error: Exception,
    ) -> FeedItemParseFailure:
        source_event_id = cls._safe_source_event_id(item)
        error_code, reason = cls._classify_item_error(error)
        return FeedItemParseFailure(
            item_index=item_index,
            source_event_id=source_event_id,
            error_code=error_code,
            reason=reason,
            structural_context=cls._safe_structural_context(item),
        )

    @staticmethod
    def _safe_source_event_id(item: object) -> str | None:
        if not isinstance(item, Mapping):
            return None
        value = item.get("id")
        if value is None or isinstance(value, bool) or not isinstance(value, str | int):
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _safe_structural_context(item: object) -> dict[str, JsonValue]:
        if not isinstance(item, Mapping):
            return {"item_type": type(item).__name__}

        present_fields = [field for field in _ITEM_STRUCTURAL_FIELDS if field in item]
        field_types = {field: type(item[field]).__name__ for field in present_fields}
        text = item.get("text")
        description = item.get("description")
        return {
            "present_fields": present_fields,
            "field_types": field_types,
            "text_length": len(text) if isinstance(text, str) else None,
            "description_length": len(description) if isinstance(description, str) else None,
            "has_user_object": isinstance(item.get("user"), Mapping),
            "has_retweeted_status": isinstance(item.get("retweeted_status"), Mapping),
        }

    @staticmethod
    def _classify_item_error(error: Exception) -> tuple[str, str]:
        message = str(error)
        if "blank content" in message:
            return "EMPTY_CONTENT", "text and description render to empty content"
        if "no top-level text" in message:
            return "MISSING_TEXT", "text and description do not provide usable content"
        if "missing status id" in message:
            return "MISSING_STATUS_ID", "status id is missing or blank"
        if "missing author id" in message:
            return "MISSING_AUTHOR_ID", "author id is missing or blank"
        if "missing Xueqiu published time" in message:
            return "MISSING_PUBLISHED_TIME", "published time is missing"
        if "unsupported Xueqiu time format" in message:
            return "INVALID_PUBLISHED_TIME", "published time format is unsupported"
        if "item is not an object" in message:
            return "INVALID_ITEM_TYPE", "feed item is not an object"
        return "ITEM_PARSE_ERROR", "feed item failed deterministic normalization"

    @staticmethod
    def _required_identifier(value: object, label: str) -> str:
        if value is None or isinstance(value, bool) or not isinstance(value, str | int):
            raise ParseFailed(f"following feed item is missing {label}")
        normalized = str(value).strip()
        if not normalized:
            raise ParseFailed(f"following feed item is missing {label}")
        return normalized

    @classmethod
    def _author_id(cls, item: Mapping[str, object]) -> str:
        value = item.get("user_id")
        if value is None and isinstance(item.get("user"), Mapping):
            value = item["user"].get("id")  # type: ignore[index,union-attr]
        return cls._required_identifier(value, "author id")

    @staticmethod
    def _post_kind(item: Mapping[str, object]) -> FeedPostKind:
        if item.get("is_column") is True:
            return FeedPostKind.COLUMN

        retweet_id = item.get("retweet_status_id")
        has_retweet_id = retweet_id is not None and str(retweet_id).strip() not in {"", "0"}
        if has_retweet_id or item.get("retweeted_status") is not None:
            return FeedPostKind.REPOST

        if retweet_id in {0, "0"} and item.get("retweeted_status") is None:
            return FeedPostKind.ORIGINAL
        return FeedPostKind.UNKNOWN


def parse_following_feed_payload(
    payload: Mapping[str, object],
    *,
    observed_at: datetime | None = None,
    now: datetime | None = None,
    batch_sequence: int | None = None,
) -> FollowingFeedBatch:
    """Functional entry point for the strict ``home_timeline`` parser."""

    return XueqiuFollowingFeedParser().parse_payload(
        payload,
        observed_at=observed_at,
        now=now,
        batch_sequence=batch_sequence,
    )


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
