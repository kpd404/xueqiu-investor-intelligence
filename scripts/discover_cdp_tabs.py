"""Print a read-only inventory of pages in an existing Edge CDP session."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from collectors.xueqiu.cdp_tabs import discover_cdp_tabs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Edge CDP tab discovery; no navigation or collection"
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("XUEQIU_CDP_ENDPOINT", "http://127.0.0.1:9222"),
        help="existing Edge Chromium CDP endpoint",
    )
    return parser.parse_args()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    try:
        result = asyncio.run(discover_cdp_tabs(args.endpoint))
    except Exception as exc:
        print(f"CDP tab discovery failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
