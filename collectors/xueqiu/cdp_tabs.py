"""Read-only discovery of tabs already open in an Edge CDP session."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from urllib.parse import unquote, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

from collectors.xueqiu.errors import BrowserDependencyMissing, CdpNotAvailable

_XUEQIU_HOSTS = frozenset({"xueqiu.com", "www.xueqiu.com"})


class CdpTabDescriptor(BaseModel):
    """Safe, read-only metadata for one page in an attached browser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context_index: int = Field(ge=0)
    page_index: int = Field(ge=0)
    url: str
    title: str
    detected_xueqiu_user_id: str | None = None


class CdpTabDiscoveryResult(BaseModel):
    """The complete tab inventory observed from one CDP connection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cdp_endpoint: str
    context_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    tabs: tuple[CdpTabDescriptor, ...] = ()


def safe_page_url(url: str) -> str:
    """Remove query and fragment values before a URL is shown in a report."""

    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def detect_xueqiu_user_id(url: str) -> str | None:
    """Extract a user id only from the explicit Xueqiu ``/u/<id>`` path."""

    parsed = urlsplit(url)
    if parsed.hostname not in _XUEQIU_HOSTS:
        return None
    segments = [unquote(segment).strip() for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0].casefold() != "u":
        return None
    return segments[1] or None


async def _resolve(value: object) -> object:
    if callable(value):
        value = value()
    if inspect.isawaitable(value):
        value = await value
    return value


async def _read_collection(owner: object, attribute: str) -> tuple[object, ...]:
    value = await _resolve(getattr(owner, attribute, ()))
    if value is None:
        return ()
    if isinstance(value, Iterable) and not isinstance(value, str | bytes | bytearray):
        return tuple(value)
    raise CdpNotAvailable(f"CDP object attribute {attribute!r} is not a collection")


async def _read_page_url(page: object) -> str:
    value = await _resolve(getattr(page, "url", ""))
    return str(value or "")


async def _read_page_title(page: object) -> str:
    try:
        value = await _resolve(page.title)
    except Exception:
        return "<title unavailable>"
    return str(value or "")[:255]


async def discover_cdp_tabs(endpoint: str) -> CdpTabDiscoveryResult:
    """Attach to an existing Chromium CDP endpoint and inspect its pages.

    The function only reads the browser's existing contexts, pages, URLs, and
    titles. It deliberately has no navigation or persistence boundary.
    """

    normalized_endpoint = endpoint.strip()
    if not normalized_endpoint:
        raise ValueError("CDP endpoint must not be blank")

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise BrowserDependencyMissing(
            "Playwright is not installed; install project dependencies before CDP discovery"
        ) from exc

    try:
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.connect_over_cdp(normalized_endpoint)
            except Exception as exc:
                raise CdpNotAvailable(
                    f"could not connect to Edge CDP endpoint {normalized_endpoint}"
                ) from exc

            contexts = await _read_collection(browser, "contexts")
            descriptors: list[CdpTabDescriptor] = []
            for context_index, context in enumerate(contexts):
                pages = await _read_collection(context, "pages")
                for page_index, page in enumerate(pages):
                    raw_url = await _read_page_url(page)
                    descriptors.append(
                        CdpTabDescriptor(
                            context_index=context_index,
                            page_index=page_index,
                            url=safe_page_url(raw_url),
                            title=await _read_page_title(page),
                            detected_xueqiu_user_id=detect_xueqiu_user_id(raw_url),
                        )
                    )
    except CdpNotAvailable:
        raise
    except Exception as exc:
        raise CdpNotAvailable("could not inspect pages from the Edge CDP session") from exc

    return CdpTabDiscoveryResult(
        cdp_endpoint=normalized_endpoint,
        context_count=len(contexts),
        page_count=len(descriptors),
        tabs=tuple(descriptors),
    )
