import argparse
import asyncio
import os
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from collectors.xueqiu import (
    FollowingFeedBatch,
    PlaywrightXueqiuBrowser,
    XueqiuAdapter,
    XueqiuAuthenticator,
    XueqiuBrowserConfig,
    XueqiuCollectorError,
    XueqiuFeedAdapter,
)
from contracts import CollectionRequest, FeedCollectionRequest, FeedPostItem
from ingestion import FeedIngestionResult, FeedIngestionService


def browser_config(*, headless: bool = False) -> XueqiuBrowserConfig:
    return XueqiuBrowserConfig(
        storage_state_path=os.getenv(
            "XUEQIU_STORAGE_STATE_PATH", ".local/xueqiu/storage_state.json"
        ),
        persistent_profile_path=os.getenv("XUEQIU_PROFILE_PATH", ".local/xueqiu/profile"),
        browser_channel=os.getenv("XUEQIU_BROWSER_CHANNEL", "msedge"),
        browser_executable_path=os.getenv("XUEQIU_BROWSER_EXECUTABLE_PATH"),
        headless=headless,
    )


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("time values must include a UTC offset")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be greater than or equal to 1")
    return parsed


def session_scope():
    """Load the database session factory only for non-dry-run execution."""

    from database.session import SessionFactory

    return SessionFactory()


def _short_text(value: str, *, limit: int = 90) -> str:
    compact = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return compact if len(compact) <= limit else f"{compact[: limit - 1]}…"


def _author_name(item: FeedPostItem) -> str:
    user = item.raw_data.get("user")
    if isinstance(user, dict):
        screen_name = user.get("screen_name")
        if isinstance(screen_name, str) and screen_name.strip():
            return screen_name.strip()
    return item.author_id


def _stop_reason(
    browser: PlaywrightXueqiuBrowser,
    batches: Sequence[FollowingFeedBatch],
    request: FeedCollectionRequest,
) -> str:
    if browser.last_following_stop_reason:
        return browser.last_following_stop_reason
    if len(batches) >= request.max_batches:
        return "MAX_BATCHES"
    return "NO_PROGRESS"


def _print_feed_summary(
    batches: Sequence[FollowingFeedBatch],
    items: Sequence[FeedPostItem],
    request: FeedCollectionRequest,
    *,
    stop_reason: str,
) -> None:
    received_items = [item for batch in batches for item in batch.items]
    unique_ids = {item.source_event_id for item in received_items}
    allowlist_skipped = sum(
        1
        for item in received_items
        if request.only_author_ids and item.author_id not in request.only_author_ids
    )
    kind_counts = Counter(item.post_kind.value for item in items)

    print("Following Feed confirmed")
    print(f"batches={len(batches)}")
    print(f"received={len(received_items)}")
    print(f"unique={len(unique_ids)}")
    print(f"duplicates_in_session={len(received_items) - len(unique_ids)}")
    print(f"allowlist_skipped={allowlist_skipped}")
    print(f"stop_reason={stop_reason}")
    if kind_counts:
        print(
            "post_kinds="
            + ",".join(f"{kind}={count}" for kind, count in sorted(kind_counts.items()))
        )
    for item in items[:5]:
        print(
            f"post source_event_id={item.source_event_id} post_kind={item.post_kind.value} "
            f"author={_author_name(item)} content={_short_text(item.content)}"
        )


async def _capture_feed(
    config: XueqiuBrowserConfig,
    request: FeedCollectionRequest,
) -> tuple[Sequence[FollowingFeedBatch], Sequence[FeedPostItem], PlaywrightXueqiuBrowser]:
    browser = PlaywrightXueqiuBrowser(config)
    batches = await browser.fetch_following_feed_batches(request)
    adapter = XueqiuFeedAdapter(browser)
    items = [item async for item in adapter.collect_batches(batches, request)]
    return batches, items, browser


