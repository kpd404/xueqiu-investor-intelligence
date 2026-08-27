import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from collectors.xueqiu.contracts import FollowingFeedBatch, XueqiuBrowserConfig
from collectors.xueqiu.errors import (
    AuthenticationRequired,
    BrowserDependencyMissing,
    NavigationFailed,
    NoContent,
    ParseFailed,
    RateLimitedOrBlocked,
)
from collectors.xueqiu.parser import XueqiuFollowingFeedParser, extract_status_items
from contracts import CollectionRequest, FeedCollectionRequest

AUTHENTICATION_MARKERS = ("立即登录/注册", "验证码登录", "账号密码登录", "二维码登录")
BLOCKED_MARKERS = ("滑动验证", "访问受限", "请求过于频繁")
NO_CONTENT_MARKERS = ("暂无内容", "还没有发布", "暂无动态")
XUEQIU_HOME_URL = "https://xueqiu.com/"
FOLLOWING_FEED_PATH = "/v4/statuses/home_timeline.json"
FOLLOWING_TAB_LABEL = "关注"


class XueqiuFollowingFeedDataSource(Protocol):
    async def fetch_following_feed_batches(
        self, request: FeedCollectionRequest
    ) -> Sequence[FollowingFeedBatch]: ...


class XueqiuPageDataSource(Protocol):
    async def fetch_status_payloads(
        self, request: CollectionRequest
    ) -> Sequence[Mapping[str, object]]: ...


class FollowingCaptureContext:
    """Tracks which browser requests belong to the active Following generation."""

    def __init__(self) -> None:
        self._generation = 0
        self._following_capture_active = False
        self._request_generations: dict[int, int | None] = {}

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def following_capture_active(self) -> bool:
        return self._following_capture_active

    def begin_following_capture(self) -> int:
        self._generation += 1
        self._following_capture_active = True
        return self._generation

    def end_following_capture(self) -> None:
        self._following_capture_active = False

    def record_request(self, request: object) -> int | None:
        generation = self._generation if self._following_capture_active else None
        self._request_generations[id(request)] = generation
        return generation

    def request_generation(self, request: object | None) -> int | None:
        if request is None:
            return None
        return self._request_generations.get(id(request))

    def accepts_generation(self, generation: int | None) -> bool:
        return (
            self._following_capture_active
            and generation is not None
            and generation == self._generation
        )

    def accepts_response(self, request: object | None) -> bool:
        return self.accepts_generation(self.request_generation(request))


def is_exact_following_label(label: str) -> bool:
    return label.strip() == FOLLOWING_TAB_LABEL


def following_tab_is_active(
    *,
    class_name: str | None = None,
    aria_selected: str | None = None,
    data_state: str | None = None,
) -> bool:
    class_tokens = set((class_name or "").split())
    if "active" in class_tokens:
        return True
    if (aria_selected or "").lower() == "true":
        return True
    return (data_state or "").lower() in {"active", "selected"}


def is_accepted_following_response(
    *,
    capture_active: bool,
    request_generation: int | None,
    current_generation: int,
    request_url: str,
    request_method: str,
    response_status: int,
    content_type: str | None,
    payload: object,
) -> bool:
    if not capture_active or request_generation != current_generation:
        return False
    if response_status < 200 or response_status >= 300:
        return False
    parsed = urlparse(request_url)
    if parsed.hostname not in {"xueqiu.com", "www.xueqiu.com"}:
        return False
    if parsed.path != FOLLOWING_FEED_PATH or request_method.upper() != "GET":
        return False
    if not content_type or "json" not in content_type.lower():
        return False
    return isinstance(payload, Mapping) and isinstance(payload.get("home_timeline"), list)


class FollowingBatchProgress:
    """Tracks valid batches, unique status IDs, and no-progress attempts."""

    def __init__(self, max_batches: int) -> None:
        self._max_batches = max_batches
        self._batches: list[FollowingFeedBatch] = []
        self._seen_source_event_ids: set[str] = set()
        self._no_progress_count = 0

    @property
    def batches(self) -> tuple[FollowingFeedBatch, ...]:
        return tuple(self._batches)

    @property
    def batch_count(self) -> int:
        return len(self._batches)

    @property
    def seen_source_event_ids(self) -> frozenset[str]:
        return frozenset(self._seen_source_event_ids)

    @property
    def no_progress_count(self) -> int:
        return self._no_progress_count

    @property
    def reached_max_batches(self) -> bool:
        return self.batch_count >= self._max_batches

    def add(self, batch: FollowingFeedBatch) -> bool:
        if self.reached_max_batches:
            return False
        self._batches.append(batch)
        before = len(self._seen_source_event_ids)
        self._seen_source_event_ids.update(item.source_event_id for item in batch.items)
        progressed = len(self._seen_source_event_ids) > before
        self._no_progress_count = 0 if progressed else self._no_progress_count + 1
        return progressed

    def mark_no_progress(self) -> None:
        self._no_progress_count += 1


