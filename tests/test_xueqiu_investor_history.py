import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from collectors.xueqiu.contracts import XueqiuBrowserConfig
from collectors.xueqiu.errors import (
    CdpNotAvailable,
    ManualVerificationRequired,
    NavigationFailed,
    NetworkUnavailable,
)
from collectors.xueqiu.investor_history import (
    InvestorHistoryCollectionRequest,
    InvestorHistoryStopReason,
    ParsedHistoryPage,
    XueqiuInvestorHistoryAdapter,
    XueqiuInvestorHistoryBrowser,
    parse_history_payload,
    summarize_history_pages,
    validate_current_investor_url,
)
from contracts import FeedPostItem, RawEventWriteResult
from pipeline import DataPipeline

INVESTOR_ID = UUID("00000000-0000-0000-0000-000000000001")
PLATFORM_USER_ID = "8799248060"
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 7, tzinfo=UTC)


def _timestamp(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _status(
    source_event_id: str,
    published_time: datetime,
    *,
    user_id: str = PLATFORM_USER_ID,
    created_at: object | None = None,
) -> dict[str, object]:
    return {
        "id": source_event_id,
        "user_id": user_id,
        "created_at": _timestamp(published_time) if created_at is None else created_at,
        "text": f"<p>{source_event_id}</p>",
        "retweet_status_id": 0,
        "retweeted_status": None,
    }


def _request(*, lookback_days: int = 7, max_pages: int = 5) -> InvestorHistoryCollectionRequest:
    return InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=lookback_days,
        max_pages=max_pages,
        until=END,
    )


def test_history_request_builds_profile_url_and_bounded_window():
    request = _request(lookback_days=15, max_pages=7)

    assert request.homepage_url == f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
    assert request.since == END - timedelta(days=15)
    assert request.until == END
    assert request.max_pages == 7


def test_human_assisted_request_has_bounded_duration():
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=3,
        max_idle_cycles=2,
        max_duration_seconds=12,
        human_assisted=True,
        until=END,
    )

    assert request.human_assisted is True
    assert request.max_duration_seconds == 12


@pytest.mark.parametrize(
    "url",
    [
        "about:blank",
        "https://xueqiu.com/",
        "https://example.com/u/8799248060",
        "https://xueqiu.com/u/other-user",
    ],
)
def test_current_page_must_be_matching_xueqiu_investor_profile(url):
    with pytest.raises(NavigationFailed):
        validate_current_investor_url(url, PLATFORM_USER_ID)


def test_history_parser_filters_other_authors_and_counts_item_failures():
    payload = {
        "statuses": [
            _status("target", END - timedelta(days=1)),
            _status("other", END - timedelta(days=1), user_id="other-user"),
            _status("malformed", END - timedelta(days=2), created_at="unsupported"),
        ],
        "next_max_id": "opaque-cursor",
    }

    page = parse_history_payload(
        payload,
        expected_user_id=PLATFORM_USER_ID,
        now=END,
        endpoint_path="/v4/statuses/user_timeline.json",
    )

    assert [post.source_event_id for post in page.posts] == ["target"]
    assert page.parse_failures == 1
    assert page.has_more is True


def test_history_summary_filters_lookback_and_deduplicates_posts():
    request = _request(lookback_days=7)
    first = parse_history_payload(
        {
            "statuses": [
                _status("newest", END),
                _status("inside", END - timedelta(days=1)),
                _status("too-old", END - timedelta(days=8)),
            ]
        },
        expected_user_id=PLATFORM_USER_ID,
        now=END,
        endpoint_path="/v4/statuses/user_timeline.json",
    )
    duplicate = parse_history_payload(
        {"statuses": [_status("inside", END - timedelta(days=1))]},
        expected_user_id=PLATFORM_USER_ID,
        now=END,
        endpoint_path="/v4/statuses/user_timeline.json",
    )

    result = summarize_history_pages(
        [first, duplicate],
        request,
        stop_reason=InvestorHistoryStopReason.TARGET_REACHED,
    )

    assert [post.source_event_id for post in result.posts] == ["newest", "inside"]
    assert result.pages == 2
    assert result.duplicate_posts_in_capture == 1
    assert len(result.posts) == 2
    assert result.newest_published_time == END
    assert result.oldest_published_time == END - timedelta(days=1)
    assert result.actual_history_span_days == 1.0