async def run_feed(args: argparse.Namespace) -> int:
    request = FeedCollectionRequest(
        max_batches=args.max_batches,
        since=parse_datetime(args.since),
        until=parse_datetime(args.until),
        only_author_ids=tuple(args.only_investor_ids or ()),
    )
    config = browser_config(headless=args.headless)
    batches, items, browser = await _capture_feed(config, request)
    _print_feed_summary(
        batches,
        items,
        request,
        stop_reason=_stop_reason(browser, batches, request),
    )

    if args.dry_run:
        print("mode=DRY_RUN")
        print("inserted=0")
        print("duplicates=0")
        print("investors_discovered=0")
        return 0

    with session_scope() as session:
        result = await FeedIngestionService(session).ingest(items)
        _print_ingestion_summary(result, request, session)
    return 0


def _print_ingestion_summary(
    result: FeedIngestionResult, request: FeedCollectionRequest, session: object
) -> None:
    print("mode=INGEST")
    print(f"inserted={result.inserted_event_count}")
    print(f"duplicates={result.duplicate_event_count}")
    print(f"investors_discovered={result.created_investor_count}")
    print(f"investors_reused={result.reused_investor_count}")
    if request.only_author_ids:
        print(f"allowlist={','.join(request.only_author_ids)}")

    from database.models import RawEvent

    seen_event_ids: set[UUID] = set()
    for event_id in result.event_ids:
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        event = session.get(RawEvent, event_id)  # type: ignore[attr-defined]
        if event is None:
            continue
        print(
            f"raw_event source_event_id={event.raw_data.get('source_event_id')} "
            f"post_kind={event.raw_data.get('post_kind')} "
            f"author_id={event.raw_data.get('author_id')} "
            f"content={_short_text(event.content)}"
        )
        if len(seen_event_ids) >= 5:
            break


async def run(args: argparse.Namespace) -> int:
    if args.feed:
        if args.authenticate:
            raise ValueError("--authenticate cannot be combined with --feed")
        return await run_feed(args)
    if args.dry_run or args.only_investor_ids or args.max_batches != 1:
        raise ValueError("--dry-run, --only-investor-ids, and --max-batches require --feed")

    config = browser_config(headless=args.headless)
    if args.authenticate:
        state_path = await XueqiuAuthenticator(config).authenticate()
        print(f"Authentication state saved to {state_path}")
        return 0

    required = {
        "--investor-id": args.investor_id,
        "--platform-user-id": args.platform_user_id,
        "--homepage-url": args.homepage_url,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"missing required arguments: {', '.join(missing)}")

    investor_id = UUID(args.investor_id)
    with session_scope() as session:
        from database.models.investor import Investor
        from database.repositories import RawEventRepository
        from pipeline import DataPipeline

        if session.get(Investor, investor_id) is None:
            raise ValueError("investor_id does not exist in the database")
        request = CollectionRequest(
            investor_id=investor_id,
            platform_user_id=args.platform_user_id,
            homepage_url=args.homepage_url,
            since=parse_datetime(args.since),
            until=parse_datetime(args.until),
            limit=args.limit,
        )
        adapter = XueqiuAdapter(PlaywrightXueqiuBrowser(config))
        result = await DataPipeline(RawEventRepository(session), session).run(adapter, request)
        print(
            f"Collected {result.total} posts: "
            f"inserted={result.inserted}, duplicates={result.duplicates}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xueqiu Following Feed smoke and ingestion runner")
    parser.add_argument("--feed", action="store_true", help="use homepage Following Feed runtime")
    parser.add_argument("--authenticate", action="store_true")
    parser.add_argument("--investor-id")
    parser.add_argument("--platform-user-id")
    parser.add_argument("--homepage-url")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--limit", type=positive_int, default=5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-batches", type=positive_int, default=1)
    parser.add_argument("--only-investor-ids", nargs="+", dest="only_investor_ids")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _failure_reason(exc: Exception) -> str:
    from collectors.xueqiu.errors import AuthenticationRequired, NoContent, RateLimitedOrBlocked

    if isinstance(exc, AuthenticationRequired):
        return "AUTH_REQUIRED"
    if isinstance(exc, RateLimitedOrBlocked):
        return "BLOCKED"
    if isinstance(exc, NoContent):
        return "NO_CONTENT"
    return "FAILED"


def main() -> None:
    try:
        raise SystemExit(asyncio.run(run(build_parser().parse_args())))
    except (ValueError, XueqiuCollectorError) as exc:
        print(f"stop_reason={_failure_reason(exc)}")
        print(f"Collection stopped: {exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
