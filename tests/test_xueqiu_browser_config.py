from collectors.xueqiu.browser import chromium_launch_options
from collectors.xueqiu.contracts import XueqiuBrowserConfig


def test_default_browser_channel_is_msedge() -> None:
    assert XueqiuBrowserConfig().browser_channel == "msedge"


def test_channel_is_used_when_executable_path_is_missing() -> None:
    options = chromium_launch_options(XueqiuBrowserConfig())

    assert options == {"headless": False, "channel": "msedge"}


def test_explicit_executable_path_overrides_channel() -> None:
    options = chromium_launch_options(
        XueqiuBrowserConfig(
            browser_channel="msedge",
            browser_executable_path="C:/custom/browser.exe",
        )
    )

    assert options == {
        "headless": False,
        "executable_path": "C:/custom/browser.exe",
    }