async def find_exact_following_tab(page: Any) -> Any:
    """Return the unique UI control whose visible label is exactly ``关注``."""

    tab = page.get_by_role("link", name=FOLLOWING_TAB_LABEL, exact=True)
    if await tab.count() == 0:
        tab = page.get_by_text(FOLLOWING_TAB_LABEL, exact=True)
    if await tab.count() != 1:
        raise NavigationFailed("the exact Xueqiu Following tab could not be identified")
    return tab


async def following_tab_locator_is_active(tab: Any) -> bool:
    """Read active state from a tab without relying on a URL change."""

    class_name = await tab.get_attribute("class")
    aria_selected = await tab.get_attribute("aria-selected")
    data_state = await tab.get_attribute("data-state")
    if following_tab_is_active(
        class_name=class_name,
        aria_selected=aria_selected,
        data_state=data_state,
    ):
        return True

    try:
        parent = tab.locator("..")
        parent_class = await parent.get_attribute("class")
    except Exception:
        parent_class = None
    return following_tab_is_active(class_name=parent_class)


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
        self._last_following_stop_reason: str | None = None

    @property
    def last_following_stop_reason(self) -> str | None:
        return self._last_following_stop_reason

    async def fetch_following_feed_batches(
        self, request: FeedCollectionRequest
    ) -> Sequence[FollowingFeedBatch]:
        """Capture bounded batches emitted by the homepage Following Feed.

        The browser never calls the endpoint directly. It only observes
        responses produced by navigating and scrolling the visible homepage.
        """

        self._last_following_stop_reason = None
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

        capture_context = FollowingCaptureContext()
        parser = XueqiuFollowingFeedParser()
        progress = FollowingBatchProgress(request.max_batches)
        response_queue: asyncio.Queue[tuple[int, Mapping[str, object], datetime]] = asyncio.Queue()
        pre_context_responses: list[tuple[Mapping[str, object], datetime]] = []
        response_tasks: list[asyncio.Task[None]] = []
        access_blocked = False
        body_text = ""
        title = ""
        browser = None
        context = None

        async def settle_response_tasks() -> None:
            if response_tasks:
                await asyncio.gather(*response_tasks, return_exceptions=True)

        async def drain_response_queue() -> int:
            accepted_count = 0
            while not response_queue.empty() and not progress.reached_max_batches:
                generation, payload, observed_at = response_queue.get_nowait()
                if not capture_context.accepts_generation(generation):
                    continue
                batch = parser.parse_payload(
                    payload,
                    observed_at=observed_at,
                    batch_sequence=progress.batch_count + 1,
                )
                progress.add(batch)
                accepted_count += 1
            return accepted_count

        async def read_page_state(page: Any) -> tuple[str, str]:
            try:
                current_body = await page.locator("body").inner_text()
                current_title = await page.title()
            except PlaywrightError as exc:
                raise NavigationFailed("could not inspect Xueqiu homepage state") from exc
            return current_body, current_title

        def raise_for_page_state(current_body: str, current_title: str) -> None:
            if access_blocked:
                self._last_following_stop_reason = "BLOCKED"
                raise RateLimitedOrBlocked("Xueqiu returned an access-limited response")
            if any(marker in current_body for marker in BLOCKED_MARKERS) or "验证" in current_title:
                self._last_following_stop_reason = "BLOCKED"
                raise RateLimitedOrBlocked("Xueqiu requested verification; collection stopped")
            if any(marker in current_body for marker in AUTHENTICATION_MARKERS):
                self._last_following_stop_reason = "AUTH_REQUIRED"
                raise AuthenticationRequired("Xueqiu authentication is missing or expired")

        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(**chromium_launch_options(self._config))
                context = await browser.new_context(storage_state=str(storage_state_path))
                page = await context.new_page()

                def record_request(request_object: object) -> None:
                    capture_context.record_request(request_object)

                async def capture_response(response: object) -> None:
                    nonlocal access_blocked
                    request_object = response.request
                    request_url = str(request_object.url or response.url)
                    parsed_url = urlparse(request_url)
                    if parsed_url.hostname not in {"xueqiu.com", "www.xueqiu.com"}:
                        return
                    response_status = int(response.status or 0)
                    if response_status in {403, 429}:
                        access_blocked = True
                        return
                    generation = capture_context.request_generation(request_object)
                    request_method = str(request_object.method)
                    if generation is None and capture_context.following_capture_active:
                        return
                    if generation is not None and not capture_context.accepts_generation(
                        generation
                    ):
                        return
                    if (
                        parsed_url.path != FOLLOWING_FEED_PATH
                        or request_method.upper() != "GET"
                        or response_status < 200
                        or response_status >= 300
                    ):
                        return
                    try:
                        headers = await response.all_headers()
                    except PlaywrightError:
                        return
                    content_type = headers.get("content-type")
                    if not content_type or "json" not in content_type.lower():
                        return
                    try:
                        payload = await response.json()
                    except PlaywrightError:
                        return
                    acceptance_generation = (
                        capture_context.generation if generation is None else generation
                    )
                    if not is_accepted_following_response(
                        capture_active=(
                            capture_context.following_capture_active or generation is None
                        ),
                        request_generation=acceptance_generation,
                        current_generation=capture_context.generation,
                        request_url=request_url,
                        request_method=request_method,
                        response_status=response_status,
                        content_type=content_type,
                        payload=payload,
                    ):
                        return
                    observed_at = datetime.now(UTC)
                    if generation is None:
                        pre_context_responses.append((payload, observed_at))
                    else:
                        await response_queue.put((generation, payload, observed_at))

                def schedule_response(response: object) -> None:
                    response_tasks.append(asyncio.create_task(capture_response(response)))

                page.on("request", record_request)
                page.on("response", schedule_response)
                try:
                    await page.goto(
                        XUEQIU_HOME_URL,
                        wait_until="domcontentloaded",
                        timeout=self._config.navigation_timeout_ms,
                    )
                    await page.wait_for_timeout(self._config.response_wait_ms)
                    body_text, title = await read_page_state(page)
                    raise_for_page_state(body_text, title)
                    await settle_response_tasks()
                    raise_for_page_state(body_text, title)

                    following_tab = await find_exact_following_tab(page)
                    tab_was_active = await following_tab_locator_is_active(following_tab)
                    await settle_response_tasks()
                    raise_for_page_state(body_text, title)
                    if not tab_was_active:
                        pre_context_responses.clear()
                    capture_context.begin_following_capture()
                    if tab_was_active:
                        for payload, observed_at in pre_context_responses:
                            await response_queue.put(
                                (capture_context.generation, payload, observed_at)
                            )
                        pre_context_responses.clear()
                    if not tab_was_active:
                        try:
                            await following_tab.click()
                            await page.wait_for_timeout(self._config.response_wait_ms)
                        except PlaywrightTimeoutError as exc:
                            raise NavigationFailed(
                                "Xueqiu Following tab activation timed out"
                            ) from exc
                        except PlaywrightError as exc:
                            raise NavigationFailed(
                                "Xueqiu Following tab activation failed"
                            ) from exc
                        if not await following_tab_locator_is_active(following_tab):
                            raise NavigationFailed("Xueqiu Following tab did not become active")
                        body_text, title = await read_page_state(page)
                        raise_for_page_state(body_text, title)

                    await settle_response_tasks()
                    raise_for_page_state(body_text, title)
                    await drain_response_queue()

                    while (
                        not progress.reached_max_batches
                        and progress.no_progress_count
                        < self._config.max_scroll_attempts_without_progress
                    ):
                        await page.mouse.wheel(0, 1600)
                        await page.wait_for_timeout(self._config.response_wait_ms)
                        await settle_response_tasks()
                        accepted_count = await drain_response_queue()
                        if accepted_count == 0:
                            progress.mark_no_progress()
                        body_text, title = await read_page_state(page)
                        raise_for_page_state(body_text, title)
                except PlaywrightTimeoutError as exc:
                    raise NavigationFailed("Xueqiu homepage navigation timed out") from exc
                except PlaywrightError as exc:
                    raise NavigationFailed("Xueqiu homepage navigation failed") from exc
                finally:
                    capture_context.end_following_capture()
                    await settle_response_tasks()
                    if context is not None:
                        await context.close()
                    if browser is not None:
                        await browser.close()
            except (
                AuthenticationRequired,
                BrowserDependencyMissing,
                NavigationFailed,
                NoContent,
                ParseFailed,
                RateLimitedOrBlocked,
            ):
                raise

        if progress.reached_max_batches:
            self._last_following_stop_reason = "MAX_BATCHES"
        elif progress.no_progress_count >= self._config.max_scroll_attempts_without_progress:
            self._last_following_stop_reason = "NO_PROGRESS"

        if not progress.batches:
            if any(marker in body_text for marker in NO_CONTENT_MARKERS):
                self._last_following_stop_reason = "NO_CONTENT"
                raise NoContent("Xueqiu Following Feed has no visible content")
            self._last_following_stop_reason = self._last_following_stop_reason or "NO_PROGRESS"
            raise ParseFailed("no supported Following Feed response was observed")
        return progress.batches

    async def fetch_following_feed(
        self, request: FeedCollectionRequest
    ) -> Sequence[FollowingFeedBatch]:
        """Compatibility alias for callers naming the feed rather than batches."""

        return await self.fetch_following_feed_batches(request)

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
