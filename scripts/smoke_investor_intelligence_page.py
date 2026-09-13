"""Real-data browser smoke test and screenshots for Investor Intelligence V0."""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path("frontend/screenshots")
VIEWPORTS = (1440, 1280, 1024)
REPRESENTATIVE_INVESTORS = (
    "沈阳城",
    "人生是历练",
    "爱投资的小人书",
    "看好股市的新人",
    "Captain-Nemo船长",
)


def _duration_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


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
        raise AssertionError(f"Investor page overflows at {width}px: {json.dumps(dimensions)}")
    if dimensions["bodyScrollWidth"] > dimensions["bodyClientWidth"] + 1:
        raise AssertionError(f"Investor body overflows at {width}px: {json.dumps(dimensions)}")


def _open_detail(page: Page, investor_id: str, width: int = 1440) -> None:
    page.set_viewport_size({"width": width, "height": 1000})
    response = page.goto(
        FRONTEND_URL + "/investors/" + investor_id,
        wait_until="networkidle",
    )
    if response is None or response.status != 200:
        raise AssertionError(f"Investor detail navigation failed for {investor_id}")
    page.locator(".investor-asset-section").wait_for(state="visible", timeout=30_000)
    _assert_no_horizontal_overflow(page, width)


def _run() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)

        start = time.perf_counter()
        response = page.request.get(API_URL + "/api/v1/intelligence/investors")
        list_ms = _duration_ms(start)
        if not response.ok:
            raise AssertionError(f"Investor list API status={response.status}")
        listing = response.json()
        if listing["total"] != 13:
            raise AssertionError(f"expected 13 effective Investor views, got {listing['total']}")
        by_name = {item["investor_name"]: item for item in listing["items"]}
        if set(REPRESENTATIVE_INVESTORS) - set(by_name):
            raise AssertionError("representative Investor is absent from the API list")

        detail_timings: dict[str, float] = {}
        details: dict[str, dict[str, object]] = {}
        for name in REPRESENTATIVE_INVESTORS:
            investor_id = str(by_name[name]["investor_id"])
            start = time.perf_counter()
            detail_response = page.request.get(
                API_URL + "/api/v1/intelligence/investors/" + investor_id
            )
            detail_timings[name] = _duration_ms(start)
            if not detail_response.ok:
                raise AssertionError(
                    f"Investor detail API status={detail_response.status} for {name}"
                )
            details[name] = detail_response.json()

        _open_detail(page, str(by_name["沈阳城"]["investor_id"]))
        if (
            len(page.locator(".investor-asset-row").all())
            != details["沈阳城"]["attention_asset_count"]
        ):
            raise AssertionError("沈阳城 Asset row count does not match API")
        for prohibited in (
            "Top holdings",
            "Best ideas",
            "Strongest conviction",
            "Current belief",
            "Influence",
        ):
            if prohibited.casefold() in page.locator("body").inner_text().casefold():
                raise AssertionError(f"Investor detail contains prohibited wording: {prohibited}")

        screenshots = {}
        for name in REPRESENTATIVE_INVESTORS:
            investor_id = str(by_name[name]["investor_id"])
            _open_detail(page, investor_id)
            body = page.locator("body").inner_text()
            for value in (
                name,
                "Attention Assets",
                "Opinion Assets",
                "Historical completeness: UNKNOWN",
                "Collection provenance unavailable",
                "2026-",
            ):
                if value not in body:
                    raise AssertionError(f"{name} page is missing {value!r}")
            if name == "爱投资的小人书" and "comparison unavailable" not in body:
                raise AssertionError("爱投资 page is missing the Thesis comparison limitation")
            screenshot_path = SCREENSHOT_DIR / (
                "investor-" + by_name[name]["investor_id"][:8] + ".png"
            )
            page.screenshot(path=str(screenshot_path), full_page=True)
            screenshots[name] = str(screenshot_path)

        _open_detail(page, str(by_name["人生是历练"]["investor_id"]))
        if page.get_by_role("button", name="Open Asset 山东黄金 HK:01787").count() != 1:
            raise AssertionError("人生是历练 page is missing HK:01787")
        if page.get_by_role("button", name="Open Asset 山东黄金 SH:600547").count() != 1:
            raise AssertionError("人生是历练 page is missing SH:600547")
        page.get_by_label("Filter", exact=True).select_option("reversal")
        expected_reversals = details["人生是历练"]["direction_reversal_asset_count"]
        if len(page.locator(".investor-asset-row").all()) != expected_reversals:
            raise AssertionError("reversal filter count does not match API")
        if "filter=reversal" not in page.url:
            raise AssertionError("Investor filter state was not preserved in URL")

        page.goto(FRONTEND_URL + "/investors", wait_until="networkidle")
        page.get_by_role("heading", name="Investor Intelligence").wait_for(
            state="visible", timeout=30_000
        )
        search = page.get_by_role("searchbox", name="Search Investor name")
        search.fill("看好股市的新人")
        page.get_by_role("button", name="Open Investor 看好股市的新人").click()
        page.get_by_role("heading", name="看好股市的新人").wait_for(state="visible", timeout=30_000)
        if "/investors/" not in page.url:
            raise AssertionError("Investor selector did not navigate to detail")

        for width in VIEWPORTS:
            _open_detail(page, str(by_name["沈阳城"]["investor_id"]), width)
            print(json.dumps({"viewport": width, "status": 200}, ensure_ascii=False))

        print("# Investor Intelligence V0 Real-data Browser Smoke")
        print(f"GET /api/v1/intelligence/investors -> 200 ({list_ms} ms)")
        print(f"effective_investor_views={listing['total']}")
        print(json.dumps({"detail_ms": detail_timings}, ensure_ascii=False))
        print(json.dumps(screenshots, ensure_ascii=False))
        print("Real-data Investor Intelligence browser smoke: PASS")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