class _FakeCaptureBrowser:
    def __init__(self, capture):
        self.capture_result = capture

    async def capture(self, request):
        return self.capture_result


class _RawEventWriter:
    def __init__(self):
        self.dtos = []
        self.hashes = set()

    def add_if_absent(self, dto):
        self.dtos.append(dto)
        created = dto.hash not in self.hashes
        self.hashes.add(dto.hash)
        return RawEventWriteResult(event_id=uuid4(), hash=dto.hash, created=created)


class _Transaction:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("rollback was not expected")


def test_history_adapter_emits_raw_events_through_data_pipeline():
    post = FeedPostItem(
        source_event_id="adapter-post",
        author_id=PLATFORM_USER_ID,
        published_time=END - timedelta(days=1),
        content="adapter post",
        raw_data={"source_event_id": "adapter-post"},
    )
    capture = summarize_history_pages(
        [
            ParsedHistoryPage(
                posts=(post,),
                parse_failures=0,
                has_more=False,
                endpoint_path="/v4/statuses/user_timeline.json",
            )
        ],
        _request(),
        stop_reason=InvestorHistoryStopReason.END_OF_HISTORY,
    )
    writer = _RawEventWriter()
    transaction = _Transaction()
    adapter = XueqiuInvestorHistoryAdapter(_FakeCaptureBrowser(capture))

    first = asyncio.run(DataPipeline(writer, transaction).run(adapter, _request()))
    second = asyncio.run(DataPipeline(writer, transaction).run(adapter, _request()))

    assert first.total == 1
    assert first.inserted == 1
    assert second.total == 1
    assert second.duplicates == 1
    assert transaction.commits == 2
    assert writer.dtos[0].investor_id == INVESTOR_ID
    assert writer.dtos[0].source == "xueqiu"
    assert writer.dtos[0].raw_data["author_id"] == PLATFORM_USER_ID


class _FakeRequest:
    def __init__(self, url: str):
        self.url = url
        self.method = "GET"


class _FakeResponse:
    def __init__(self, request: _FakeRequest, payload: dict[str, object]):
        self.request = request
        self.url = request.url
        self.status = 200
        self._payload = payload

    async def all_headers(self):
        return {"content-type": "application/json"}

    async def json(self):
        return self._payload


class _FakeBodyLocator:
    def __init__(self, text="Investor profile"):
        self.text = text

    async def inner_text(self):
        return self.text


