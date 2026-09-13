"""Real-data browser smoke test and screenshots for the Overview page."""

from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path("frontend/screenshots")
VIEWPORTS = (1440, 1280, 1024)


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
        raise AssertionError(f"Overview overflows at {width}px: {json.dumps(dimensions)}")
    if dimensions["bodyScrollWidth"] > dimensions["bodyClientWidth"] + 1:
        raise AssertionError(f"Overview body overflows at {width}px: {json.dumps(dimensions)}")


def _open_overview(page: Page, width: int = 1440) -> None:
    page.set_viewport_size({"width": width, "height": 1000})
    response = page.goto(FRONTEND_URL + "/", wait_until="networkidle")
    if response is None or response.status != 200:
        raise AssertionError("Overview navigation failed")
    page.get_by_role("heading", name="Observed Intelligence Overview").wait_for(
        state="visible", timeout=30_000
    )
    page.locator(".overview-summary").wait_for(state="visible", timeout=30_000)
    _assert_no_horizontal_overflow(page, width)


def _result_count(page: Page) -> int:
    return int(page.locator(".discovery-result-bar > div:first-child > strong").inner_text())


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
        items = response.json()["items"]
        if len(items) != 45:
            raise AssertionError(f"expected 45 observed Assets, got {len(items)}")
        shared_attention = sum(item["attention_investor_count"] >= 2 for item in items)
        multi_opinion = sum(item["opinion_investor_count"] >= 2 for item in items)
        disagreement = sum(
            item.get("latest_alignment") == "MIXED_DIRECTION"
            or item.get("latest_consensus") == "DIVERGENT"
            for item in items
        )
        attention_gap = sum(item["attention_opinion_gap"] for item in items)
        repeated_thesis = sum(item["has_repeated_thesis"] for item in items)
        divergent = [item for item in items if item.get("latest_consensus") == "DIVERGENT"]
        if (shared_attention, multi_opinion, disagreement, attention_gap, repeated_thesis) != (
            24,
            17,
            10,
            9,
            30,
        ):
            raise AssertionError("real overview calibration counts drifted")
        if len(divergent) != 1:
            raise AssertionError(f"expected one DIVERGENT Asset, got {len(divergent)}")

        _open_overview(page)
        body = page.locator("body").inner_text()
        for prohibited in (
            "Trending",
            "Hot",
            "Rising",
            "Cooling",
            "Momentum",
            "Most important",
            "Best idea",
            "Opportunity",
            "Recommended",
        ):
            if prohibited.casefold() in body.casefold():
                raise AssertionError(f"Overview contains prohibited wording: {prohibited}")
        if "Historical completeness: UNKNOWN" not in body or "Observed evidence only" not in body:
            raise AssertionError("Overview is missing the data boundary")
        if "龙源电力" not in body or "DIVERGENT" not in body:
            raise AssertionError("Overview is missing the current divergent Asset")
        if "Missing Thesis Comparison · 1" not in body:
            raise AssertionError("Overview is missing the current data gap")

        screenshots = {"overview_1440": str(SCREENSHOT_DIR / "overview-1440.png")}
        page.screenshot(path=screenshots["overview_1440"], full_page=True)

        for button_name, expected, query in (
            ("Explore Shared Attention", shared_attention, "attention=2"),
            ("Explore Multi-Opinion", multi_opinion, "opinion=2"),
            ("Explore Direction Disagreement", disagreement, "cross=disagreement"),
            ("Explore Attention > Opinion", attention_gap, "gap=attention_gt_opinion"),
            ("Explore Repeated Thesis", repeated_thesis, "thesis=repeated"),
        ):
            _open_overview(page)
            page.get_by_role("button", name=button_name, exact=True).click()
            page.get_by_role("heading", name="Asset Discovery").wait_for(
                state="visible", timeout=30_000
            )
            if query not in page.url or _result_count(page) != expected:
                raise AssertionError(f"{button_name} navigation/count mismatch")

        _open_overview(page, 1280)
        screenshots["overview_1280"] = str(SCREENSHOT_DIR / "overview-1280.png")
        page.screenshot(path=screenshots["overview_1280"], full_page=True)

        _open_overview(page)
        page.locator(".overview-disagreement-section").screenshot(
            path=str(SCREENSHOT_DIR / "overview-disagreement.png")
        )
        screenshots["disagreement_section"] = str(SCREENSHOT_DIR / "overview-disagreement.png")
        page.locator(".gap-panel").screenshot(
            path=str(SCREENSHOT_DIR / "overview-attention-gap.png")
        )
        screenshots["attention_gap_section"] = str(SCREENSHOT_DIR / "overview-attention-gap.png")

        page.get_by_role("button", name=re.compile("大唐发电.*HK:00991.*→")).click()
        page.get_by_role("heading", name="大唐发电").wait_for(state="visible", timeout=30_000)
        if "/assets/" not in page.url:
            raise AssertionError("Data gap did not navigate to Asset detail")

        dragon = next(
            item for item in items if item["market"] == "HK" and item["symbol"] == "00916"
        )
        _open_overview(page)
        page.get_by_role("button", name="Open 龙源电力 HK:00916").first.click()
        page.get_by_role("heading", name="龙源电力").wait_for(state="visible", timeout=30_000)
        if str(dragon["asset_id"]) not in page.url:
            raise AssertionError("DIVERGENT Asset row navigated to the wrong detail")

        _open_overview(page)
        overview_height = page.evaluate("document.documentElement.scrollHeight")
        detail_asset = next(
            item for item in items if item["market"] == "HK" and item["symbol"] == "00902"
        )
        response = page.goto(
            FRONTEND_URL + "/assets/" + str(detail_asset["asset_id"]), wait_until="networkidle"
        )
        if response is None or response.status != 200:
            raise AssertionError("detail navigation failed for height comparison")
        page.get_by_role("heading", name="华能国际").wait_for(state="visible", timeout=30_000)
        detail_height = page.evaluate("document.documentElement.scrollHeight")
        if overview_height >= detail_height:
            raise AssertionError("Overview is not shorter than Asset Detail")

        for width in VIEWPORTS:
            _open_overview(page, width)
            print(json.dumps({"viewport": width, "status": 200}, ensure_ascii=False))

        print("# Observed Intelligence Overview V0 Real-data Browser Smoke")
        print("GET /api/v1/intelligence/assets -> 200")
        print(f"observed_assets={len(items)}")
        print(f"shared_attention={shared_attention}")
        print(f"multi_opinion={multi_opinion}")
        print(f"direction_disagreement={disagreement}")
        print(f"attention_gt_opinion={attention_gap}")
        print(f"repeated_thesis={repeated_thesis}")
        print(json.dumps(screenshots, ensure_ascii=False))
        print("Real-data Overview browser smoke: PASS")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
