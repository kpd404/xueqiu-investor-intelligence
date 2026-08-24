import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from collectors.xueqiu.contracts import XueqiuBrowserConfig
from collectors.xueqiu.errors import (
    AuthenticationRequired,
    BrowserDependencyMissing,
    NavigationFailed,
    NoContent,
    ParseFailed,
    RateLimitedOrBlocked,
)
from collectors.xueqiu.parser import extract_status_items
from contracts import CollectionRequest

AUTHENTICATION_MARKERS = ("立即登录/注册", "验证码登录", "账号密码登录", "二维码登录")
BLOCKED_MARKERS = ("滑动验证", "访问受限", "请求过于频繁")
NO_CONTENT_MARKERS = ("暂无内容", "还没有发布", "暂无动态")


class XueqiuPageDataSource(Protocol):
    async def fetch_status_payloads(
        self, request: CollectionRequest
    ) -> Sequence[Mapping[str, object]]: ...


def validate_xueqiu_homepage_url(homepage_url: str | None) -> str:
    if not homepage_url:
        raise NavigationFailed("homepage_url is required for Xueqiu collection")
    parsed = urlparse(homepage_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "xueqiu.com",
        "www.xueqiu.com",
    }:
        raise NavigationFailed("homepage_url must be an xueqiu.com URL")
    if not parsed.path.startswith("/u/"):
        raise NavigationFailed("homepage_url must point to a Xueqiu investor profile")
    return homepage_url


def chromium_launch_options(
    config: XueqiuBrowserConfig,
    *,
    headless: bool | None = None,
) -> dict[str, object]:
    options: dict[str, object] = {"headless": config.headless if headless is None else headless}
    if config.browser_executable_path:
        options["executable_path"] = config.browser_executable_path
    else:
        options["channel"] = config.browser_channel
    return options


class PlaywrightXueqiuBrowser:
    """Internal browser lifecycle; no Playwright object crosses this boundary."""

    def __init__(self, config: XueqiuBrowserConfig) -> None:
        self._config = config

    async def fetch_status_payloads(
        self, request: CollectionRequest
    ) -> Sequence[Mapping[str, object]]:
        homepage_url = validate_xueqiu_homepage_url(request.homepage_url)
        storage_state_path = Path(self._config.storage_state_path)
        if not storage_state_path.is_file():
            raise AuthenticationRequired(
                "Xueqiu authentication state is missing; run the manual authentication command"
            )

        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserDependencyMissing(
                "Playwright is not installed; install project dependencies before collection"
            ) from exc

        payloads: list[Mapping[str, object]] = []
        response_tasks: list[asyncio.Task[None]] = []
        access_blocked = False

        async with async_playwright() as playwright:
            launch_options = chromium_launch_options(self._config)
            browser = await playwright.chromium.launch(**launch_options)
            context = await browser.new_context(storage_state=str(storage_state_path))
            page = await context.new_page()

            async def capture_response(response: object) -> None:
                nonlocal access_blocked
                status = getattr(response, "status", 0)
                if status in {403, 429}:
                    access_blocked = True
                url = getattr(response, "url", "")
                if urlparse(url).hostname not in {"xueqiu.com", "www.xueqiu.com"}:
                    return
                headers = await response.all_headers()  # type: ignore[attr-defined]
                if "json" not in headers.get("content-type", ""):
                    return
                try:
                    payload = await response.json()  # type: ignore[attr-defined]
                except PlaywrightError:
                    return
                if isinstance(payload, Mapping) and extract_status_items(payload):
                    payloads.append(payload)

            def schedule_capture(response: object) -> None:
                response_tasks.append(asyncio.create_task(capture_response(response)))

            page.on("response", schedule_capture)
            try:
                await page.goto(
                    homepage_url,
                    wait_until="domcontentloaded",
                    timeout=self._config.navigation_timeout_ms,
                )
                await page.wait_for_timeout(self._config.response_wait_ms)
                if response_tasks:
                    await asyncio.gather(*response_tasks, return_exceptions=True)
                body_text = await page.locator("body").inner_text()
                title = await page.title()
            except PlaywrightTimeoutError as exc:
                raise NavigationFailed("Xueqiu profile navigation timed out") from exc
            except PlaywrightError as exc:
                raise NavigationFailed("Xueqiu profile navigation failed") from exc
            finally:
                await context.close()
                await browser.close()

        if any(marker in body_text for marker in BLOCKED_MARKERS) or "验证" in title:
            raise RateLimitedOrBlocked("Xueqiu requested verification; collection stopped")
        if access_blocked:
            raise RateLimitedOrBlocked("Xueqiu returned an access-limited response")
        if any(marker in body_text for marker in AUTHENTICATION_MARKERS):
            raise AuthenticationRequired("Xueqiu authentication is missing or expired")
        if not payloads and any(marker in body_text for marker in NO_CONTENT_MARKERS):
            raise NoContent("Xueqiu profile has no public posts")
        if not payloads:
            raise ParseFailed("no supported structured status response was observed")
        return payloads