class _FakeHistoryPage:
    endpoint = "https://xueqiu.com/v4/statuses/user_timeline.json"

    def __init__(
        self,
        *,
        old_age_days: int = 8,
        emit_scroll_response: bool = True,
        repeat_scroll_response: bool = False,
        emit_auxiliary_response: bool = False,
        emit_non_primary_status_response: bool = False,
        page_control_pages: tuple[int, ...] | None = None,
        page_ages: dict[int, int] | None = None,
        repeat_page_ids: bool = False,
    ):
        self.handlers = {"response": []}
        self.wheel_calls = 0
        self.mouse = self
        self.url = "about:blank"
        self.goto_calls = 0
        self.body_text = "Investor profile"
        self.old_age_days = old_age_days
        self.emit_scroll_response = emit_scroll_response
        self.repeat_scroll_response = repeat_scroll_response
        self.emit_auxiliary_response = emit_auxiliary_response
        self.emit_non_primary_status_response = emit_non_primary_status_response
        self.page_control_pages = page_control_pages
        self.page_ages = page_ages or {}
        self.repeat_page_ids = repeat_page_ids
        self.page_control_page = 1

    def on(self, event, callback):
        self.handlers[event].append(callback)

    def emit_response(self, response):
        for callback in self.handlers["response"]:
            callback(response)

    async def goto(self, url, **kwargs):
        self.goto_calls += 1
        if self.emit_auxiliary_response:
            self.emit_response(
                _FakeResponse(
                    _FakeRequest("https://xueqiu.com/statuses/video/timeline.json?page=1"),
                    {"statuses": []},
                )
            )
        if self.emit_non_primary_status_response:
            self.emit_response(
                _FakeResponse(
                    _FakeRequest("https://xueqiu.com/statuses/original/timeline.json?page=1"),
                    {"statuses": [_status("auxiliary-old", END - timedelta(days=365))]},
                )
            )
        self.emit_response(
            _FakeResponse(
                _FakeRequest(f"{self.endpoint}?page=1"),
                {"statuses": [_status("new", END - timedelta(days=1))]},
            )
        )

    async def wait_for_timeout(self, timeout_ms):
        await asyncio.sleep(0)

    async def evaluate(self, script, arg=None):
        if "xueqiu_page_control_discovery_v1" in script:
            if self.page_control_pages is None:
                return {
                    "scroll_y": 0,
                    "scroll_height": 1000,
                    "loading": False,
                }
            has_next = self.page_control_page < max(self.page_control_pages)
            next_page = self.page_control_page + 1 if has_next else None
            return {
                "has_pagination_control": True,
                "current_page": self.page_control_page,
                "next_page": next_page,
                "next_available": has_next,
                "control_role": "link",
                "control_selector": 'role=link name="下一页"',
                "disabled": False if has_next else True,
                "end_state": not has_next,
                "key": {
                    "tag": "a",
                    "role": "link",
                    "text": "下一页",
                    "aria_label": "",
                    "title": "",
                    "data_page": "",
                },
            }
        if "xueqiu_page_control_click_v1" in script:
            if self.page_control_pages is None:
                return {"clicked": False}
            next_page = self.page_control_page + 1
            if next_page not in self.page_control_pages:
                return {"clicked": False}
            self.page_control_page = next_page
            source_event_id = "page-1" if self.repeat_page_ids else f"page-{next_page}"
            self.emit_response(
                _FakeResponse(
                    _FakeRequest(f"{self.endpoint}?page={next_page}"),
                    {
                        "statuses": [
                            _status(
                                source_event_id,
                                END
                                - timedelta(days=self.page_ages.get(next_page, self.old_age_days)),
                            )
                        ]
                    },
                )
            )
            return {"clicked": True}
        return {"scroll_y": 0, "scroll_height": 1000, "loading": False}

    async def wheel(self, x, y):
        self.wheel_calls += 1
        if self.emit_scroll_response and (self.wheel_calls == 1 or self.repeat_scroll_response):
            self.emit_response(
                _FakeResponse(
                    _FakeRequest(f"{self.endpoint}?page=2"),
                    {"statuses": [_status("old", END - timedelta(days=self.old_age_days))]},
                )
            )

    def locator(self, selector):
        assert selector == "body"
        return _FakeBodyLocator(self.body_text)

    async def title(self):
        return "雪球 Investor"


class _FakeHistoryContext:
    def __init__(self, page):
        self.page = page
        self.pages = [page]

    async def new_page(self):
        return self.page

    async def close(self):
        return None


class _FakePlaywrightBrowser:
    def __init__(self, page):
        self.page = page

    async def new_context(self, *, storage_state):
        assert storage_state
        return _FakeHistoryContext(self.page)

    async def close(self):
        return None


class _FakeChromium:
    def __init__(self, page):
        self.page = page
        self.cdp_endpoints = []

    async def launch(self, **options):
        return _FakePlaywrightBrowser(self.page)

    async def connect_over_cdp(self, endpoint):
        self.cdp_endpoints.append(endpoint)
        return _FakeCdpBrowser(self.page)


