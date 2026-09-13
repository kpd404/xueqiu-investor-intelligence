"""Real-data browser smoke test and screenshots for Asset Intelligence Page V0."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path("frontend/screenshots")
CASES = (
    ("招商轮船", "SH", "601872"),
    ("龙源电力", "HK", "00916"),
    ("贵州茅台", "SH", "600519"),
    ("大唐发电", "HK", "00991"),
)


def _find_asset(items: list[dict[str, object]], market: str, symbol: str) -> dict[str, object]:
    matches = [
        item for item in items if item.get("market") == market and item.get("symbol") == symbol
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {market}:{symbol}, got {len(matches)}")
    return matches[0]


def _assert_page(name: str, market: str, symbol: str, body: str) -> None:
    required = [name, market, symbol, "HISTORICAL COMPLETENESS", "UNKNOWN"]
    for value in required:
        if value not in body:
            raise AssertionError(f"{market}:{symbol} page is missing {value!r}")
    if market == "SH" and symbol == "601872":
        for investor in ("笨笨的投资者2", "沈阳城", "Captain-Nemo船长", "看好股市的新人"):
            if investor not in body:
                raise AssertionError(f"招商轮船 page is missing {investor}")
    elif market == "HK" and symbol == "00916":
        for value in ("MIXED DIRECTION", "DIVERGENT", "BEARISH", "BULLISH"):
            if value not in body:
                raise AssertionError(f"龙源电力 page is missing {value}")
    elif market == "SH" and symbol == "600519":
        body_lower = body.casefold()
        if "attention investors" not in body_lower or "opinion investors" not in body_lower:
            raise AssertionError("贵州茅台 page is missing breadth labels")
    elif market == "HK" and symbol == "00991":
        for value in ("14", "13", "1 comparison unavailable"):
            if value not in body:
                raise AssertionError(f"大唐发电 page is missing {value!r}")


def _run() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        assets_response = page.request.get(
            API_URL + "/api/v1/intelligence/assets?limit=100&offset=0"
        )
        if not assets_response.ok:
            raise AssertionError(f"Asset list API status={assets_response.status}")
        items = assets_response.json()["items"]
        print("# Asset Intelligence Page V0 Real-data Browser Smoke")
        print(f"GET /api/v1/intelligence/assets -> {assets_response.status}")
        print(f"actual evidence-bearing assets={len(items)}")
        if len(items) != 45:
            raise AssertionError(f"expected 45 evidence-bearing Assets, got {len(items)}")

        for name, market, symbol in CASES:
            asset = _find_asset(items, market, symbol)
            asset_id = str(asset["asset_id"])
            response = page.goto(FRONTEND_URL + "/assets/" + asset_id, wait_until="networkidle")
            if response is None or response.status != 200:
                raise AssertionError(f"frontend navigation failed for {market}:{symbol}")
            page.locator("h1").wait_for(state="visible", timeout=30_000)
            page.locator(".timeline-panel").wait_for(state="visible", timeout=30_000)
            body = page.locator("body").inner_text()
            _assert_page(name, market, symbol, body)
            screenshot = SCREENSHOT_DIR / f"{market.lower()}-{symbol}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            print(
                json.dumps(
                    {
                        "asset": f"{market}:{symbol}",
                        "name": name,
                        "asset_id": asset_id,
                        "status": response.status,
                        "screenshot": str(screenshot),
                    },
                    ensure_ascii=False,
                )
            )
        browser.close()
    print("Real-data browser smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
