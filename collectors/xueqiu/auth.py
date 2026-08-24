import asyncio
from pathlib import Path

from collectors.xueqiu.browser import (
    AUTHENTICATION_MARKERS,
    BLOCKED_MARKERS,
    chromium_launch_options,
)
from collectors.xueqiu.contracts import XueqiuBrowserConfig
from collectors.xueqiu.errors import (
    AuthenticationRequired,
    BrowserDependencyMissing,
    NavigationFailed,
    RateLimitedOrBlocked,
)


class XueqiuAuthenticator:
    """Visible, user-confirmed authentication with no credential handling."""

    def __init__(self, config: XueqiuBrowserConfig) -> None:
        self._config = config

    async def authenticate(self) -> Path:
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserDependencyMissing(
                "Playwright is not installed; install project dependencies before authentication"
            ) from exc

        storage_path = Path(self._config.storage_state_path)
        profile_path = Path(self._config.persistent_profile_path)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            launch_options: dict[str, object] = {
                "headless": False,
                "user_data_dir": str(profile_path),
            }
            launch_options.update(chromium_launch_options(self._config, headless=False))
            context = await playwright.chromium.launch_persistent_context(**launch_options)
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto(
                    "https://xueqiu.com/",
                    wait_until="domcontentloaded",
                    timeout=self._config.navigation_timeout_ms,
                )
                print("请在可见浏览器中手动完成雪球登录。完成后回到终端按 Enter。")
                await asyncio.to_thread(input)
                body_text = await page.locator("body").inner_text()
                title = await page.title()
                if any(marker in body_text for marker in BLOCKED_MARKERS) or "验证" in title:
                    raise RateLimitedOrBlocked(
                        "Xueqiu requested verification; authentication state was not saved"
                    )
                if any(marker in body_text for marker in AUTHENTICATION_MARKERS):
                    raise AuthenticationRequired("Xueqiu login was not completed")
                await context.storage_state(path=str(storage_path))
            except PlaywrightTimeoutError as exc:
                raise NavigationFailed("Xueqiu authentication page timed out") from exc
            except PlaywrightError as exc:
                raise NavigationFailed("Xueqiu authentication page failed") from exc
            finally:
                await context.close()
        return storage_path