class _FakeCdpBrowser:
    def __init__(self, page):
        self.contexts = [_FakeHistoryContext(page)]

    async def close(self):
        return None


class _FakePlaywright:
    def __init__(self, page):
        self.chromium = _FakeChromium(page)


class _FakePlaywrightManager:
    def __init__(self, page):
        self.playwright = _FakePlaywright(page)

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc, traceback):
        return None


def test_history_browser_stops_when_target_date_is_reached(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage()
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    storage_state = tmp_path / "storage_state.json"
    storage_state.write_text("{}", encoding="utf-8")
    request = _request(lookback_days=7, max_pages=3)
    browser = XueqiuInvestorHistoryBrowser(
        XueqiuBrowserConfig(
            storage_state_path=str(storage_state),
            response_wait_ms=0,
            max_idle_cycles_without_progress=2,
        )
    )

    result = asyncio.run(browser.capture(request))

    assert result.pages == 2
    assert [post.source_event_id for post in result.posts] == ["new"]
    assert result.stop_reason is InvestorHistoryStopReason.TARGET_REACHED
    assert browser.last_stop_reason is InvestorHistoryStopReason.TARGET_REACHED
    assert page.wheel_calls == 1


def test_history_browser_reaches_30d_target(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(old_age_days=30)
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    request = _request(lookback_days=30, max_pages=3)
    request = request.model_copy(update={"max_duration_seconds": 5})
    storage_state_path = tmp_path / "storage_state.json"
    storage_state_path.write_text("{}", encoding="utf-8")
    browser = XueqiuInvestorHistoryBrowser(
        XueqiuBrowserConfig(
            storage_state_path=str(storage_state_path),
            response_wait_ms=0,
            max_idle_cycles_without_progress=2,
        )
    )
    result = asyncio.run(browser.capture(request))

    assert result.stop_reason is InvestorHistoryStopReason.TARGET_REACHED
    assert result.oldest_published_time == END - timedelta(days=30)


def test_auxiliary_timeline_responses_do_not_consume_page_budget(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(old_age_days=30, emit_auxiliary_response=True)
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    storage_state_path = tmp_path / "storage_state.json"
    storage_state_path.write_text("{}", encoding="utf-8")
    request = _request(lookback_days=30, max_pages=2)
    browser = XueqiuInvestorHistoryBrowser(
        XueqiuBrowserConfig(
            storage_state_path=str(storage_state_path),
            response_wait_ms=0,
            max_idle_cycles_without_progress=2,
        )
    )

    result = asyncio.run(browser.capture(request))

    assert result.pages == 2
    assert result.oldest_published_time == END - timedelta(days=30)
    assert result.stop_reason is InvestorHistoryStopReason.TARGET_REACHED
    assert page.wheel_calls == 1


def test_non_primary_timeline_statuses_do_not_trigger_history_target(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(
        old_age_days=8,
        emit_scroll_response=False,
        emit_non_primary_status_response=True,
    )
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    storage_state_path = tmp_path / "storage_state.json"
    storage_state_path.write_text("{}", encoding="utf-8")
    request = _request(lookback_days=30, max_pages=3)
    browser = XueqiuInvestorHistoryBrowser(
        XueqiuBrowserConfig(
            storage_state_path=str(storage_state_path),
            response_wait_ms=0,
            max_idle_cycles_without_progress=1,
        )
    )

    result = asyncio.run(browser.capture(request))

    assert result.pages == 1
    assert len(result.posts) == 1
    assert result.stop_reason is InvestorHistoryStopReason.NO_PROGRESS
    assert "/statuses/original/timeline.json" in result.observed_endpoint_paths


def test_history_browser_has_bounded_no_progress(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(emit_scroll_response=False)
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    storage_state_path = tmp_path / "storage_state.json"
    storage_state_path.write_text("{}", encoding="utf-8")
    request = _request(lookback_days=30, max_pages=3)
    browser = XueqiuInvestorHistoryBrowser(
        XueqiuBrowserConfig(
            storage_state_path=str(storage_state_path),
            response_wait_ms=0,
            max_idle_cycles_without_progress=2,
        )
    )
    result = asyncio.run(browser.capture(request))

    assert result.stop_reason is InvestorHistoryStopReason.NO_PROGRESS
    assert page.wheel_calls == 2


def test_repeated_timeline_response_does_not_count_as_progress(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(repeat_scroll_response=True)
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    storage_state_path = tmp_path / "storage_state.json"
    storage_state_path.write_text("{}", encoding="utf-8")
    request = _request(lookback_days=30, max_pages=10)
    browser = XueqiuInvestorHistoryBrowser(
        XueqiuBrowserConfig(
            storage_state_path=str(storage_state_path),
            response_wait_ms=0,
            max_idle_cycles_without_progress=2,
        )
    )

    result = asyncio.run(browser.capture(request))

    assert result.stop_reason is InvestorHistoryStopReason.NO_PROGRESS
    assert result.pagination_trace[-1].repeated_item_count >= 1
    assert result.pagination_trace[-1].new_status_id_count == 0
    assert result.scroll_trace[-1].progress is False


def test_human_assisted_mode_uses_current_page_without_profile_goto(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage()

    async def manual_navigation(_function, *_args, **_kwargs):
        page.url = f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
        page.emit_response(
            _FakeResponse(
                _FakeRequest(f"{page.endpoint}?page=1"),
                {"statuses": [_status("manual-current", END - timedelta(days=1))]},
            )
        )
        return None

    monkeypatch.setattr(asyncio, "to_thread", manual_navigation)
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    storage_state = tmp_path / "storage_state.json"
    storage_state.write_text("{}", encoding="utf-8")
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=3,
        max_idle_cycles=1,
        max_duration_seconds=5,
        human_assisted=True,
        until=END,
    )
    browser = XueqiuInvestorHistoryBrowser(
        XueqiuBrowserConfig(
            storage_state_path=str(storage_state),
            response_wait_ms=0,
            max_idle_cycles_without_progress=1,
        )
    )

    result = asyncio.run(browser.capture(request))

    assert page.goto_calls == 0
    assert page.url == f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
    assert result.posts[0].source_event_id == "manual-current"
    assert result.stop_reason is InvestorHistoryStopReason.NO_PROGRESS


def test_human_assisted_verification_stops_safely(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage()
    page.body_text = "滑动验证"

    async def manual_navigation(_function, *_args, **_kwargs):
        page.url = f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
        return None

    monkeypatch.setattr(asyncio, "to_thread", manual_navigation)
    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _FakePlaywrightManager(page),
    )
    storage_state = tmp_path / "storage_state.json"
    storage_state.write_text("{}", encoding="utf-8")
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=2,
        max_duration_seconds=5,
        human_assisted=True,
        until=END,
    )

    with pytest.raises(ManualVerificationRequired, match="MANUAL_VERIFICATION_REQUIRED"):
        asyncio.run(
            XueqiuInvestorHistoryBrowser(
                XueqiuBrowserConfig(
                    storage_state_path=str(storage_state),
                    response_wait_ms=0,
                )
            ).capture(request)
        )


def test_cdp_attach_reuses_existing_page_without_new_context_or_goto(
    monkeypatch: pytest.MonkeyPatch,
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(old_age_days=30)
    page.url = f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
    manager = _FakePlaywrightManager(page)

    async def confirm(_function, *_args, **_kwargs):
        page.emit_response(
            _FakeResponse(
                _FakeRequest(f"{page.endpoint}?page=1"),
                {"statuses": [_status("page-1", END - timedelta(days=30))]},
            )
        )
        return None

    monkeypatch.setattr(asyncio, "to_thread", confirm)
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: manager)
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=3,
        max_idle_cycles=2,
        max_duration_seconds=5,
        human_assisted=True,
        attach_cdp_endpoint="http://127.0.0.1:9222",
        until=END,
    )

    result = asyncio.run(
        XueqiuInvestorHistoryBrowser(XueqiuBrowserConfig(response_wait_ms=0)).capture(request)
    )

    assert manager.playwright.chromium.cdp_endpoints == ["http://127.0.0.1:9222"]
    assert page.goto_calls == 0
    assert result.connected_context_count == 1
    assert result.connected_page_count == 1
    assert result.selected_page_url == f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
    assert result.stop_reason is InvestorHistoryStopReason.TARGET_REACHED


def test_cdp_page_control_advances_page_and_stops_at_30d(
    monkeypatch: pytest.MonkeyPatch,
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(
        page_control_pages=(1, 2, 3),
        page_ages={1: 1, 2: 10, 3: 30},
    )
    page.url = f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
    manager = _FakePlaywrightManager(page)

    async def confirm(_function, *_args, **_kwargs):
        page.emit_response(
            _FakeResponse(
                _FakeRequest(f"{page.endpoint}?page=1"),
                {"statuses": [_status("page-1", END - timedelta(days=1))]},
            )
        )
        return None

    monkeypatch.setattr(asyncio, "to_thread", confirm)
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: manager)
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=5,
        max_idle_cycles=2,
        max_duration_seconds=5,
        human_assisted=True,
        attach_cdp_endpoint="http://127.0.0.1:9222",
        until=END,
    )

    result = asyncio.run(
        XueqiuInvestorHistoryBrowser(XueqiuBrowserConfig(response_wait_ms=0)).capture(request)
    )

    assert page.wheel_calls == 0
    assert page.goto_calls == 0
    assert result.pages == 3
    assert len(result.posts) == 3
    assert result.oldest_published_time == END - timedelta(days=30)
    assert result.stop_reason is InvestorHistoryStopReason.TARGET_REACHED
    assert [trace.response_page for trace in result.page_control_trace] == [2, 3]
    assert result.page_control_trace[0].control_role == "link"
    assert result.page_control_trace[0].control_selector == 'role=link name="下一页"'
    assert all(trace.progress for trace in result.page_control_trace)


def test_cdp_page_control_disabled_state_is_end_of_pagination(
    monkeypatch: pytest.MonkeyPatch,
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(page_control_pages=(1, 2), page_ages={1: 1, 2: 2})
    page.url = f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
    manager = _FakePlaywrightManager(page)

    async def confirm(_function, *_args, **_kwargs):
        page.emit_response(
            _FakeResponse(
                _FakeRequest(f"{page.endpoint}?page=1"),
                {"statuses": [_status("page-1", END - timedelta(days=1))]},
            )
        )
        return None

    monkeypatch.setattr(asyncio, "to_thread", confirm)
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: manager)
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=5,
        max_idle_cycles=2,
        max_duration_seconds=5,
        human_assisted=True,
        attach_cdp_endpoint="http://127.0.0.1:9222",
        until=END,
    )

    result = asyncio.run(
        XueqiuInvestorHistoryBrowser(XueqiuBrowserConfig(response_wait_ms=0)).capture(request)
    )

    assert result.pages == 2
    assert result.stop_reason is InvestorHistoryStopReason.END_OF_PAGINATION
    assert result.page_control_trace[-1].end_state is True
    assert result.page_control_trace[-1].clicked is False


def test_cdp_page_control_repeated_ids_do_not_count_as_progress(
    monkeypatch: pytest.MonkeyPatch,
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage(
        page_control_pages=(1, 2, 3),
        page_ages={1: 1, 2: 2, 3: 3},
        repeat_page_ids=True,
    )
    page.url = f"https://xueqiu.com/u/{PLATFORM_USER_ID}"

    async def confirm(_function, *_args, **_kwargs):
        page.emit_response(
            _FakeResponse(
                _FakeRequest(f"{page.endpoint}?page=1"),
                {"statuses": [_status("page-1", END - timedelta(days=1))]},
            )
        )
        return None

    monkeypatch.setattr(asyncio, "to_thread", confirm)
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: _FakePlaywrightManager(page))
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=5,
        max_idle_cycles=1,
        max_duration_seconds=5,
        human_assisted=True,
        attach_cdp_endpoint="http://127.0.0.1:9222",
        until=END,
    )

    result = asyncio.run(
        XueqiuInvestorHistoryBrowser(XueqiuBrowserConfig(response_wait_ms=0)).capture(request)
    )

    assert result.stop_reason is InvestorHistoryStopReason.NO_PROGRESS
    assert result.page_control_trace[-1].page_advanced is True
    assert result.page_control_trace[-1].new_status_id_count == 0
    assert result.page_control_trace[-1].progress is False


def test_cdp_page_control_missing_stops_without_scroll_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage()
    page.url = f"https://xueqiu.com/u/{PLATFORM_USER_ID}"
    manager = _FakePlaywrightManager(page)

    async def confirm(_function, *_args, **_kwargs):
        page.emit_response(
            _FakeResponse(
                _FakeRequest(f"{page.endpoint}?page=1"),
                {"statuses": [_status("page-1", END - timedelta(days=1))]},
            )
        )
        return None

    monkeypatch.setattr(asyncio, "to_thread", confirm)
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: manager)
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        max_pages=5,
        max_idle_cycles=2,
        max_duration_seconds=5,
        human_assisted=True,
        attach_cdp_endpoint="http://127.0.0.1:9222",
        until=END,
    )

    result = asyncio.run(
        XueqiuInvestorHistoryBrowser(XueqiuBrowserConfig(response_wait_ms=0)).capture(request)
    )

    assert page.wheel_calls == 0
    assert result.stop_reason is InvestorHistoryStopReason.PAGE_CONTROL_NOT_FOUND
    assert result.page_control_trace[-1].has_pagination_control is False


