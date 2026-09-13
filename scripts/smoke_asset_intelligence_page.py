"""Real-data browser smoke test and screenshots for Asset Intelligence Page V0.1."""

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
    ("华能国际", "HK", "00902"),
    ("大唐发电", "HK", "00991"),
    ("山东黄金", "HK", "01787"),
    ("山东黄金", "SH", "600547"),
)
VIEWPORTS = (1440, 1280, 1024)


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
    elif market == "HK" and symbol == "00902":
        if (
            "Investor Views" not in body
            or "Unified Timeline" not in body
            or "Thesis changes" not in body
        ):
            raise AssertionError("华能国际 page is missing dense intelligence sections")
    elif market == "HK" and symbol == "00991":
        for value in ("14", "13", "1 comparison unavailable"):
            if value not in body:
                raise AssertionError(f"大唐发电 page is missing {value!r}")


def _assert_no_horizontal_overflow(page, market: str, symbol: str, width: int) -> None:
    dimensions = page.evaluate(
        """() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          bodyScrollWidth: document.body.scrollWidth,
          bodyClientWidth: document.body.clientWidth
        })"""
    )
    if dimensions["scrollWidth"] > dimensions["clientWidth"] + 1:
        raise AssertionError(f"{market}:{symbol} overflows at {width}px: {json.dumps(dimensions)}")
    if dimensions["bodyScrollWidth"] > dimensions["bodyClientWidth"] + 1:
        raise AssertionError(
            f"{market}:{symbol} body overflows at {width}px: {json.dumps(dimensions)}"
        )


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

        resolved_assets: dict[tuple[str, str], str] = {}
        for name, market, symbol in CASES:
            asset = _find_asset(items, market, symbol)
            asset_id = str(asset["asset_id"])
            resolved_assets[(market, symbol)] = asset_id
            for width in VIEWPORTS:
                page.set_viewport_size({"width": width, "height": 1000})
                response = page.goto(FRONTEND_URL + "/assets/" + asset_id, wait_until="networkidle")
                if response is None or response.status != 200:
                    raise AssertionError(f"frontend navigation failed for {market}:{symbol}")
                page.locator("h1").wait_for(state="visible", timeout=30_000)
                page.locator(".timeline-panel").wait_for(state="visible", timeout=30_000)
                if market == "HK" and symbol == "00991":
                    page.locator(".investor-card-header").first.click()
                body = page.locator("body").inner_text()
                _assert_page(name, market, symbol, body)
                _assert_no_horizontal_overflow(page, market, symbol, width)
                screenshot = None
                if width == 1440:
                    screenshot_path = SCREENSHOT_DIR / f"{market.lower()}-{symbol}.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    screenshot = str(screenshot_path)
                print(
                    json.dumps(
                        {
                            "asset": f"{market}:{symbol}",
                            "name": name,
                            "asset_id": asset_id,
                            "viewport": width,
                            "status": response.status,
                            "screenshot": screenshot,
                        },
                        ensure_ascii=False,
                    )
                )
        if resolved_assets[("HK", "01787")] == resolved_assets[("SH", "600547")]:
            raise AssertionError("山东黄金 HK:01787 and SH:600547 share an asset id")
        browser.close()
    print("Real-data browser smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
