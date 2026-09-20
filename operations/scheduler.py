"""Lightweight configurable scheduler for the canonical refresh."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from config import get_settings
from contracts import OperationalRefreshStatus, OperationalRefreshTrigger
from operations.refresh import OperationalRefreshService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the lightweight scheduled Operational Refresh loop"
    )
    parser.add_argument("--cdp-endpoint", help="authenticated Edge CDP endpoint")
    parser.add_argument("--interval-minutes", type=int)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--once", action="store_true", help="execute one scheduled tick and exit")
    return parser


async def run_scheduler(
    *,
    cdp_endpoint: str | None,
    interval_minutes: int,
    max_batches: int = 1,
    once: bool = False,
) -> int:
    if interval_minutes < 1:
        raise ValueError("interval_minutes must be at least 1")
    if max_batches < 1:
        raise ValueError("max_batches must be at least 1")
    service = OperationalRefreshService()
    while True:
        summary = await service.run(
            cdp_endpoint=cdp_endpoint,
            max_batches=max_batches,
            trigger=OperationalRefreshTrigger.SCHEDULED,
            require_cdp=True,
        )
        logger.info(
            "scheduled refresh result=%s run_id=%s",
            summary.result,
            summary.counts.get("operational_run_id"),
        )
        if once:
            return (
                0
                if summary.result
                in {
                    OperationalRefreshStatus.SUCCESS.value,
                    OperationalRefreshStatus.PARTIAL_FAILURE.value,
                }
                else 1
            )
        await asyncio.sleep(interval_minutes * 60)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    endpoint = args.cdp_endpoint or settings.xueqiu_cdp_endpoint
    interval = args.interval_minutes or settings.operational_refresh_interval_minutes
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return asyncio.run(
            run_scheduler(
                cdp_endpoint=endpoint,
                interval_minutes=interval,
                max_batches=args.max_batches,
                once=args.once,
            )
        )
    except KeyboardInterrupt:
        logger.info("scheduled refresh stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
