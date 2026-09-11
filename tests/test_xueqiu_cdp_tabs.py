import asyncio

import pytest

from collectors.xueqiu.cdp_tabs import (
    CdpTabDiscoveryResult,
    detect_xueqiu_user_id,
    discover_cdp_tabs,
    safe_page_url,
)
from collectors.xueqiu.errors import CdpNotAvailable


class _FakePage:
    def __init__(self, url: str, title: str) -> None:
        self.url = url
        self._title = title

    async def title(self) -> str:
        return self._title


class _FakeContext:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


class _FakeBrowser:
    def __init__(self) -> None:
        self.contexts = [
            _FakeContext(
                [
                    _FakePage(
                        "https://xueqiu.com/u/9086045991?tab=timeline#latest",
                        "雪球 Investor",
                    ),
                    _FakePage("https://example.com/", "Example"),
                ]
            ),
            _FakeContext([_FakePage("https://xueqiu.com/u/4364582897", "雪球 2")]),
        ]


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.browser = browser
        self.endpoints: list[str] = []

    async def connect_over_cdp(self, endpoint: str) -> _FakeBrowser:
        self.endpoints.append(endpoint)
        return self.browser


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium


class _FakePlaywrightManager:
    def __init__(self, playwright: _FakePlaywright) -> None:
        self.playwright = playwright

    async def __aenter__(self) -> _FakePlaywright:
        return self.playwright

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def test_user_id_detection_is_explicit_and_query_safe() -> None:
    assert detect_xueqiu_user_id("https://xueqiu.com/u/9086045991?tab=timeline") == "9086045991"
    assert detect_xueqiu_user_id("https://xueqiu.com/statuses/123") is None
    assert detect_xueqiu_user_id("https://example.com/u/9086045991") is None
    assert safe_page_url("https://xueqiu.com/u/1?secret=value#fragment") == (
        "https://xueqiu.com/u/1"
    )


def test_discovery_reads_existing_contexts_and_pages_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import playwright.async_api as playwright_api

    browser = _FakeBrowser()
    chromium = _FakeChromium(browser)
    manager = _FakePlaywrightManager(_FakePlaywright(chromium))
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: manager)

    result = asyncio.run(discover_cdp_tabs("http://127.0.0.1:9222"))

    assert isinstance(result, CdpTabDiscoveryResult)
    assert chromium.endpoints == ["http://127.0.0.1:9222"]
    assert result.context_count == 2
    assert result.page_count == 3
    assert result.tabs[0].detected_xueqiu_user_id == "9086045991"
    assert result.tabs[0].url == "https://xueqiu.com/u/9086045991"
    assert result.tabs[1].detected_xueqiu_user_id is None
    assert result.tabs[2].detected_xueqiu_user_id == "4364582897"


class _FailingChromium:
    async def connect_over_cdp(self, endpoint: str) -> object:
        raise RuntimeError("connection refused")


class _FailingPlaywright:
    chromium = _FailingChromium()


class _FailingManager:
    async def __aenter__(self) -> _FailingPlaywright:
        return _FailingPlaywright()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def test_discovery_reports_cdp_attach_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import playwright.async_api as playwright_api

    monkeypatch.setattr(playwright_api, "async_playwright", lambda: _FailingManager())

    with pytest.raises(CdpNotAvailable, match="could not connect"):
        asyncio.run(discover_cdp_tabs("http://127.0.0.1:9222"))