def test_cdp_attach_rejects_non_target_existing_page(monkeypatch: pytest.MonkeyPatch):
    import playwright.async_api as playwright_api

    page = _FakeHistoryPage()
    page.url = "https://xueqiu.com/u/other-user"
    manager = _FakePlaywrightManager(page)
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: manager)
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        human_assisted=True,
        attach_cdp_endpoint="http://127.0.0.1:9222",
        until=END,
    )

    with pytest.raises(NetworkUnavailable, match="no existing"):
        asyncio.run(XueqiuInvestorHistoryBrowser(XueqiuBrowserConfig()).capture(request))


class _CdpFailureChromium:
    async def connect_over_cdp(self, endpoint):
        raise RuntimeError("connection refused")


class _CdpFailurePlaywright:
    def __init__(self):
        self.chromium = _CdpFailureChromium()


class _CdpFailureManager:
    async def __aenter__(self):
        return _CdpFailurePlaywright()

    async def __aexit__(self, exc_type, exc, traceback):
        return None


def test_cdp_endpoint_unavailable_is_explicit(monkeypatch: pytest.MonkeyPatch):
    import playwright.async_api as playwright_api

    monkeypatch.setattr(
        playwright_api,
        "async_playwright",
        lambda: _CdpFailureManager(),
    )
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=INVESTOR_ID,
        platform_user_id=PLATFORM_USER_ID,
        lookback_days=30,
        human_assisted=True,
        attach_cdp_endpoint="http://127.0.0.1:9222",
        until=END,
    )

    with pytest.raises(CdpNotAvailable, match="could not connect"):
        asyncio.run(XueqiuInvestorHistoryBrowser(XueqiuBrowserConfig()).capture(request))
