"""Real-data browser smoke test and screenshots for Asset Discovery V0."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path("frontend/screenshots")
VIEWPORTS = (1440, 1280, 1024)


def _find_asset(items: list[dict[str, object]], market: str, symbol: str) -> dict[str, object]:
    matches = [
        item for item in items if item.get("market") == market and item.get("symbol") == symbol
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {market}:{symbol}, got {len(matches)}")
    return matches[0]


def _result_count(page: Page) -> int:
    return int(page.locator(".discovery-result-bar > div:first-child > strong").inner_text())


def _assert_no_horizontal_overflow(page: Page, width: int) -> None:
    dimensions = page.evaluate(
        """() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          bodyScrollWidth: document.body.scrollWidth,
          bodyClientWidth: document.body.clientWidth
        })"""
    )
    if dimensions["scrollWidth"] > dimensions["clientWidth"] + 1:
        raise AssertionError(f"Discovery overflows at {width}px: {json.dumps(dimensions)}")
    if dimensions["bodyScrollWidth"] > dimensions["bodyClientWidth"] + 1:
        raise AssertionError(f"Discovery body overflows at {width}px: {json.dumps(dimensions)}")


def _open_discovery(page: Page, query: str = "") -> None:
    url = FRONTEND_URL + "/assets" + ("?" + query if query else "")
    response = page.goto(url, wait_until="networkidle")
    if response is None or response.status != 200:
        raise AssertionError(f"Discovery navigation failed: {url}")
    page.get_by_role("heading", name="Asset Discovery").wait_for(state="visible", timeout=30_000)
    page.locator(".discovery-list").wait_for(state="visible", timeout=30_000)


def _capture(page: Page, filename: str) -> str:
    path = SCREENSHOT_DIR / filename
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def _run() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        response = page.request.get(API_URL + "/api/v1/intelligence/assets?limit=100&offset=0")
        if not response.ok:
            raise AssertionError(f"Asset list API status={response.status}")
        catalog = response.json()
        items = catalog["items"]
        if len(items) != 45:
            raise AssertionError(f"expected 45 evidence-bearing Assets, got {len(items)}")
        shared_attention_count = sum(item["attention_investor_count"] >= 2 for item in items)
        multi_opinion_count = sum(item["opinion_investor_count"] >= 2 for item in items)
        disagreement_count = sum(
            item.get("latest_alignment") == "MIXED_DIRECTION"
            or item.get("latest_consensus") == "DIVERGENT"
            for item in items
        )
        gap_count = sum(item["attention_opinion_gap"] for item in items)
        if shared_attention_count != 24:
            raise AssertionError(
                f"expected 24 Shared Attention Assets, got {shared_attention_count}"
            )
        if multi_opinion_count != 17:
            raise AssertionError(f"expected 17 Multi-Opinion Assets, got {multi_opinion_count}")
        if disagreement_count < 1:
            raise AssertionError("expected at least one direction-disagreement Asset")

        page.set_viewport_size({"width": 1440, "height": 1000})
        _open_discovery(page)
        if _result_count(page) != len(items):
            raise AssertionError("All preset did not show the full catalog")
        if page.locator("#discovery-sort").input_value() != "name":
            raise AssertionError("default sort is not Asset name")
        screenshots = {"all": _capture(page, "discovery-all.png")}

        page.get_by_role("button", name="Shared Attention").click()
        if _result_count(page) != shared_attention_count:
            raise AssertionError("Shared Attention preset count mismatch")
        screenshots["shared_attention"] = _capture(page, "discovery-shared-attention.png")

        page.get_by_role("button", name="Multi-Opinion").click()
        if _result_count(page) != multi_opinion_count:
            raise AssertionError("Multi-Opinion preset count mismatch")
        screenshots["multi_opinion"] = _capture(page, "discovery-multi-opinion.png")

        page.get_by_role("button", name="Direction Disagreement").click()
        if _result_count(page) != disagreement_count:
            raise AssertionError("Direction Disagreement preset count mismatch")
        screenshots["disagreement"] = _capture(page, "discovery-disagreement.png")

        page.get_by_role("button", name="Attention > Opinion").click()
        if _result_count(page) != gap_count:
            raise AssertionError("Attention > Opinion preset count mismatch")
        screenshots["attention_gap"] = _capture(page, "discovery-attention-gap.png")

        _open_discovery(page)
        search = page.get_by_role("searchbox", name="Search observed Assets")
        search.fill("山东黄金")
        page.get_by_role("button", name="Open 山东黄金 HK:01787").wait_for(state="visible")
        page.get_by_role("button", name="Open 山东黄金 SH:600547").wait_for(state="visible")
        if len(page.locator(".discovery-card").all()) != 2:
            raise AssertionError("山东黄金 search did not return exactly two listings")
        screenshots["shandong_gold"] = _capture(page, "discovery-shandong-gold.png")

        page.get_by_role("button", name="Open 山东黄金 HK:01787").click()
        page.get_by_role("heading", name="山东黄金").wait_for(state="visible", timeout=30_000)
        if page.locator(".listing-badge").filter(has_text="HK").count() == 0:
            raise AssertionError("HK listing navigation did not preserve market")

        divergence_asset = _find_asset(items, "HK", "00916")
        _open_discovery(page, "cross=divergent")
        if not page.get_by_role("button", name="Open 龙源电力 HK:00916").is_visible():
            raise AssertionError("DIVERGENT filter did not expose 龙源电力")
        if str(divergence_asset["asset_id"]) == "":
            raise AssertionError("missing Dragon asset id")

        for width in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": 1000})
            _open_discovery(page)
            _assert_no_horizontal_overflow(page, width)
            print(json.dumps({"viewport": width, "status": 200}, ensure_ascii=False))

        print("# Asset Discovery V0 Real-data Browser Smoke")
        print(f"GET /api/v1/intelligence/assets -> {response.status}")
        print(f"actual evidence-bearing assets={len(items)}")
        print(f"shared_attention={shared_attention_count}")
        print(f"multi_opinion={multi_opinion_count}")
        print(f"direction_disagreement={disagreement_count}")
        print(f"attention_gt_opinion={gap_count}")
        print(json.dumps(screenshots, ensure_ascii=False))
        print("Real-data Asset Discovery browser smoke: PASS")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
