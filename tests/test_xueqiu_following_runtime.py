import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from collectors.xueqiu import XueqiuFeedAdapter
from collectors.xueqiu.browser import (
    FOLLOWING_FEED_PATH,
    XUEQIU_HOME_URL,
    FollowingBatchProgress,
    FollowingCaptureContext,
    PlaywrightXueqiuBrowser,
    following_tab_is_active,
    is_accepted_following_response,
    is_exact_following_label,
)
from collectors.xueqiu.contracts import FollowingFeedBatch, XueqiuBrowserConfig
from contracts import FeedCollectionRequest, FeedPostItem, FeedPostKind

OBSERVED_AT = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)


def make_post(source_event_id: str, *, author_id: str = "100") -> FeedPostItem:
    return FeedPostItem(
        source_event_id=source_event_id,
        author_id=author_id,
        post_kind=FeedPostKind.ORIGINAL,
        published_time=OBSERVED_AT,
        content=f"post-{source_event_id}",
    )


def make_batch(*source_event_ids: str) -> FollowingFeedBatch:
    return FollowingFeedBatch(
        items=tuple(make_post(source_event_id) for source_event_id in source_event_ids),
        next_max_id=source_event_ids[-1] if source_event_ids else None,
        observed_at=OBSERVED_AT,
    )


def test_exact_following_label_does_not_match_management_or_curated_tabs() -> None:
    assert is_exact_following_label("关注")
    assert not is_exact_following_label("关注97")
    assert not is_exact_following_label("关注精选")
    assert not is_exact_following_label("热门")


def test_following_tab_active_state_uses_explicit_active_attributes() -> None:
    assert following_tab_is_active(class_name="tab active")
    assert following_tab_is_active(aria_selected="true")
    assert following_tab_is_active(data_state="selected")
    assert not following_tab_is_active(class_name="tab")


def test_response_acceptance_requires_following_context_generation_endpoint_and_container() -> None:
    common = {
        "capture_active": True,
        "request_generation": 2,
        "current_generation": 2,
        "request_url": f"https://xueqiu.com{FOLLOWING_FEED_PATH}?max_id=opaque",
        "request_method": "GET",
        "response_status": 200,
        "content_type": "application/json",
        "payload": {"home_timeline": []},
    }
    assert is_accepted_following_response(**common)

    assert not is_accepted_following_response(**{**common, "capture_active": False})
    assert not is_accepted_following_response(**{**common, "request_generation": 1})
    assert not is_accepted_following_response(
        **{**common, "request_url": "https://xueqiu.com/v4/statuses/show.json"}
    )
    assert not is_accepted_following_response(**{**common, "payload": {"list": []}})
    assert not is_accepted_following_response(**{**common, "payload": {"home_timeline": {}}})


def test_late_response_from_old_generation_is_rejected() -> None:
    context = FollowingCaptureContext()
    old_request = object()
    context.begin_following_capture()
    assert context.record_request(old_request) == 1
    context.end_following_capture()
    context.begin_following_capture()
    assert context.generation == 2
    assert not context.accepts_response(old_request)

    current_request = object()
    assert context.record_request(current_request) == 2
    assert context.accepts_response(current_request)


def test_max_batches_counts_valid_batches_and_duplicate_ids_are_not_progress() -> None:
    progress = FollowingBatchProgress(max_batches=2)

    assert progress.add(make_batch("1"))
    assert progress.add(make_batch("2"))
    assert progress.reached_max_batches
    assert progress.batch_count == 2
    assert not progress.add(make_batch("3"))

    duplicate_progress = FollowingBatchProgress(max_batches=4)
    assert duplicate_progress.add(make_batch("1"))
    assert not duplicate_progress.add(make_batch("1"))
    assert duplicate_progress.no_progress_count == 1


def test_no_progress_can_stop_after_bounded_scroll_attempts() -> None:
    progress = FollowingBatchProgress(max_batches=5)
    progress.add(make_batch("1"))
    progress.add(make_batch("1"))
    progress.mark_no_progress()
    progress.mark_no_progress()

    assert progress.no_progress_count == 3
    assert progress.no_progress_count >= XueqiuBrowserConfig().max_scroll_attempts_without_progress


