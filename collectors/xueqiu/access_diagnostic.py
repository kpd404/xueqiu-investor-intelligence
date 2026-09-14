"""Diagnostic-only Xueqiu access probe.

This module observes the normal homepage navigation path. It never writes
database rows, exports session state, or prints response bodies.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from collectors.xueqiu.browser import (
    AUTHENTICATION_MARKERS,
    BLOCKED_MARKERS,
    FOLLOWING_FEED_PATH,
    NO_CONTENT_MARKERS,
    XUEQIU_HOME_URL,
    chromium_launch_options,
    is_accepted_following_response,
)
from collectors.xueqiu.contracts import XueqiuBrowserConfig
from collectors.xueqiu.parser import XueqiuFollowingFeedParser


@dataclass(frozen=True)
class ResponseDiagnostic:
    host: str
    path: str
    method: str
    status: int
    content_type: str | None
    body_length: int | None
    body_fingerprint: str | None
    safe_markers: tuple[str, ...]
    following_candidate: bool
    parsed_item_count: int | None
    parser_error_type: str | None
    redirect_depth: int


@dataclass(frozen=True)
class AccessDiagnosticReport:
    acquisition_mode: str
    browser_mode: str
    storage_state_present: bool
    requested_url: str
    final_url: str | None
    navigation_status: int | None
    page_title: str | None
    page_body_length: int
    page_body_fingerprint: str
    page_safe_markers: tuple[str, ...]
    response_count: int
    xueqiu_response_count: int
    following_response_count: int
    accepted_following_payload_count: int
    parsed_following_item_count: int
    parser_error_types: tuple[str, ...]
    redirect_depth: int
    login_state_result: str
    block_detection_source: tuple[str, ...]
    result: str
    responses: tuple[ResponseDiagnostic, ...]

    def as_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def safe_url(value: str | None) -> str | None:
    """Return URL origin/path only; never expose query or fragment values."""

    if not value:
        return None
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def safe_body_summary(body: str) -> tuple[int, str, tuple[str, ...]]:
    markers: list[str] = []
    for marker in BLOCKED_MARKERS:
        if marker in body:
            markers.append(f"BLOCKED_MARKER:{marker}")
    for marker in AUTHENTICATION_MARKERS:
        if marker in body:
            markers.append(f"AUTH_MARKER:{marker}")
    for marker in NO_CONTENT_MARKERS:
        if marker in body:
            markers.append(f"NO_CONTENT_MARKER:{marker}")
    encoded = body.encode("utf-8", errors="replace")
    return len(body), hashlib.sha256(encoded).hexdigest()[:16], tuple(markers)


def classify_block_detection(
    *,
    responses: tuple[ResponseDiagnostic, ...],
    page_safe_markers: tuple[str, ...],
    page_title: str | None,
    accepted_following_payload_count: int,
) -> tuple[str, ...]:
    """Classify observed signals without changing production matcher semantics."""

    sources: list[str] = []
    if any(response.status in {403, 429} for response in responses):
        sources.append("HTTP_STATUS")
    if any(
        marker.startswith("BLOCKED_MARKER:")
        for response in responses
        for marker in response.safe_markers
    ):
        sources.append("RESPONSE_BODY_MARKER")
    if any(marker.startswith("BLOCKED_MARKER:") for marker in page_safe_markers):
        sources.append("PAGE_BODY_MARKER")
    if page_title and "验证" in page_title:
        sources.append("PAGE_TITLE_MARKER")
    if any(marker.startswith("AUTH_MARKER:") for marker in page_safe_markers):
        sources.append("LOGIN_STATE_MARKER")
    if accepted_following_payload_count == 0:
        sources.append("NO_ACCEPTED_FOLLOWING_RESPONSE")
    return tuple(dict.fromkeys(sources))


def _redirect_depth(request: Any) -> int:
    depth = 0
    previous = getattr(request, "redirected_from", None)
    while previous is not None and depth < 20:
        depth += 1
        previous = getattr(previous, "redirected_from", None)
    return depth


async def _inspect_response(
    response: Any,
    *,
    parser: XueqiuFollowingFeedParser,
    current_generation: int,
) -> ResponseDiagnostic | None:
    request = response.request
    parsed_url = urlparse(str(getattr(request, "url", "") or getattr(response, "url", "")))
    if parsed_url.hostname not in {"xueqiu.com", "www.xueqiu.com"}:
        return None

    headers = await response.all_headers()
    content_type = headers.get("content-type")
    body = ""
    payload: Mapping[str, object] | None = None
    parser_error_type: str | None = None
    parsed_item_count: int | None = None
    body_length: int | None = None
    body_fingerprint: str | None = None
    safe_markers: tuple[str, ...] = ()

    if (
        parsed_url.path == FOLLOWING_FEED_PATH
        or "html" in (content_type or "").lower()
        or "json" in (content_type or "").lower()
    ):
        try:
            body = await response.text()
            body_length, body_fingerprint, safe_markers = safe_body_summary(body)
        except Exception:
            if parsed_url.path == FOLLOWING_FEED_PATH:
                parser_error_type = "RESPONSE_BODY_UNAVAILABLE"

    if parsed_url.path == FOLLOWING_FEED_PATH and "json" in (content_type or "").lower():
        try:
            candidate = json.loads(body)
            if isinstance(candidate, Mapping):
                payload = candidate
        except (TypeError, ValueError):
            parser_error_type = parser_error_type or "INVALID_JSON"

    following_candidate = is_accepted_following_response(
        capture_active=True,
        request_generation=current_generation,
        current_generation=current_generation,
        request_url=str(getattr(request, "url", "") or getattr(response, "url", "")),
        request_method=str(getattr(request, "method", "GET")),
        response_status=int(getattr(response, "status", 0) or 0),
        content_type=content_type,
        payload=payload,
    )
    if following_candidate and payload is not None:
        try:
            batch = parser.parse_payload(
                payload,
                observed_at=datetime.now(UTC),
                batch_sequence=1,
            )
            parsed_item_count = len(batch.items)
        except Exception as exc:
            parser_error_type = type(exc).__name__

    return ResponseDiagnostic(
        host=parsed_url.netloc,
        path=parsed_url.path,
        method=str(getattr(request, "method", "GET")).upper(),
        status=int(getattr(response, "status", 0) or 0),
        content_type=content_type,
        body_length=body_length,
        body_fingerprint=body_fingerprint,
        safe_markers=safe_markers,
        following_candidate=following_candidate,
        parsed_item_count=parsed_item_count,
        parser_error_type=parser_error_type,
        redirect_depth=_redirect_depth(request),
    )


async def diagnose_access(
    config: XueqiuBrowserConfig,
    *,
    cdp_endpoint: str | None = None,
) -> AccessDiagnosticReport:
    """Observe collector storage-state or an existing CDP browser session."""

    storage_state_path = Path(config.storage_state_path)
    storage_state_present = storage_state_path.is_file()
    acquisition_mode = "EXISTING_CDP" if cdp_endpoint else "COLLECTOR_STORAGE_STATE"
    browser_mode = (
        "VISIBLE_EXISTING_BROWSER"
        if cdp_endpoint
        else ("HEADLESS" if config.headless else "VISIBLE_NEW_CONTEXT")
    )

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed") from exc

    responses: list[ResponseDiagnostic] = []
    response_tasks: list[asyncio.Task[None]] = []
    parser = XueqiuFollowingFeedParser()
    browser = None
    context = None
    page = None

    async with async_playwright() as playwright:
        if cdp_endpoint:
            browser = await playwright.chromium.connect_over_cdp(cdp_endpoint)
            contexts = list(browser.contexts)
            pages = list(contexts[0].pages) if contexts else []
            if not pages:
                return AccessDiagnosticReport(
                    acquisition_mode=acquisition_mode,
                    browser_mode=browser_mode,
                    storage_state_present=storage_state_present,
                    requested_url=XUEQIU_HOME_URL,
                    final_url=None,
                    navigation_status=None,
                    page_title=None,
                    page_body_length=0,
                    page_body_fingerprint="",
                    page_safe_markers=(),
                    response_count=0,
                    xueqiu_response_count=0,
                    following_response_count=0,
                    accepted_following_payload_count=0,
                    parsed_following_item_count=0,
                    parser_error_types=("NO_EXISTING_TARGET_PAGE",),
                    redirect_depth=0,
                    login_state_result="UNKNOWN",
                    block_detection_source=(),
                    result="NO_EXISTING_TARGET_PAGE",
                    responses=(),
                )
            page = pages[0]
        else:
            if not storage_state_present:
                return AccessDiagnosticReport(
                    acquisition_mode=acquisition_mode,
                    browser_mode=browser_mode,
                    storage_state_present=False,
                    requested_url=XUEQIU_HOME_URL,
                    final_url=None,
                    navigation_status=None,
                    page_title=None,
                    page_body_length=0,
                    page_body_fingerprint="",
                    page_safe_markers=(),
                    response_count=0,
                    xueqiu_response_count=0,
                    following_response_count=0,
                    accepted_following_payload_count=0,
                    parsed_following_item_count=0,
                    parser_error_types=("AUTH_STATE_FILE_MISSING",),
                    redirect_depth=0,
                    login_state_result="AUTH_STATE_FILE_MISSING",
                    block_detection_source=(),
                    result="LOGIN_STATE_MISSING",
                    responses=(),
                )
            browser = await playwright.chromium.launch(**chromium_launch_options(config))
            context = await browser.new_context(storage_state=str(storage_state_path))
            page = await context.new_page()

        def schedule(response: Any) -> None:
            async def capture() -> None:
                diagnostic = await _inspect_response(
                    response,
                    parser=parser,
                    current_generation=1,
                )
                if diagnostic is not None:
                    responses.append(diagnostic)

            response_tasks.append(asyncio.create_task(capture()))

        page.on("response", schedule)
        navigation_response = await page.goto(
            XUEQIU_HOME_URL,
            wait_until="domcontentloaded",
            timeout=config.navigation_timeout_ms,
        )
        await page.wait_for_timeout(config.response_wait_ms)
        if response_tasks:
            await asyncio.gather(*response_tasks, return_exceptions=True)
        body_text = await page.locator("body").inner_text()
        title = await page.title()
        final_url = safe_url(str(page.url))
        page_body_length, page_fingerprint, page_markers = safe_body_summary(body_text)

        accepted = [item for item in responses if item.following_candidate]
        parser_errors = tuple(
            sorted(
                {
                    item.parser_error_type
                    for item in responses
                    if item.path == FOLLOWING_FEED_PATH and item.parser_error_type
                }
            )
        )
        block_sources = classify_block_detection(
            responses=tuple(responses),
            page_safe_markers=page_markers,
            page_title=title,
            accepted_following_payload_count=len(accepted),
        )
        login_state_result = (
            "LOGIN_MARKER_PRESENT"
            if any(marker.startswith("AUTH_MARKER:") for marker in page_markers)
            else "NO_LOGIN_MARKER_OBSERVED"
        )
        result = (
            "ACCESS_BLOCKED"
            if any(
                source
                in {
                    "HTTP_STATUS",
                    "PAGE_BODY_MARKER",
                    "PAGE_TITLE_MARKER",
                }
                for source in block_sources
            )
            else "ACCESSIBLE_FEED_PAYLOAD"
            if accepted
            else "NO_ACCEPTED_FOLLOWING_RESPONSE"
        )
        report = AccessDiagnosticReport(
            acquisition_mode=acquisition_mode,
            browser_mode=browser_mode,
            storage_state_present=storage_state_present,
            requested_url=XUEQIU_HOME_URL,
            final_url=final_url,
            navigation_status=(
                int(navigation_response.status) if navigation_response is not None else None
            ),
            page_title=title,
            page_body_length=page_body_length,
            page_body_fingerprint=page_fingerprint,
            page_safe_markers=page_markers,
            response_count=len(responses),
            xueqiu_response_count=len(responses),
            following_response_count=sum(item.path == FOLLOWING_FEED_PATH for item in responses),
            accepted_following_payload_count=len(accepted),
            parsed_following_item_count=sum(item.parsed_item_count or 0 for item in accepted),
            parser_error_types=parser_errors,
            redirect_depth=max((item.redirect_depth for item in responses), default=0),
            login_state_result=login_state_result,
            block_detection_source=block_sources,
            result=result,
            responses=tuple(responses),
        )
        if context is not None:
            await context.close()
        if browser is not None and not cdp_endpoint:
            await browser.close()
        return report


__all__ = [
    "AccessDiagnosticReport",
    "ResponseDiagnostic",
    "classify_block_detection",
    "diagnose_access",
    "safe_body_summary",
    "safe_url",
]
