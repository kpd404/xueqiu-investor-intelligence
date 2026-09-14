"""Run a read-only Xueqiu access/session diagnostic; never writes the database."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collectors.xueqiu.access_diagnostic import diagnose_access  # noqa: E402
from collectors.xueqiu.smoke import browser_config  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--cdp-endpoint",
        help="connect to an existing user browser CDP endpoint; no new context is created",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    report = await diagnose_access(
        browser_config(headless=args.headless),
        cdp_endpoint=args.cdp_endpoint,
    )
    print("# Xueqiu Collection Access Diagnosis")
    print(report.as_json())
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
