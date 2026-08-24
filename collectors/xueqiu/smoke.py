import argparse
import asyncio
import os
from datetime import datetime
from uuid import UUID

from collectors.xueqiu import (
    PlaywrightXueqiuBrowser,
    XueqiuAdapter,
    XueqiuAuthenticator,
    XueqiuBrowserConfig,
    XueqiuCollectorError,
)
from contracts import CollectionRequest
from database.models.investor import Investor
from database.repositories import RawEventRepository
from database.session import SessionFactory
from pipeline import DataPipeline


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


async def run(args: argparse.Namespace) -> int:
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
    with SessionFactory() as session:
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
    parser = argparse.ArgumentParser(description="Xueqiu post collector smoke test")
    parser.add_argument("--authenticate", action="store_true")
    parser.add_argument("--investor-id")
    parser.add_argument("--platform-user-id")
    parser.add_argument("--homepage-url")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--headless", action="store_true")
    return parser


def main() -> None:
    try:
        raise SystemExit(asyncio.run(run(build_parser().parse_args())))
    except (ValueError, XueqiuCollectorError) as exc:
        print(f"Collection stopped: {exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