class FixtureFollowingBrowser:
    def __init__(self, batches: tuple[FollowingFeedBatch, ...]) -> None:
        self.batches = batches

    async def fetch_following_feed_batches(
        self, request: FeedCollectionRequest
    ) -> tuple[FollowingFeedBatch, ...]:
        return self.batches


def test_feed_adapter_consumes_batches_without_persistence_and_filters_authors_and_window() -> None:
    second_time = OBSERVED_AT + timedelta(minutes=1)
    included = make_post("1", author_id="100")
    excluded_author = make_post("2", author_id="200")
    excluded_window = FeedPostItem(
        source_event_id="3",
        author_id="100",
        post_kind=FeedPostKind.ORIGINAL,
        published_time=second_time,
        content="outside",
    )
    batches = (
        FollowingFeedBatch(items=(included, excluded_author), observed_at=OBSERVED_AT),
        FollowingFeedBatch(items=(included, excluded_window), observed_at=OBSERVED_AT),
    )
    request = FeedCollectionRequest(
        max_batches=2,
        only_author_ids=("100",),
        until=OBSERVED_AT,
    )

    result = asyncio.run(
        collect_items(XueqiuFeedAdapter(FixtureFollowingBrowser(batches)), request)
    )

    assert [item.source_event_id for item in result] == ["1"]


async def collect_items(
    adapter: XueqiuFeedAdapter, request: FeedCollectionRequest
) -> list[FeedPostItem]:
    return [item async for item in adapter.collect(request)]


class FakeRequest:
    def __init__(self, url: str, method: str = "GET") -> None:
        self.url = url
        self.method = method


class FakeResponse:
    def __init__(self, request: FakeRequest, payload: dict[str, object]) -> None:
        self.request = request
        self.url = request.url
        self.status = 200
        self._payload = payload

    async def all_headers(self) -> dict[str, str]:
        return {"content-type": "application/json"}

    async def json(self) -> dict[str, object]:
        return self._payload


class FakeParentLocator:
    async def get_attribute(self, name: str) -> str | None:
        return None


class FakeFollowingTab:
    def __init__(self, page: "FakeFollowingPage") -> None:
        self.page = page
        self.active = False

    async def count(self) -> int:
        return 1

    async def get_attribute(self, name: str) -> str | None:
        return "active" if name == "class" and self.active else None

    def locator(self, selector: str) -> FakeParentLocator:
        return FakeParentLocator()

    async def click(self) -> None:
        self.active = True
        request = FakeRequest(f"{self.page.feed_url}?source=following")
        self.page.emit_request(request)
        self.page.emit_response(FakeResponse(request, self.page.payload("current")))
        self.page.emit_response(self.page.late_hot_response)


class FakeBodyLocator:
    async def inner_text(self) -> str:
        return "首页 关注 热门 自选"


class FakeMouse:
    def __init__(self, page: "FakeFollowingPage") -> None:
        self.page = page
        self.wheel_calls = 0

    async def wheel(self, x: int, y: int) -> None:
        self.wheel_calls += 1
        if self.wheel_calls == 1:
            request = FakeRequest(f"{self.page.feed_url}?max_id=opaque")
            self.page.emit_request(request)
            self.page.emit_response(FakeResponse(request, self.page.payload("scroll")))


