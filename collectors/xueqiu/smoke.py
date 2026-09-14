import argparse
import asyncio
import hashlib
import os
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
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
from contracts import (
    CollectionCoverageStatus,
    CollectionMode,
    CollectionRequest,
    CollectionRunCreate,
    CollectionRunStatus,
    CollectionTransport,
    FeedCollectionRequest,
    FeedPostItem,
)
from contracts.collection_provenance import utc_now
from database.repositories import CollectionObservationRepository, CollectionRunRepository
from ingestion import FeedIngestionResult, FeedIngestionService


def browser_config(
    *, headless: bool = False, cdp_endpoint: str | None = None
) -> XueqiuBrowserConfig:
    return XueqiuBrowserConfig(
        storage_state_path=os.getenv(
            "XUEQIU_STORAGE_STATE_PATH", ".local/xueqiu/storage_state.json"
        ),
        persistent_profile_path=os.getenv("XUEQIU_PROFILE_PATH", ".local/xueqiu/profile"),
        browser_channel=os.getenv("XUEQIU_BROWSER_CHANNEL", "msedge"),
        browser_executable_path=os.getenv("XUEQIU_BROWSER_EXECUTABLE_PATH"),
        cdp_endpoint=cdp_endpoint,
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


def _cursor_digest(value: str | None) -> str:
    if value is None:
        return "none"
    return f"str:{len(value)}:{hashlib.sha256(value.encode()).hexdigest()[:12]}"


def _batch_time_bounds(batch: FollowingFeedBatch) -> tuple[str, str]:
    if not batch.items:
        return "none", "none"
    values = [item.published_time.astimezone(UTC) for item in batch.items]
    return min(values).isoformat(), max(values).isoformat()


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


def _run_status_for_stop_reason(stop_reason: str) -> CollectionRunStatus:
    if stop_reason in {"RISK_CONTROL", "LOGIN_REQUIRED", "MANUAL_STOP"}:
        return CollectionRunStatus.ABORTED
    return CollectionRunStatus.COMPLETED


def _create_feed_run(
    request: FeedCollectionRequest,
    *,
    transport: CollectionTransport,
) -> UUID:
    with session_scope() as session:
        run = CollectionRunRepository(session).create_run(
            CollectionRunCreate(
                source=XueqiuFeedAdapter.source,
                adapter_name=XueqiuFeedAdapter.adapter_name,
                collection_mode=CollectionMode.FEED,
                transport=transport,
                started_at=utc_now(),
                coverage_status=CollectionCoverageStatus.UNKNOWN,
                requested_window_start=request.since,
                requested_window_end=request.until,
                scope_type="FOLLOWING_FEED",
                parameters_json={
                    "max_batches": request.max_batches,
                    "only_author_ids": list(request.only_author_ids),
                },
            )
        )
        session.commit()
        return run.id


def _close_run(
    run_id: UUID,
    *,
    status: CollectionRunStatus,
    stop_reason: str | None,
    summary_json: dict[str, object] | None = None,
) -> None:
    with session_scope() as session:
        repository = CollectionRunRepository(session)
        if status is CollectionRunStatus.COMPLETED:
            repository.finish_run(
                run_id,
                ended_at=utc_now(),
                stop_reason=stop_reason,
                summary_json=summary_json,
            )
        elif status is CollectionRunStatus.ABORTED:
            repository.abort_run(
                run_id,
                ended_at=utc_now(),
                stop_reason=stop_reason,
                summary_json=summary_json,
            )
        else:
            repository.fail_run(
                run_id,
                ended_at=utc_now(),
                stop_reason=stop_reason,
                summary_json=summary_json,
            )
        session.commit()


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
    for index, batch in enumerate(batches, start=1):
        published_min, published_max = _batch_time_bounds(batch)
        print(
            f"batch={index} items={len(batch.items) + len(batch.item_failures)} "
            f"valid={len(batch.items)} skipped={len(batch.item_failures)} "
            f"next_id={_cursor_digest(batch.next_id)} "
            f"next_max_id={_cursor_digest(batch.next_max_id)} "
            f"published_min={published_min} published_max={published_max}"
        )
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
    config = browser_config(headless=args.headless, cdp_endpoint=args.cdp_endpoint)
    run_id: UUID | None = None
    if not args.dry_run:
        run_id = _create_feed_run(
            request,
            transport=(
                CollectionTransport.BROWSER_CDP
                if args.cdp_endpoint
                else CollectionTransport.BROWSER_SESSION
            ),
        )
    try:
        batches, items, browser = await _capture_feed(config, request)
    except Exception as exc:
        if run_id is not None:
            _close_run(
                run_id,
                status=CollectionRunStatus.FAILED,
                stop_reason=_failure_reason(exc),
            )
        raise
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

    stop_reason = _stop_reason(browser, batches, request)
    try:
        with session_scope() as session:
            result = await FeedIngestionService(
                session,
                collection_observation_repository=CollectionObservationRepository(session),
                collection_run_id=run_id,
            ).ingest(items)
            summary = {
                "batches": len(batches),
                "items": len(items),
                "inserted_raw_events": result.inserted_event_count,
                "reused_raw_events": result.duplicate_event_count,
            }
            run_repository = CollectionRunRepository(session)
            if _run_status_for_stop_reason(stop_reason) is CollectionRunStatus.COMPLETED:
                run_repository.finish_run(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason=stop_reason,
                    summary_json=summary,
                )
            else:
                run_repository.abort_run(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason=stop_reason,
                    summary_json=summary,
                )
            session.commit()
            _print_ingestion_summary(result, request, session)
    except Exception as exc:
        if run_id is not None:
            _close_run(
                run_id,
                status=CollectionRunStatus.FAILED,
                stop_reason=_failure_reason(exc),
            )
        raise
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
        run = CollectionRunRepository(session).create_run(
            CollectionRunCreate(
                source=adapter.source,
                adapter_name=adapter.adapter_name,
                collection_mode=adapter.collection_mode,
                transport=adapter.transport,
                started_at=utc_now(),
                coverage_status=CollectionCoverageStatus.UNKNOWN,
                requested_window_start=request.since,
                requested_window_end=request.until,
                scope_type="INVESTOR_PROFILE",
                scope_key=str(investor_id),
                parameters_json={"limit": request.limit},
            )
        )
        session.commit()
        try:
            result = await DataPipeline(
                RawEventRepository(session),
                session,
                collection_observation_repository=CollectionObservationRepository(session),
                collection_run_id=run.id,
                source_page=request.homepage_url,
                source_context_json={"platform_user_id": request.platform_user_id},
            ).run(adapter, request)
            CollectionRunRepository(session).finish_run(
                run.id,
                ended_at=utc_now(),
                stop_reason="REQUEST_COMPLETED",
                summary_json={
                    "inserted_raw_events": result.inserted,
                    "reused_raw_events": result.duplicates,
                },
            )
            session.commit()
        except Exception:
            session.rollback()
            CollectionRunRepository(session).fail_run(
                run.id,
                ended_at=utc_now(),
                stop_reason="FAILED",
            )
            session.commit()
            raise
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
    parser.add_argument(
        "--cdp-endpoint",
        help="attach to an existing authenticated browser via CDP; no new context is created",
    )
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