class FakeFollowingPage:
    feed_url = f"https://xueqiu.com{FOLLOWING_FEED_PATH}"

    def __init__(self, *, initial_following: bool = False) -> None:
        self.handlers: dict[str, list[object]] = {"request": [], "response": []}
        self.following_tab = FakeFollowingTab(self)
        self.mouse = FakeMouse(self)
        self.initial_following = initial_following
        old_request = FakeRequest(f"{self.feed_url}?source=hot")
        self.late_hot_response = FakeResponse(old_request, self.payload("late-hot"))

    def payload(self, source_event_id: str) -> dict[str, object]:
        return {
            "home_timeline": [
                {
                    "id": source_event_id,
                    "created_at": 1787817600000,
                    "text": f"<p>{source_event_id}</p>",
                    "user_id": 100,
                    "retweet_status_id": 0,
                    "retweeted_status": None,
                }
            ],
            "next_id": source_event_id,
            "next_max_id": source_event_id,
        }

    def on(self, event: str, callback: object) -> None:
        self.handlers[event].append(callback)

    def emit_request(self, request: FakeRequest) -> None:
        for callback in self.handlers["request"]:
            callback(request)  # type: ignore[operator]

    def emit_response(self, response: FakeResponse) -> None:
        for callback in self.handlers["response"]:
            callback(response)  # type: ignore[operator]

    async def goto(self, url: str, **kwargs: object) -> None:
        assert url == XUEQIU_HOME_URL
        if self.initial_following:
            self.following_tab.active = True
            request = FakeRequest(f"{self.feed_url}?source=following")
            self.emit_request(request)
            self.emit_response(FakeResponse(request, self.payload("initial")))
        else:
            self.emit_request(self.late_hot_response.request)

    async def wait_for_timeout(self, timeout_ms: int) -> None:
        await asyncio.sleep(0)

    def get_by_role(self, role: str, *, name: str, exact: bool) -> FakeFollowingTab:
        assert (role, name, exact) == ("link", "关注", True)
        return self.following_tab

    def get_by_text(self, text: str, *, exact: bool) -> FakeFollowingTab:
        assert (text, exact) == ("关注", True)
        return self.following_tab

    def locator(self, selector: str) -> FakeBodyLocator:
        assert selector == "body"
        return FakeBodyLocator()

    async def title(self) -> str:
        return "我的首页 - 雪球"


class FakeBrowserContext:
    def __init__(self, page: FakeFollowingPage) -> None:
        self.page = page

    async def new_page(self) -> FakeFollowingPage:
        return self.page

    async def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self, page: FakeFollowingPage) -> None:
        self.page = page

    async def new_context(self, *, storage_state: str) -> FakeBrowserContext:
        assert storage_state
        return FakeBrowserContext(self.page)

    async def close(self) -> None:
        return None


class FakeChromium:
    def __init__(self, page: FakeFollowingPage) -> None:
        self.page = page
        self.launch_options: dict[str, object] | None = None

    async def launch(self, **options: object) -> FakeBrowser:
        self.launch_options = options
        return FakeBrowser(self.page)


class FakePlaywright:
    def __init__(self, page: FakeFollowingPage) -> None:
        self.chromium = FakeChromium(page)


class FakePlaywrightManager:
    def __init__(self, page: FakeFollowingPage) -> None:
        self.playwright = FakePlaywright(page)

    async def __aenter__(self) -> FakePlaywright:
        return self.playwright

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def test_playwright_following_runtime_filters_late_hot_response_and_counts_batches(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import playwright.async_api as playwright_api

    page = FakeFollowingPage()
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: FakePlaywrightManager(page))
    storage_state = tmp_path / "storage_state.json"  # type: ignore[union-attr]
    storage_state.write_text("{}", encoding="utf-8")
    config = XueqiuBrowserConfig(
        storage_state_path=str(storage_state),
        response_wait_ms=0,
        max_scroll_attempts_without_progress=2,
    )

    result = asyncio.run(
        PlaywrightXueqiuBrowser(config).fetch_following_feed_batches(
            FeedCollectionRequest(max_batches=2)
        )
    )

    assert [batch.items[0].source_event_id for batch in result] == ["current", "scroll"]
    assert page.mouse.wheel_calls == 1


def test_playwright_following_runtime_keeps_initial_batch_when_tab_is_already_active(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import playwright.async_api as playwright_api

    page = FakeFollowingPage(initial_following=True)
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: FakePlaywrightManager(page))
    storage_state = tmp_path / "storage_state.json"  # type: ignore[union-attr]
    storage_state.write_text("{}", encoding="utf-8")
    config = XueqiuBrowserConfig(storage_state_path=str(storage_state), response_wait_ms=0)

    result = asyncio.run(
        PlaywrightXueqiuBrowser(config).fetch_following_feed_batches(
            FeedCollectionRequest(max_batches=1)
        )
    )

    assert [batch.items[0].source_event_id for batch in result] == ["initial"]
    assert page.mouse.wheel_calls == 0
