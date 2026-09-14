"""Bounded Xueqiu Investor profile-history probe.

This module is intentionally separate from the authenticated Following Feed
runtime. It observes the JSON responses emitted while navigating one Investor
profile page and emits normalized RawEventDTO values through the existing
source-adapter/DataPipeline boundary.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from collectors.xueqiu.browser import (
    AUTHENTICATION_MARKERS,
    BLOCKED_MARKERS,
    NO_CONTENT_MARKERS,
    chromium_launch_options,
    validate_xueqiu_homepage_url,
)
from collectors.xueqiu.contracts import XueqiuBrowserConfig
from collectors.xueqiu.errors import (
    AuthenticationRequired,
    BrowserDependencyMissing,
    CdpNotAvailable,
    ManualVerificationRequired,
    NavigationFailed,
    NetworkUnavailable,
    NoContent,
    RateLimitedOrBlocked,
    XueqiuCollectorError,
)
from collectors.xueqiu.parser import XueqiuFollowingFeedParser, parse_xueqiu_time
from contracts import (
    CollectionCoverageStatus,
    CollectionMode,
    CollectionRequest,
    CollectionRunCreate,
    CollectionTransport,
    FeedPostItem,
    RawEventDTO,
)

HISTORY_SOURCE = "xueqiu"
HISTORY_PROFILE_URL_TEMPLATE = "https://xueqiu.com/u/{platform_user_id}"
_HISTORY_PATH_HINTS = ("status", "timeline")
_CURSOR_KEYS = (
    "page",
    "max_id",
    "next_id",
    "next_max_id",
    "cursor",
    "since_id",
)
_HISTORY_STATUS_CONTAINER_KEYS = (
    "statuses",
    "user_timeline",
    "timeline",
    "items",
    "list",
    "data",
)
_NON_CHRONOLOGICAL_FLAG_KEYS = (
    "is_top",
    "is_sticky",
    "is_pinned",
    "pinned",
    "sticky",
    "top",
    "top_status",
    "sticky_status",
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class InvestorHistoryStopReason(StrEnum):
    TARGET_REACHED = "TARGET_REACHED"
    END_OF_HISTORY = "END_OF_HISTORY"
    END_OF_PAGINATION = "END_OF_PAGINATION"
    MAX_PAGES = "MAX_PAGES"
    NO_PROGRESS = "NO_PROGRESS"
    PAGE_CONTROL_NOT_FOUND = "PAGE_CONTROL_NOT_FOUND"
    FIRST_PAGE_UNAVAILABLE = "FIRST_PAGE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    NO_CONTENT = "NO_CONTENT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    BLOCKED = "BLOCKED"
    MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
    CDP_NOT_AVAILABLE = "CDP_NOT_AVAILABLE"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    BROWSER_DEPENDENCY_MISSING = "BROWSER_DEPENDENCY_MISSING"
    MAX_DURATION = "MAX_DURATION"


class InvestorHistoryProbeStatus(StrEnum):
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"


class InvestorHistoryCompleteness(StrEnum):
    OBSERVED_HISTORY = "OBSERVED_HISTORY"
    COMPLETE_HISTORY = "COMPLETE_HISTORY"
    COMPLETENESS_UNKNOWN = "COMPLETENESS_UNKNOWN"


class InvestorHistoryCollectionRequest(CollectionRequest):
    """Bounded request for one Investor profile-history probe."""

    lookback_days: int = Field(gt=0, le=3650)
    max_pages: int = Field(default=10, ge=1, le=100)
    max_idle_cycles: int | None = Field(default=None, ge=1, le=20)
    max_duration_seconds: int = Field(default=180, ge=1, le=3600)
    human_assisted: bool = False
    attach_cdp_endpoint: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_history_window(self) -> InvestorHistoryCollectionRequest:
        if self.since is None or self.until is None:
            raise ValueError("history probes require both since and until")
        if self.since > self.until:
            raise ValueError("history since must be earlier than or equal to until")
        if self.attach_cdp_endpoint and not self.human_assisted:
            raise ValueError("attach_cdp_endpoint requires human_assisted=True")
        return self

    @classmethod
    def for_lookback(
        cls,
        *,
        investor_id: UUID,
        platform_user_id: str,
        lookback_days: int,
        max_pages: int = 10,
        max_idle_cycles: int | None = None,
        max_duration_seconds: int = 180,
        human_assisted: bool = False,
        attach_cdp_endpoint: str | None = None,
        until: datetime | None = None,
    ) -> InvestorHistoryCollectionRequest:
        end = until or utc_now()
        if end.tzinfo is None or end.utcoffset() is None:
            raise ValueError("until must be timezone-aware")
        end = end.astimezone(UTC)
        return cls(
            investor_id=investor_id,
            platform_user_id=platform_user_id,
            homepage_url=HISTORY_PROFILE_URL_TEMPLATE.format(
                platform_user_id=platform_user_id.strip()
            ),
            since=end - timedelta(days=lookback_days),
            until=end,
            requested_at=end,
            lookback_days=lookback_days,
            max_pages=max_pages,
            max_idle_cycles=max_idle_cycles,
            max_duration_seconds=max_duration_seconds,
            human_assisted=human_assisted,
            attach_cdp_endpoint=attach_cdp_endpoint,
        )


class InvestorHistoryProbeResult(BaseModel):
    """Metrics emitted by one bounded profile-history probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: InvestorHistoryProbeStatus
    investor_id: UUID
    platform_user_id: str
    lookback_days: int = Field(gt=0)
    max_pages: int = Field(ge=1)
    max_duration_seconds: int = Field(default=180, ge=1)
    human_assisted: bool = False
    completeness: InvestorHistoryCompleteness = InvestorHistoryCompleteness.COMPLETENESS_UNKNOWN
    cdp_endpoint: str | None = None
    connected_context_count: int = Field(default=0, ge=0)
    connected_page_count: int = Field(default=0, ge=0)
    selected_page_url: str | None = None
    selected_page_title: str | None = None
    pages: int = Field(ge=0)
    valid_posts: int = Field(ge=0)
    inserted_raw_events: int = Field(ge=0)
    duplicate_raw_events: int = Field(ge=0)
    duplicate_posts_in_capture: int = Field(ge=0)
    parse_failures: int = Field(ge=0)
    newest_published_time: AwareDatetime | None = None
    oldest_published_time: AwareDatetime | None = None
    actual_history_span_days: float | None = Field(default=None, ge=0)
    cutoff_proven: bool = False
    cutoff_evidence_count: int = Field(default=0, ge=0)
    first_page_bootstrap_attempted: bool = False
    first_page_bootstrap_succeeded: bool = False
    stop_reason: InvestorHistoryStopReason
    observed_endpoint_paths: tuple[str, ...] = ()
    pagination_trace: tuple[HistoryPaginationTrace, ...] = ()
    scroll_trace: tuple[HistoryScrollTrace, ...] = ()
    page_control_trace: tuple[HistoryPageControlTrace, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class ParsedHistoryPage:
    """Internal normalized result for one observed history response."""

    posts: tuple[FeedPostItem, ...]
    parse_failures: int
    has_more: bool | None
    endpoint_path: str
    status_ids: tuple[str, ...] = ()
    status_times: tuple[tuple[str, AwareDatetime], ...] = ()
    chronology_reliable: bool = False


class HistoryPaginationTrace(BaseModel):
    """Safe trace for one real status/timeline response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    request_path: str
    http_status: int = Field(ge=0)
    content_type: str
    pagination_query: dict[str, str] = Field(default_factory=dict)
    response_item_count: int = Field(ge=0)
    newest_status_id: str | None = None
    newest_published_time: AwareDatetime | None = None
    oldest_status_id: str | None = None
    oldest_published_time: AwareDatetime | None = None
    response_ids_fingerprint: str
    repeated_item_count: int = Field(ge=0)
    new_status_id_count: int = Field(default=0, ge=0)
    duplicate_response: bool = False
    pagination_fields: dict[str, str] = Field(default_factory=dict)


class HistoryScrollTrace(BaseModel):
    """Trace for one manual/automatic scroll cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    mode: str
    scroll_y_before: float | None = None
    scroll_y_after: float | None = None
    scroll_height_before: float | None = None
    scroll_height_after: float | None = None
    loading_before: bool | None = None
    loading_after: bool | None = None
    new_timeline_request_count: int = Field(ge=0)
    new_status_id_count: int = Field(default=0, ge=0)
    oldest_published_time_after: AwareDatetime | None = None
    progress: bool


class HistoryPageControlTrace(BaseModel):
    """Trace for one observed DOM pagination-control decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    current_page: int | None = Field(default=None, ge=1)
    next_page: int | None = Field(default=None, ge=1)
    has_pagination_control: bool
    next_available: bool
    control_role: str | None = None
    control_selector: str | None = None
    disabled: bool | None = None
    end_state: bool
    clicked: bool
    response_page: int | None = Field(default=None, ge=1)
    page_advanced: bool
    new_status_id_count: int = Field(default=0, ge=0)
    progress: bool


class InvestorHistoryCapture(BaseModel):
    """Successful bounded capture before optional RawEvent persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    posts: tuple[FeedPostItem, ...] = ()
    pages: int = Field(ge=0)
    duplicate_posts_in_capture: int = Field(ge=0)
    parse_failures: int = Field(ge=0)
    stop_reason: InvestorHistoryStopReason
    newest_published_time: AwareDatetime | None = None
    oldest_published_time: AwareDatetime | None = None
    actual_history_span_days: float | None = Field(default=None, ge=0)
    cutoff_proven: bool = False
    cutoff_evidence_count: int = Field(default=0, ge=0)
    first_page_bootstrap_attempted: bool = False
    first_page_bootstrap_succeeded: bool = False
    observed_endpoint_paths: tuple[str, ...] = ()
    connected_context_count: int = Field(default=0, ge=0)
    connected_page_count: int = Field(default=0, ge=0)
    selected_page_url: str | None = None
    selected_page_title: str | None = None
    pagination_trace: tuple[HistoryPaginationTrace, ...] = ()
    scroll_trace: tuple[HistoryScrollTrace, ...] = ()
    page_control_trace: tuple[HistoryPageControlTrace, ...] = ()


def browser_config(
    *,
    headless: bool = False,
    response_wait_ms: int = 1500,
) -> XueqiuBrowserConfig:
    """Use the same login-state environment variables as the existing smoke runner."""

    return XueqiuBrowserConfig(
        storage_state_path=os.getenv(
            "XUEQIU_STORAGE_STATE_PATH",
            ".local/xueqiu/storage_state.json",
        ),
        persistent_profile_path=os.getenv("XUEQIU_PROFILE_PATH", ".local/xueqiu/profile"),
        browser_channel=os.getenv("XUEQIU_BROWSER_CHANNEL", "msedge"),
        browser_executable_path=os.getenv("XUEQIU_BROWSER_EXECUTABLE_PATH"),
        headless=headless,
        response_wait_ms=response_wait_ms,
    )


def _truthy_history_marker(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().casefold() in {
            "1",
            "true",
            "yes",
            "top",
            "sticky",
            "pinned",
            "置顶",
        }
    return False


def _is_non_chronological_item(item: Mapping[str, object]) -> bool:
    if any(_truthy_history_marker(item.get(key)) for key in _NON_CHRONOLOGICAL_FLAG_KEYS):
        return True
    mark_description = item.get("mark_desc")
    if isinstance(mark_description, str):
        marker = mark_description.casefold()
        return any(value in marker for value in ("sticky", "pinned", "置顶"))
    return False


def _looks_like_history_status(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and "id" in value
        and any(
            key in value
            for key in ("created_at", "timeBefore", "text", "description", "user_id", "user")
        )
    )


def _history_status_values(payload: Mapping[str, object]) -> list[object]:
    for key in _HISTORY_STATUS_CONTAINER_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value

    candidate_lists = [
        value
        for value in payload.values()
        if isinstance(value, list) and any(_looks_like_history_status(item) for item in value)
    ]
    return candidate_lists[0] if len(candidate_lists) == 1 else []


def _candidate_status_items(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [
        item
        for item in _history_status_values(payload)
        if _looks_like_history_status(item)
        and isinstance(item, Mapping)
        and not _is_non_chronological_item(item)
    ]


def _raw_author_id(item: Mapping[str, object]) -> str | None:
    value = item.get("user_id")
    user = item.get("user")
    if value is None and isinstance(user, Mapping):
        value = user.get("id")
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).strip()
    return normalized or None


def _history_response_path(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.hostname not in {"xueqiu.com", "www.xueqiu.com"}:
        return None
    path = parsed.path.lower()
    return path if any(hint in path for hint in _HISTORY_PATH_HINTS) else None


def _is_primary_timeline_path(path: str) -> bool:
    """Use only the canary-observed user timeline response for pagination."""

    return path.endswith("/user_timeline.json")


def validate_current_investor_url(current_url: str, expected_user_id: str) -> str:
    """Validate the page manually opened by the user without navigating."""

    parsed = urlparse(current_url)
    if parsed.hostname not in {"xueqiu.com", "www.xueqiu.com"}:
        raise NavigationFailed("current page is not an xueqiu.com page")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0] != "u" or not segments[1].strip():
        raise NavigationFailed("current page is not a Xueqiu Investor profile")
    actual_user_id = segments[1].strip()
    if actual_user_id != expected_user_id.strip():
        raise NavigationFailed(
            "current Xueqiu Investor profile does not match the requested platform user id"
        )
    return current_url


def _response_has_history_container(payload: Mapping[str, object]) -> bool:
    return any(isinstance(value, list) for value in payload.values())


def _page_signature(url: str, payload: Mapping[str, object]) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    cursor = {
        key: values[0] if values else None
        for key, values in sorted(query.items())
        if key in _CURSOR_KEYS
    }
    identity = {
        "path": parsed.path,
        "cursor": cursor,
        "payload": payload,
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _payload_has_more(payload: Mapping[str, object]) -> bool | None:
    for key in ("has_more", "hasMore", "has_next", "hasNext", "more"):
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)

    for key in ("next_id", "next_max_id", "next_cursor"):
        if key in payload:
            value = payload.get(key)
            return value is not None and str(value).strip() not in {"", "0"}

    status_lists = [
        value
        for key, value in payload.items()
        if key in {"statuses", "items", "list", "data", "timeline", "user_timeline"}
        and isinstance(value, list)
    ]
    if status_lists and any(len(value) == 0 for value in status_lists):
        return False
    return None


def _safe_trace_value(value: object, *, key: str) -> str:
    text = str(value)
    if key.lower() in {"page", "offset", "limit"} and len(text) <= 32:
        return text
    return f"{type(value).__name__}:{len(text)}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def _trace_query_params(url: str) -> dict[str, str]:
    query = parse_qs(urlparse(url).query, keep_blank_values=True)
    return {
        key: _safe_trace_value(values[0] if values else "", key=key)
        for key, values in sorted(query.items())
        if any(
            token in key.lower() for token in ("page", "max", "cursor", "since", "last", "offset")
        )
    }


def _trace_response_fields(payload: Mapping[str, object]) -> dict[str, str]:
    return {
        str(key): _safe_trace_value(value, key=str(key))
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
        if any(
            token in str(key).lower()
            for token in ("page", "max", "cursor", "since", "last", "offset", "next")
        )
    }


def _trace_status_snapshot(
    payload: Mapping[str, object],
    *,
    expected_user_id: str,
    now: datetime,
) -> tuple[tuple[str, ...], tuple[tuple[str, datetime], ...]]:
    ids: list[str] = []
    status_times: list[tuple[str, datetime]] = []
    for item in _candidate_status_items(payload):
        author_id = _raw_author_id(item)
        if author_id is not None and author_id != expected_user_id:
            continue
        status_id = str(item.get("id", "")).strip()
        if not status_id:
            continue
        ids.append(status_id)
        raw_time = item.get("created_at") or item.get("timeBefore")
        try:
            status_times.append((status_id, parse_xueqiu_time(raw_time, now=now)))
        except Exception:
            continue
    return tuple(ids), tuple(status_times)


async def _read_scroll_state(page: object) -> dict[str, float | bool | None]:
    try:
        value = await page.evaluate(  # type: ignore[attr-defined]
            """() => {
              const body = document.body;
              const doc = document.documentElement;
              const loading = document.querySelector(
                '[aria-busy="true"], [class*="loading"], [class*="spinner"]'
              );
              return {
                scroll_y: window.scrollY,
                scroll_height: Math.max(body?.scrollHeight || 0, doc?.scrollHeight || 0),
                loading: Boolean(loading)
              };
            }"""
        )
        if isinstance(value, Mapping):
            return {
                "scroll_y": float(value.get("scroll_y", 0) or 0),
                "scroll_height": float(value.get("scroll_height", 0) or 0),
                "loading": bool(value.get("loading", False)),
            }
    except Exception:
        pass
    return {"scroll_y": None, "scroll_height": None, "loading": None}


_PAGE_CONTROL_DISCOVERY_SCRIPT = """
() => {
  // xueqiu_page_control_discovery_v1
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const visible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && rect.width > 0
      && rect.height > 0;
  };
  const isDisabled = (element) => Boolean(
    element.disabled
      || element.getAttribute('aria-disabled') === 'true'
      || /\\b(disabled|disable)\\b/i.test(String(element.className || ''))
  );
  const interactive = Array.from(
    document.querySelectorAll('a,button,[role="button"],[role="link"]')
  ).filter(visible).map((element) => {
    const tag = element.tagName.toLowerCase();
    const explicitRole = normalize(element.getAttribute('role'));
    const role = explicitRole || (tag === 'a' ? 'link' : tag === 'button' ? 'button' : 'control');
    const text = normalize(element.innerText || element.textContent);
    const ariaLabel = normalize(element.getAttribute('aria-label'));
    const title = normalize(element.getAttribute('title'));
    const dataPage = normalize(
      element.getAttribute('data-page')
        || element.getAttribute('data-pagenum')
        || element.getAttribute('data-page-number')
    );
    const numberText = dataPage || text;
    const pageNumber = /^\\d+$/.test(numberText) ? Number(numberText) : null;
    const className = String(element.className || '');
    const current = element.getAttribute('aria-current') === 'page'
      || /\\b(active|current|selected)\\b/i.test(className);
    return {
      element,
      tag,
      role,
      text,
      ariaLabel,
      title,
      dataPage,
      pageNumber,
      current,
      disabled: isDisabled(element),
    };
  });
  const pageItems = interactive.filter((item) => item.pageNumber !== null);
  const currentItem = pageItems.find((item) => item.current);
  const currentPage = currentItem?.pageNumber ?? null;
  const nextCandidates = interactive.filter((item) => {
    const label = `${item.ariaLabel} ${item.text} ${item.title}`.toLowerCase();
    return /下一页|下页|next|›|»/.test(label) || item.text === '>' || item.text === '→';
  });
  const fallback = currentPage === null
    ? null
    : pageItems.find((item) => item.pageNumber === currentPage + 1);
  const selected = nextCandidates.find((item) => !item.disabled)
    || nextCandidates[0]
    || fallback
    || null;
  const label = selected
    ? (selected.ariaLabel || selected.text || selected.title || String(selected.pageNumber || ''))
    : '';
  const selector = selected
    ? `role=${selected.role} name=${JSON.stringify(label)}`
    : null;
  return {
    has_pagination_control: pageItems.length > 0 || nextCandidates.length > 0,
    current_page: currentPage,
    next_page: selected?.pageNumber ?? (currentPage === null ? null : currentPage + 1),
    next_available: Boolean(selected && !selected.disabled),
    control_role: selected?.role ?? null,
    control_selector: selector,
    disabled: selected?.disabled ?? null,
    end_state: Boolean(selected?.disabled)
      || Boolean(!selected && pageItems.length > 0 && currentPage !== null),
    key: selected ? {
      tag: selected.tag,
      role: selected.role,
      text: selected.text,
      aria_label: selected.ariaLabel,
      title: selected.title,
      data_page: selected.dataPage,
    } : null,
  };
}
"""

_PAGE_CONTROL_CLICK_SCRIPT = """
({ tag, role, text, aria_label: ariaLabel, title, data_page: dataPage }) => {
  // xueqiu_page_control_click_v1
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const visible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && rect.width > 0
      && rect.height > 0;
  };
  const isDisabled = (element) => Boolean(
    element.disabled
      || element.getAttribute('aria-disabled') === 'true'
      || /\\b(disabled|disable)\\b/i.test(String(element.className || ''))
  );
  const elements = Array.from(
    document.querySelectorAll('a,button,[role="button"],[role="link"]')
  ).filter(visible);
  const element = elements.find((candidate) => {
    const candidateTag = candidate.tagName.toLowerCase();
    const candidateRole = normalize(candidate.getAttribute('role'))
      || (candidateTag === 'a' ? 'link' : candidateTag === 'button' ? 'button' : 'control');
    const candidateText = normalize(candidate.innerText || candidate.textContent);
    const candidateAriaLabel = normalize(candidate.getAttribute('aria-label'));
    const candidateTitle = normalize(candidate.getAttribute('title'));
    const candidateDataPage = normalize(
      candidate.getAttribute('data-page')
        || candidate.getAttribute('data-pagenum')
        || candidate.getAttribute('data-page-number')
    );
    return candidateTag === tag
      && candidateRole === role
      && candidateText === text
      && candidateAriaLabel === ariaLabel
      && candidateTitle === title
      && candidateDataPage === dataPage;
  });
  if (!element || isDisabled(element)) {
    return { clicked: false };
  }
  element.scrollIntoView({ block: 'center', inline: 'nearest' });
  element.click();
  return { clicked: true };
}
"""


@dataclass(frozen=True)
class _PageControlState:
    has_pagination_control: bool = False
    current_page: int | None = None
    next_page: int | None = None
    next_available: bool = False
    control_role: str | None = None
    control_selector: str | None = None
    disabled: bool | None = None
    end_state: bool = False
    key: Mapping[str, str] | None = None


def _positive_page_number(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def _page_control_state_from_payload(value: object) -> _PageControlState:
    if not isinstance(value, Mapping):
        return _PageControlState()
    raw_key = value.get("key")
    key = (
        {
            str(name): str(raw_value or "")
            for name, raw_value in raw_key.items()
            if isinstance(name, str)
        }
        if isinstance(raw_key, Mapping)
        else None
    )
    return _PageControlState(
        has_pagination_control=bool(value.get("has_pagination_control", False)),
        current_page=_positive_page_number(value.get("current_page")),
        next_page=_positive_page_number(value.get("next_page")),
        next_available=bool(value.get("next_available", False)),
        control_role=str(value["control_role"]) if value.get("control_role") else None,
        control_selector=(
            str(value["control_selector"]) if value.get("control_selector") else None
        ),
        disabled=(bool(value["disabled"]) if value.get("disabled") is not None else None),
        end_state=bool(value.get("end_state", False)),
        key=key,
    )


async def _inspect_page_control(page: object) -> _PageControlState:
    try:
        payload = await page.evaluate(_PAGE_CONTROL_DISCOVERY_SCRIPT)  # type: ignore[attr-defined]
    except Exception:
        return _PageControlState()
    return _page_control_state_from_payload(payload)


async def _click_page_control(page: object, state: _PageControlState) -> bool:
    if state.key is None:
        return False
    try:
        result = await page.evaluate(  # type: ignore[attr-defined]
            _PAGE_CONTROL_CLICK_SCRIPT,
            dict(state.key),
        )
    except Exception:
        return False
    return isinstance(result, Mapping) and bool(result.get("clicked", False))


def _trace_page_number(trace: HistoryPaginationTrace) -> int | None:
    return _positive_page_number(trace.pagination_query.get("page"))


def _build_pagination_trace(
    *,
    sequence: int,
    request_url: str,
    http_status: int,
    content_type: str,
    payload: Mapping[str, object] | None,
    expected_user_id: str,
    now: datetime,
    previous_response_ids: set[str],
    seen_status_ids: set[str],
    duplicate_response: bool,
) -> tuple[HistoryPaginationTrace, tuple[str, ...], tuple[tuple[str, datetime], ...]]:
    ids: tuple[str, ...] = ()
    status_times: tuple[tuple[str, datetime], ...] = ()
    if payload is not None:
        ids, status_times = _trace_status_snapshot(
            payload,
            expected_user_id=expected_user_id,
            now=now,
        )
    unique_ids = set(ids)
    ordered_times = sorted(status_times, key=lambda item: (item[1], item[0]))
    newest = ordered_times[-1] if ordered_times else (None, None)
    oldest = ordered_times[0] if ordered_times else (None, None)
    fingerprint = hashlib.sha256(
        json.dumps(sorted(unique_ids), separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    trace = HistoryPaginationTrace(
        sequence=sequence,
        request_path=urlparse(request_url).path,
        http_status=http_status,
        content_type=content_type,
        pagination_query=_trace_query_params(request_url),
        response_item_count=len(ids),
        newest_status_id=newest[0],
        newest_published_time=newest[1],
        oldest_status_id=oldest[0],
        oldest_published_time=oldest[1],
        response_ids_fingerprint=fingerprint,
        repeated_item_count=len(unique_ids & previous_response_ids),
        new_status_id_count=len(unique_ids - seen_status_ids),
        duplicate_response=duplicate_response,
        pagination_fields=_trace_response_fields(payload or {}),
    )
    return trace, ids, status_times


def parse_history_payload(
    payload: Mapping[str, object],
    *,
    expected_user_id: str,
    now: datetime,
    endpoint_path: str = "",
) -> ParsedHistoryPage:
    """Parse target-author status items while isolating item failures."""

    parser = XueqiuFollowingFeedParser()
    status_ids, status_times = _trace_status_snapshot(
        payload,
        expected_user_id=expected_user_id,
        now=now,
    )
    posts: list[FeedPostItem] = []
    parse_failures = 0
    for item in _candidate_status_items(payload):
        raw_author_id = _raw_author_id(item)
        if raw_author_id is not None and raw_author_id != expected_user_id:
            continue
        try:
            post = parser._parse_item(item, now=now)  # noqa: SLF001
        except Exception:
            parse_failures += 1
            continue
        if post.author_id != expected_user_id:
            continue
        posts.append(post)
    post_times = [post.published_time.astimezone(UTC) for post in posts]
    chronology_reliable = len(post_times) >= 2 and all(
        earlier >= later for earlier, later in zip(post_times, post_times[1:], strict=False)
    )
    return ParsedHistoryPage(
        posts=tuple(posts),
        parse_failures=parse_failures,
        has_more=_payload_has_more(payload),
        endpoint_path=endpoint_path,
        status_ids=status_ids,
        status_times=tuple(
            (status_id, timestamp.astimezone(UTC)) for status_id, timestamp in status_times
        ),
        chronology_reliable=chronology_reliable,
    )


def _cutoff_evidence_ids(
    pages: Sequence[ParsedHistoryPage],
    request: InvestorHistoryCollectionRequest,
) -> set[str]:
    """Return independent, chronologically ordered posts proving the cutoff."""

    since = request.since.astimezone(UTC)
    until = request.until.astimezone(UTC)
    evidence_ids: set[str] = set()
    for page in pages:
        if not page.chronology_reliable:
            continue
        for post in page.posts:
            published_time = post.published_time.astimezone(UTC)
            if published_time <= since and published_time <= until:
                evidence_ids.add(post.source_event_id)
    return evidence_ids


def summarize_history_pages(
    pages: Sequence[ParsedHistoryPage],
    request: InvestorHistoryCollectionRequest,
    *,
    stop_reason: InvestorHistoryStopReason,
    observed_endpoint_paths: Sequence[str] = (),
) -> InvestorHistoryCapture:
    """Deduplicate and window normalized posts into probe metrics."""

    all_posts: list[FeedPostItem] = []
    seen_ids: set[str] = set()
    duplicate_posts = 0
    for page in pages:
        for post in page.posts:
            if post.source_event_id in seen_ids:
                duplicate_posts += 1
                continue
            seen_ids.add(post.source_event_id)
            all_posts.append(post)

    since = request.since.astimezone(UTC)
    until = request.until.astimezone(UTC)
    selected = sorted(
        (post for post in all_posts if since <= post.published_time.astimezone(UTC) <= until),
        key=lambda post: (post.published_time.astimezone(UTC), post.source_event_id),
        reverse=True,
    )
    times = [post.published_time.astimezone(UTC) for post in selected]
    newest = max(times) if times else None
    oldest = min(times) if times else None
    span = (newest - oldest).total_seconds() / 86400 if newest and oldest else None
    cutoff_evidence_ids = _cutoff_evidence_ids(pages, request)
    endpoint_paths = tuple(
        sorted(
            set(observed_endpoint_paths)
            or {page.endpoint_path for page in pages if page.endpoint_path}
        )
    )
    return InvestorHistoryCapture(
        posts=tuple(selected),
        pages=len(pages),
        duplicate_posts_in_capture=duplicate_posts,
        parse_failures=sum(page.parse_failures for page in pages),
        stop_reason=stop_reason,
        newest_published_time=newest,
        oldest_published_time=oldest,
        actual_history_span_days=span,
        cutoff_proven=len(cutoff_evidence_ids) >= 2,
        cutoff_evidence_count=len(cutoff_evidence_ids),
        observed_endpoint_paths=endpoint_paths,
    )


def _safe_page_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


async def _safe_page_descriptor(page: object) -> tuple[str, str]:
    url = _safe_page_url(str(getattr(page, "url", "")))
    try:
        title = str(await page.title())  # type: ignore[attr-defined]
    except Exception:
        title = "<title unavailable>"
    return title[:255], url


async def _select_existing_cdp_page(
    browser: object,
    *,
    expected_user_id: str,
) -> tuple[object, int, int, str, str]:
    contexts = list(getattr(browser, "contexts", ()))
    pages = [page for context in contexts for page in list(getattr(context, "pages", ()))]
    print("Browser connected")
    print(f"contexts={len(contexts)}")
    print(f"pages={len(pages)}")

    candidates = [
        page
        for page in pages
        if _is_matching_investor_page(str(getattr(page, "url", "")), expected_user_id)
    ]
    if not candidates:
        visible_pages = [
            await _safe_page_descriptor(page)
            for page in pages
            if "xueqiu.com" in str(getattr(page, "url", ""))
        ]
        if visible_pages:
            print(f"safe_xueqiu_pages={visible_pages}")
        raise NetworkUnavailable(
            "no existing Xueqiu Investor page matches the requested platform user id"
        )

    descriptors = [await _safe_page_descriptor(page) for page in candidates]
    if len(candidates) > 1:
        print("Multiple matching Xueqiu Investor pages:")
        for index, (title, url) in enumerate(descriptors, start=1):
            print(f"page={index} title={title!r} url={url}")
        selection = await asyncio.to_thread(
            input,
            "请选择要接管的 page 编号并按 Enter：",
        )
        try:
            selected_index = int(selection.strip()) - 1
        except ValueError as exc:
            raise NetworkUnavailable("invalid existing-page selection") from exc
        if selected_index not in range(len(candidates)):
            raise NetworkUnavailable("existing-page selection is out of range")
        selected = candidates[selected_index]
        title, safe_url = descriptors[selected_index]
    else:
        selected = candidates[0]
        title, safe_url = descriptors[0]

    print(f"selected_page_url={safe_url}")
    print(f"selected_page_title={title}")
    return selected, len(contexts), len(pages), safe_url, title


def _is_matching_investor_page(url: str, expected_user_id: str) -> bool:
    try:
        validate_current_investor_url(url, expected_user_id)
    except NavigationFailed:
        return False
    return True


class XueqiuInvestorHistoryBrowser:
    """Bounded browser-native profile history capture with no direct API calls."""

    def __init__(self, config: XueqiuBrowserConfig) -> None:
        self._config = config
        self._last_stop_reason: InvestorHistoryStopReason | None = None

    @property
    def last_stop_reason(self) -> InvestorHistoryStopReason | None:
        return self._last_stop_reason

    async def capture(
        self,
        request: InvestorHistoryCollectionRequest,
    ) -> InvestorHistoryCapture:
        homepage_url = validate_xueqiu_homepage_url(request.homepage_url)
        storage_state_path = Path(self._config.storage_state_path)
        if request.attach_cdp_endpoint is None and not storage_state_path.is_file():
            self._last_stop_reason = InvestorHistoryStopReason.AUTH_REQUIRED
            raise AuthenticationRequired(
                "Xueqiu authentication state is missing; run the manual authentication command"
            )

        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            self._last_stop_reason = InvestorHistoryStopReason.BROWSER_DEPENDENCY_MISSING
            raise BrowserDependencyMissing(
                "Playwright is not installed; install project dependencies before collection"
            ) from exc

        pages: list[ParsedHistoryPage] = []
        seen_page_signatures: set[str] = set()
        pagination_traces: list[HistoryPaginationTrace] = []
        scroll_traces: list[HistoryScrollTrace] = []
        page_control_traces: list[HistoryPageControlTrace] = []
        previous_response_ids: set[str] = set()
        seen_status_ids: set[str] = set()
        progress_ids: set[str] = set()
        progress_oldest: datetime | None = None
        response_tasks: list[asyncio.Task[None]] = []
        timeline_endpoint_path: str | None = None
        access_blocked = False
        body_text = ""
        title = ""
        browser = None
        context = None
        connected_context_count = 0
        connected_page_count = 0
        selected_page_url = None
        selected_page_title = None
        first_page_bootstrap_attempted = False
        first_page_bootstrap_succeeded = False

        async def settle_response_tasks() -> None:
            if response_tasks:
                await asyncio.gather(*response_tasks, return_exceptions=True)
                response_tasks.clear()

        async def read_page_state(page: object) -> tuple[str, str]:
            try:
                current_body = await page.locator("body").inner_text()  # type: ignore[attr-defined]
                current_title = await page.title()  # type: ignore[attr-defined]
            except PlaywrightError as exc:
                self._last_stop_reason = InvestorHistoryStopReason.NAVIGATION_FAILED
                raise NavigationFailed("could not inspect Xueqiu Investor profile state") from exc
            return current_body, current_title

        async def ensure_page_state(
            page: object,
            current_body: str,
            current_title: str,
        ) -> tuple[str, str]:
            nonlocal access_blocked

            if current_title.strip() == "405" or current_body.strip().startswith("405"):
                self._last_stop_reason = InvestorHistoryStopReason.NETWORK_UNAVAILABLE
                raise NavigationFailed("current Xueqiu Investor page displays HTTP 405")
            has_challenge = (
                access_blocked
                or any(marker in current_body for marker in BLOCKED_MARKERS)
                or "验证" in current_title
                or any(marker in current_body for marker in AUTHENTICATION_MARKERS)
            )
            if not has_challenge:
                return current_body, current_title
            if not request.human_assisted or request.attach_cdp_endpoint is not None:
                if any(marker in current_body for marker in AUTHENTICATION_MARKERS):
                    self._last_stop_reason = (
                        InvestorHistoryStopReason.MANUAL_VERIFICATION_REQUIRED
                        if request.attach_cdp_endpoint is not None
                        else InvestorHistoryStopReason.AUTH_REQUIRED
                    )
                    if request.attach_cdp_endpoint is not None:
                        raise ManualVerificationRequired(
                            "MANUAL_VERIFICATION_REQUIRED: CDP page requires login"
                        )
                    raise AuthenticationRequired("Xueqiu authentication is missing or expired")
                self._last_stop_reason = InvestorHistoryStopReason.BLOCKED
                if request.attach_cdp_endpoint is not None:
                    self._last_stop_reason = InvestorHistoryStopReason.MANUAL_VERIFICATION_REQUIRED
                    raise ManualVerificationRequired(
                        "MANUAL_VERIFICATION_REQUIRED: CDP page requires verification"
                    )
                raise RateLimitedOrBlocked("Xueqiu requested verification; history probe stopped")

            access_blocked = False
            self._last_stop_reason = InvestorHistoryStopReason.MANUAL_VERIFICATION_REQUIRED
            print("MANUAL_VERIFICATION_REQUIRED")
            await asyncio.to_thread(
                input,
                "请在当前浏览器中手动完成登录/验证，完成后回到终端按 Enter 继续：",
            )
            refreshed_body, refreshed_title = await read_page_state(page)
            still_challenged = (
                any(marker in refreshed_body for marker in BLOCKED_MARKERS)
                or "验证" in refreshed_title
                or any(marker in refreshed_body for marker in AUTHENTICATION_MARKERS)
            )
            if still_challenged:
                raise ManualVerificationRequired(
                    "MANUAL_VERIFICATION_REQUIRED: the verification state is still visible"
                )
            return refreshed_body, refreshed_title

        async def ensure_cdp_bootstrap_safety(page: object) -> tuple[str, str]:
            body, current_title = await read_page_state(page)
            body, current_title = await ensure_page_state(page, body, current_title)
            validate_current_investor_url(
                str(getattr(page, "url", "")),
                request.platform_user_id,
            )
            return body, current_title

        async with async_playwright() as playwright:
            try:
                if request.attach_cdp_endpoint is not None:
                    try:
                        browser = await playwright.chromium.connect_over_cdp(
                            request.attach_cdp_endpoint
                        )
                    except Exception as exc:
                        self._last_stop_reason = InvestorHistoryStopReason.CDP_NOT_AVAILABLE
                        raise CdpNotAvailable(
                            f"could not connect to Edge CDP endpoint {request.attach_cdp_endpoint}"
                        ) from exc
                    (
                        page,
                        connected_context_count,
                        connected_page_count,
                        selected_page_url,
                        selected_page_title,
                    ) = await _select_existing_cdp_page(
                        browser,
                        expected_user_id=request.platform_user_id,
                    )
                else:
                    browser = await playwright.chromium.launch(
                        **chromium_launch_options(self._config)
                    )
                    context = await browser.new_context(storage_state=str(storage_state_path))
                    page = await context.new_page()

                async def capture_response(response: object) -> None:
                    nonlocal access_blocked, previous_response_ids, seen_status_ids
                    nonlocal timeline_endpoint_path
                    status = int(getattr(response, "status", 0) or 0)
                    request_object = getattr(response, "request", None)
                    request_url = str(
                        getattr(request_object, "url", None) or getattr(response, "url", "")
                    )
                    path = _history_response_path(request_url)
                    if path is None:
                        return
                    method = str(getattr(request_object, "method", "GET")).upper()
                    if method != "GET":
                        return
                    if status in {403, 429}:
                        access_blocked = True
                    try:
                        headers = await response.all_headers()  # type: ignore[attr-defined]
                        content_type = headers.get("content-type", "")
                        payload = (
                            await response.json()  # type: ignore[attr-defined]
                            if "json" in content_type.lower()
                            else None
                        )
                    except PlaywrightError:
                        return
                    payload_mapping = payload if isinstance(payload, Mapping) else None
                    signature = (
                        _page_signature(request_url, payload_mapping)
                        if payload_mapping is not None
                        else f"{request_url}:{status}:{content_type}"
                    )
                    duplicate_response = signature in seen_page_signatures
                    trace, response_ids, response_times = _build_pagination_trace(
                        sequence=len(pagination_traces) + 1,
                        request_url=request_url,
                        http_status=status,
                        content_type=content_type,
                        payload=payload_mapping,
                        expected_user_id=request.platform_user_id,
                        now=request.until,
                        previous_response_ids=previous_response_ids,
                        seen_status_ids=seen_status_ids,
                        duplicate_response=duplicate_response,
                    )
                    pagination_traces.append(trace)
                    primary_timeline_response = _is_primary_timeline_path(path)
                    if primary_timeline_response:
                        previous_response_ids = set(response_ids)
                        seen_status_ids.update(response_ids)
                    else:
                        return
                    if (
                        payload_mapping is None
                        or not _response_has_history_container(payload_mapping)
                        or duplicate_response
                    ):
                        return
                    parsed_page = parse_history_payload(
                        payload_mapping,
                        expected_user_id=request.platform_user_id,
                        now=request.until,
                        endpoint_path=path,
                    )
                    # Auxiliary profile requests (for example video/original
                    # timelines) can contain list-shaped JSON containers but
                    # do not represent a history page for the target author.
                    # Keep max_pages and the reported page count scoped to
                    # responses that actually contain target status IDs.
                    if not parsed_page.status_ids and not parsed_page.posts:
                        return
                    if timeline_endpoint_path is None:
                        timeline_endpoint_path = path
                    seen_page_signatures.add(signature)
                    pages.append(parsed_page)

                def schedule_capture(response: object) -> None:
                    response_tasks.append(asyncio.create_task(capture_response(response)))

                page.on("response", schedule_capture)  # type: ignore[attr-defined]
                try:
                    loop = asyncio.get_running_loop()
                    deadline = loop.time() + request.max_duration_seconds

                    async def wait_bounded(milliseconds: int) -> bool:
                        remaining = deadline - loop.time()
                        if remaining <= 0:
                            return False
                        await page.wait_for_timeout(  # type: ignore[attr-defined]
                            min(milliseconds, max(0, int(remaining * 1000)))
                        )
                        return loop.time() < deadline

                    def current_observed_oldest() -> datetime | None:
                        trace_times = [
                            trace.oldest_published_time
                            for trace in pagination_traces
                            if trace.oldest_published_time is not None
                            and (
                                timeline_endpoint_path is None
                                or trace.request_path == timeline_endpoint_path
                            )
                        ]
                        return min(trace_times) if trace_times else None

                    async def record_scroll_trace(
                        *,
                        mode: str,
                        before_state: Mapping[str, float | bool | None],
                        trace_start: int,
                    ) -> bool:
                        nonlocal progress_oldest
                        after_state = await _read_scroll_state(page)
                        new_ids = seen_status_ids - progress_ids
                        current_oldest = current_observed_oldest()
                        oldest_moved = current_oldest is not None and (
                            progress_oldest is None or current_oldest < progress_oldest
                        )
                        progress = bool(new_ids) or oldest_moved
                        scroll_traces.append(
                            HistoryScrollTrace(
                                sequence=len(scroll_traces) + 1,
                                mode=mode,
                                scroll_y_before=before_state.get("scroll_y"),
                                scroll_y_after=after_state.get("scroll_y"),
                                scroll_height_before=before_state.get("scroll_height"),
                                scroll_height_after=after_state.get("scroll_height"),
                                loading_before=before_state.get("loading"),
                                loading_after=after_state.get("loading"),
                                new_timeline_request_count=len(pagination_traces) - trace_start,
                                new_status_id_count=len(new_ids),
                                oldest_published_time_after=current_oldest,
                                progress=progress,
                            )
                        )
                        progress_ids.update(seen_status_ids)
                        if current_oldest is not None and (
                            progress_oldest is None or current_oldest < progress_oldest
                        ):
                            progress_oldest = current_oldest
                        return progress

                    def target_reached() -> bool:
                        # One anomalously old or pinned item must not prove the
                        # historical boundary. Require two distinct posts from
                        # a page whose target-author chronology is ordered.
                        return len(_cutoff_evidence_ids(pages, request)) >= 2

                    def latest_timeline_page() -> int | None:
                        if timeline_endpoint_path is None:
                            return None
                        for trace in reversed(pagination_traces):
                            if trace.request_path == timeline_endpoint_path:
                                page_number = _trace_page_number(trace)
                                if page_number is not None:
                                    return page_number
                        return None

                    async def wait_for_timeline_response(
                        trace_start: int,
                    ) -> tuple[HistoryPaginationTrace, ...]:
                        wait_window_ms = max(self._config.response_wait_ms, 100)
                        response_deadline = min(
                            deadline,
                            loop.time() + (wait_window_ms / 1000),
                        )
                        while loop.time() < response_deadline:
                            await settle_response_tasks()
                            new_traces = tuple(pagination_traces[trace_start:])
                            timeline_traces = tuple(
                                trace
                                for trace in new_traces
                                if timeline_endpoint_path is not None
                                and trace.request_path == timeline_endpoint_path
                            )
                            if timeline_traces:
                                return timeline_traces
                            remaining = response_deadline - loop.time()
                            if remaining <= 0:
                                break
                            await page.wait_for_timeout(  # type: ignore[attr-defined]
                                min(50, max(1, int(remaining * 1000)))
                            )
                        await settle_response_tasks()
                        return tuple(
                            trace
                            for trace in pagination_traces[trace_start:]
                            if timeline_endpoint_path is not None
                            and trace.request_path == timeline_endpoint_path
                        )

                    async def paginate_by_page_controls() -> InvestorHistoryStopReason:
                        """Advance only through visible DOM pagination controls."""

                        nonlocal idle_cycles, progress_oldest
                        while True:
                            if not pages:
                                page_control_traces.append(
                                    HistoryPageControlTrace(
                                        sequence=len(page_control_traces) + 1,
                                        current_page=None,
                                        next_page=None,
                                        has_pagination_control=False,
                                        next_available=False,
                                        control_role=None,
                                        control_selector=None,
                                        disabled=None,
                                        end_state=False,
                                        clicked=False,
                                        page_advanced=False,
                                        progress=False,
                                    )
                                )
                                return InvestorHistoryStopReason.FIRST_PAGE_UNAVAILABLE
                            if target_reached():
                                return InvestorHistoryStopReason.TARGET_REACHED
                            if len(pages) >= request.max_pages:
                                return InvestorHistoryStopReason.MAX_PAGES
                            if deadline - loop.time() <= 0:
                                return InvestorHistoryStopReason.TIMEOUT

                            state = await _inspect_page_control(page)
                            current_page = state.current_page or latest_timeline_page()
                            next_page = state.next_page or (
                                current_page + 1 if current_page is not None else None
                            )
                            if not state.has_pagination_control:
                                page_control_traces.append(
                                    HistoryPageControlTrace(
                                        sequence=len(page_control_traces) + 1,
                                        current_page=current_page,
                                        next_page=next_page,
                                        has_pagination_control=False,
                                        next_available=False,
                                        control_role=state.control_role,
                                        control_selector=state.control_selector,
                                        disabled=state.disabled,
                                        end_state=False,
                                        clicked=False,
                                        page_advanced=False,
                                        progress=False,
                                    )
                                )
                                return InvestorHistoryStopReason.PAGE_CONTROL_NOT_FOUND
                            if not state.next_available:
                                page_control_traces.append(
                                    HistoryPageControlTrace(
                                        sequence=len(page_control_traces) + 1,
                                        current_page=current_page,
                                        next_page=next_page,
                                        has_pagination_control=True,
                                        next_available=False,
                                        control_role=state.control_role,
                                        control_selector=state.control_selector,
                                        disabled=state.disabled,
                                        end_state=state.end_state,
                                        clicked=False,
                                        page_advanced=False,
                                        progress=False,
                                    )
                                )
                                return InvestorHistoryStopReason.END_OF_PAGINATION

                            trace_start = len(pagination_traces)
                            clicked = await _click_page_control(page, state)
                            if not clicked:
                                page_control_traces.append(
                                    HistoryPageControlTrace(
                                        sequence=len(page_control_traces) + 1,
                                        current_page=current_page,
                                        next_page=next_page,
                                        has_pagination_control=True,
                                        next_available=True,
                                        control_role=state.control_role,
                                        control_selector=state.control_selector,
                                        disabled=state.disabled,
                                        end_state=False,
                                        clicked=False,
                                        page_advanced=False,
                                        progress=False,
                                    )
                                )
                                return InvestorHistoryStopReason.PAGE_CONTROL_NOT_FOUND

                            timeline_traces = await wait_for_timeline_response(trace_start)
                            response_page = next(
                                (
                                    page_number
                                    for page_number in reversed(
                                        [_trace_page_number(trace) for trace in timeline_traces]
                                    )
                                    if page_number is not None
                                ),
                                None,
                            )
                            page_advanced = bool(
                                response_page is not None
                                and (
                                    (current_page is not None and response_page > current_page)
                                    or (next_page is not None and response_page == next_page)
                                )
                            )
                            new_status_id_count = sum(
                                trace.new_status_id_count for trace in timeline_traces
                            )
                            progress = page_advanced and new_status_id_count > 0
                            current_oldest = current_observed_oldest()
                            if current_oldest is not None and (
                                progress_oldest is None or current_oldest < progress_oldest
                            ):
                                progress_oldest = current_oldest
                            page_control_traces.append(
                                HistoryPageControlTrace(
                                    sequence=len(page_control_traces) + 1,
                                    current_page=current_page,
                                    next_page=next_page,
                                    has_pagination_control=True,
                                    next_available=True,
                                    control_role=state.control_role,
                                    control_selector=state.control_selector,
                                    disabled=state.disabled,
                                    end_state=False,
                                    clicked=True,
                                    response_page=response_page,
                                    page_advanced=page_advanced,
                                    new_status_id_count=new_status_id_count,
                                    progress=progress,
                                )
                            )
                            if progress:
                                idle_cycles = 0
                                progress_ids.update(seen_status_ids)
                                if target_reached():
                                    return InvestorHistoryStopReason.TARGET_REACHED
                                continue

                            idle_cycles += 1
                            if deadline - loop.time() <= 0:
                                return InvestorHistoryStopReason.TIMEOUT
                            if idle_cycles >= idle_limit:
                                return InvestorHistoryStopReason.NO_PROGRESS

                    if request.attach_cdp_endpoint is not None:
                        bootstrap_before = await _read_scroll_state(page)
                        bootstrap_trace_start = len(pagination_traces)
                        await settle_response_tasks()
                        body_text, title = await ensure_cdp_bootstrap_safety(page)
                        if not pages:
                            first_page_bootstrap_attempted = True
                            await page.reload(  # type: ignore[attr-defined]
                                wait_until="domcontentloaded",
                                timeout=self._config.navigation_timeout_ms,
                            )
                            await wait_bounded(self._config.response_wait_ms)
                            await settle_response_tasks()
                            body_text, title = await ensure_cdp_bootstrap_safety(page)
                            first_page_bootstrap_succeeded = bool(pages)
                        await record_scroll_trace(
                            mode=(
                                "AUTO_RELOAD_BOOTSTRAP"
                                if first_page_bootstrap_attempted
                                else "CDP_SETUP"
                            ),
                            before_state=bootstrap_before,
                            trace_start=bootstrap_trace_start,
                        )
                    elif request.human_assisted:
                        await asyncio.to_thread(
                            input,
                            "请在当前浏览器中手动进入目标大V主页；若出现登录确认或验证，请只手动完成。"
                            "页面正常加载后回到终端按 Enter：",
                        )
                        body_text, title = await read_page_state(page)
                        body_text, title = await ensure_page_state(page, body_text, title)
                        validate_current_investor_url(
                            str(getattr(page, "url", "")),
                            request.platform_user_id,
                        )
                    else:
                        navigation_response = await page.goto(  # type: ignore[attr-defined]
                            homepage_url,
                            wait_until="domcontentloaded",
                            timeout=self._config.navigation_timeout_ms,
                        )
                        navigation_status = getattr(navigation_response, "status", None)
                        if isinstance(navigation_status, int) and navigation_status >= 400:
                            self._last_stop_reason = InvestorHistoryStopReason.NAVIGATION_FAILED
                            raise NavigationFailed(
                                "Xueqiu Investor profile returned "
                                f"HTTP {navigation_status}; history probe stopped"
                            )

                    await wait_bounded(self._config.response_wait_ms)
                    await settle_response_tasks()
                    body_text, title = await read_page_state(page)
                    body_text, title = await ensure_page_state(page, body_text, title)
                    if not progress_ids:
                        progress_ids.update(seen_status_ids)
                        progress_oldest = current_observed_oldest()

                    idle_limit = (
                        request.max_idle_cycles
                        if request.max_idle_cycles is not None
                        else self._config.max_idle_cycles_without_progress
                    )
                    idle_cycles = 0
                    stop_reason: InvestorHistoryStopReason | None = None

                    if target_reached():
                        stop_reason = InvestorHistoryStopReason.TARGET_REACHED
                    elif pages and pages[-1].has_more is False:
                        stop_reason = InvestorHistoryStopReason.END_OF_HISTORY

                    if stop_reason is None and request.attach_cdp_endpoint is not None:
                        stop_reason = await paginate_by_page_controls()
                    else:
                        while (
                            stop_reason is None
                            and len(pages) < request.max_pages
                            and idle_cycles < idle_limit
                        ):
                            if deadline - loop.time() <= 0:
                                stop_reason = InvestorHistoryStopReason.MAX_DURATION
                                break
                            before_state = await _read_scroll_state(page)
                            trace_start = len(pagination_traces)
                            await page.mouse.wheel(0, 1800)  # type: ignore[attr-defined]
                            bounded = await wait_bounded(self._config.response_wait_ms)
                            await settle_response_tasks()
                            progress = await record_scroll_trace(
                                mode="AUTOMATIC",
                                before_state=before_state,
                                trace_start=trace_start,
                            )
                            body_text, title = await read_page_state(page)
                            body_text, title = await ensure_page_state(page, body_text, title)
                            if not bounded:
                                stop_reason = InvestorHistoryStopReason.MAX_DURATION
                                break
                            if not progress:
                                idle_cycles += 1
                                continue
                            idle_cycles = 0
                            latest_page = pages[-1]
                            if any(
                                post.published_time.astimezone(UTC) <= request.since.astimezone(UTC)
                                for post in latest_page.posts
                            ):
                                stop_reason = InvestorHistoryStopReason.TARGET_REACHED
                            elif latest_page.has_more is False:
                                stop_reason = InvestorHistoryStopReason.END_OF_HISTORY

                    if stop_reason is None:
                        if len(pages) >= request.max_pages:
                            stop_reason = InvestorHistoryStopReason.MAX_PAGES
                        elif deadline - loop.time() <= 0:
                            stop_reason = InvestorHistoryStopReason.MAX_DURATION
                        else:
                            stop_reason = InvestorHistoryStopReason.NO_PROGRESS
                except PlaywrightTimeoutError as exc:
                    self._last_stop_reason = InvestorHistoryStopReason.NAVIGATION_FAILED
                    raise NavigationFailed("Xueqiu Investor profile navigation timed out") from exc
                except PlaywrightError as exc:
                    self._last_stop_reason = InvestorHistoryStopReason.NAVIGATION_FAILED
                    raise NavigationFailed("Xueqiu Investor profile navigation failed") from exc
            finally:
                await settle_response_tasks()
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()

        if (
            any(marker in body_text for marker in BLOCKED_MARKERS)
            or "验证" in title
            or access_blocked
        ):
            self._last_stop_reason = InvestorHistoryStopReason.BLOCKED
            raise RateLimitedOrBlocked("Xueqiu requested verification; history probe stopped")
        if any(marker in body_text for marker in AUTHENTICATION_MARKERS):
            self._last_stop_reason = InvestorHistoryStopReason.AUTH_REQUIRED
            raise AuthenticationRequired("Xueqiu authentication is missing or expired")
        if not pages and any(marker in body_text for marker in NO_CONTENT_MARKERS):
            self._last_stop_reason = InvestorHistoryStopReason.NO_CONTENT
            raise NoContent("Xueqiu Investor profile has no public posts")

        self._last_stop_reason = stop_reason
        capture = summarize_history_pages(
            pages,
            request,
            stop_reason=stop_reason,
            observed_endpoint_paths=tuple(
                sorted({trace.request_path for trace in pagination_traces})
            ),
        )
        return capture.model_copy(
            update={
                "connected_context_count": connected_context_count,
                "connected_page_count": connected_page_count,
                "selected_page_url": selected_page_url,
                "selected_page_title": selected_page_title,
                "pagination_trace": tuple(pagination_traces),
                "scroll_trace": tuple(scroll_traces),
                "page_control_trace": tuple(page_control_traces),
                "first_page_bootstrap_attempted": first_page_bootstrap_attempted,
                "first_page_bootstrap_succeeded": first_page_bootstrap_succeeded,
            }
        )


class XueqiuInvestorHistoryAdapter:
    """SourceAdapter that converts one bounded history capture to RawEventDTOs."""

    source = HISTORY_SOURCE
    adapter_name = "xueqiu_profile_history_cdp"
    collection_mode = CollectionMode.ENTITY_HISTORY
    transport = CollectionTransport.BROWSER_CDP

    def __init__(self, browser: XueqiuInvestorHistoryBrowser) -> None:
        self._browser = browser
        self.last_capture: InvestorHistoryCapture | None = None

    async def collect(
        self,
        request: InvestorHistoryCollectionRequest,
    ) -> AsyncIterator[RawEventDTO]:
        capture = await self._browser.capture(request)
        self.last_capture = capture
        for post in capture.posts:
            raw_data = dict(post.raw_data)
            raw_data["source_event_id"] = post.source_event_id
            raw_data["author_id"] = post.author_id
            raw_data["event_type"] = post.event_type.value
            raw_data["post_kind"] = post.post_kind.value
            yield RawEventDTO.build(
                investor_id=request.investor_id,
                event_type=post.event_type,
                source=self.source,
                url=post.url
                or HISTORY_PROFILE_URL_TEMPLATE.format(platform_user_id=post.author_id),
                published_time=post.published_time,
                content=post.content,
                raw_data=raw_data,
            )


def _failure_reason(exc: Exception) -> InvestorHistoryStopReason:
    if isinstance(exc, AuthenticationRequired):
        return InvestorHistoryStopReason.AUTH_REQUIRED
    if isinstance(exc, ManualVerificationRequired):
        return InvestorHistoryStopReason.MANUAL_VERIFICATION_REQUIRED
    if isinstance(exc, CdpNotAvailable):
        return InvestorHistoryStopReason.CDP_NOT_AVAILABLE
    if isinstance(exc, NetworkUnavailable):
        return InvestorHistoryStopReason.NETWORK_UNAVAILABLE
    if isinstance(exc, RateLimitedOrBlocked):
        return InvestorHistoryStopReason.BLOCKED
    if isinstance(exc, NavigationFailed):
        if "HTTP 405" in str(exc):
            return InvestorHistoryStopReason.NETWORK_UNAVAILABLE
        return InvestorHistoryStopReason.NAVIGATION_FAILED
    if isinstance(exc, NoContent):
        return InvestorHistoryStopReason.NO_CONTENT
    if isinstance(exc, BrowserDependencyMissing):
        return InvestorHistoryStopReason.BROWSER_DEPENDENCY_MISSING
    return InvestorHistoryStopReason.PARSE_FAILED


async def run_history_probe(
    request: InvestorHistoryCollectionRequest,
    config: XueqiuBrowserConfig,
    *,
    dry_run: bool = False,
) -> InvestorHistoryProbeResult:
    """Run one bounded capture and optionally persist through DataPipeline."""

    adapter = XueqiuInvestorHistoryAdapter(XueqiuInvestorHistoryBrowser(config))
    run_id: UUID | None = None
    inserted = 0
    duplicates = 0
    if not dry_run:
        from database.repositories import CollectionRunRepository
        from database.session import SessionFactory

        with SessionFactory() as session:
            run = CollectionRunRepository(session).create_run(
                CollectionRunCreate(
                    source=adapter.source,
                    adapter_name=adapter.adapter_name,
                    collection_mode=adapter.collection_mode,
                    transport=adapter.transport,
                    started_at=utc_now(),
                    coverage_status=CollectionCoverageStatus.UNKNOWN,
                    requested_window_start=request.since,
                    requested_window_end=request.until,
                    scope_type="INVESTOR_PROFILE",
                    scope_key=f"{request.investor_id}:{request.platform_user_id}",
                    parameters_json={
                        "lookback_days": request.lookback_days,
                        "max_pages": request.max_pages,
                        "max_idle_cycles": request.max_idle_cycles,
                        "max_duration_seconds": request.max_duration_seconds,
                        "human_assisted": request.human_assisted,
                        "cdp_attached": request.attach_cdp_endpoint is not None,
                    },
                )
            )
            session.commit()
            run_id = run.id

    try:
        if dry_run:
            async for _dto in adapter.collect(request):
                pass
        else:
            from database.repositories import (
                CollectionObservationRepository,
                CollectionRunRepository,
                RawEventRepository,
            )
            from database.session import SessionFactory
            from pipeline import DataPipeline

            with SessionFactory() as session:
                pipeline_result = await DataPipeline(
                    RawEventRepository(session),
                    session,
                    collection_observation_repository=CollectionObservationRepository(session),
                    collection_run_id=run_id,
                    source_page=request.homepage_url,
                    source_context_json={
                        "platform_user_id": request.platform_user_id,
                        "cdp_attached": request.attach_cdp_endpoint is not None,
                    },
                ).run(adapter, request)
                inserted = pipeline_result.inserted
                duplicates = pipeline_result.duplicates
        capture = adapter.last_capture
        if capture is None:
            raise RuntimeError("history adapter completed without a capture result")
        if run_id is not None:
            from database.repositories import CollectionRunRepository
            from database.session import SessionFactory

            with SessionFactory() as session:
                CollectionRunRepository(session).finish_run(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason=capture.stop_reason.value,
                    summary_json={
                        "pages": capture.pages,
                        "valid_posts": len(capture.posts),
                        "inserted_raw_events": inserted,
                        "reused_raw_events": duplicates,
                        "parse_failures": capture.parse_failures,
                    },
                )
                session.commit()
        return InvestorHistoryProbeResult(
            status=(
                InvestorHistoryProbeStatus.COMPLETED
                if capture.stop_reason
                in {
                    InvestorHistoryStopReason.TARGET_REACHED,
                    InvestorHistoryStopReason.END_OF_HISTORY,
                    InvestorHistoryStopReason.END_OF_PAGINATION,
                }
                else InvestorHistoryProbeStatus.STOPPED
            ),
            investor_id=request.investor_id,
            platform_user_id=request.platform_user_id,
            lookback_days=request.lookback_days,
            max_pages=request.max_pages,
            max_duration_seconds=request.max_duration_seconds,
            human_assisted=request.human_assisted,
            completeness=InvestorHistoryCompleteness.COMPLETENESS_UNKNOWN,
            cdp_endpoint=request.attach_cdp_endpoint,
            connected_context_count=capture.connected_context_count,
            connected_page_count=capture.connected_page_count,
            selected_page_url=capture.selected_page_url,
            selected_page_title=capture.selected_page_title,
            pagination_trace=capture.pagination_trace,
            scroll_trace=capture.scroll_trace,
            page_control_trace=capture.page_control_trace,
            pages=capture.pages,
            valid_posts=len(capture.posts),
            inserted_raw_events=inserted,
            duplicate_raw_events=duplicates,
            duplicate_posts_in_capture=capture.duplicate_posts_in_capture,
            parse_failures=capture.parse_failures,
            newest_published_time=capture.newest_published_time,
            oldest_published_time=capture.oldest_published_time,
            actual_history_span_days=capture.actual_history_span_days,
            cutoff_proven=capture.cutoff_proven,
            cutoff_evidence_count=capture.cutoff_evidence_count,
            first_page_bootstrap_attempted=capture.first_page_bootstrap_attempted,
            first_page_bootstrap_succeeded=capture.first_page_bootstrap_succeeded,
            stop_reason=capture.stop_reason,
            observed_endpoint_paths=capture.observed_endpoint_paths,
        )
    except XueqiuCollectorError as exc:
        if run_id is not None:
            from database.repositories import CollectionRunRepository
            from database.session import SessionFactory

            with SessionFactory() as session:
                repository = CollectionRunRepository(session)
                close = (
                    repository.abort_run
                    if isinstance(exc, (ManualVerificationRequired, RateLimitedOrBlocked))
                    else repository.fail_run
                )
                close(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason=_failure_reason(exc).value,
                    summary_json={"error": str(exc)[:1000]},
                )
                session.commit()
        return InvestorHistoryProbeResult(
            status=InvestorHistoryProbeStatus.STOPPED,
            investor_id=request.investor_id,
            platform_user_id=request.platform_user_id,
            lookback_days=request.lookback_days,
            max_pages=request.max_pages,
            max_duration_seconds=request.max_duration_seconds,
            human_assisted=request.human_assisted,
            completeness=InvestorHistoryCompleteness.COMPLETENESS_UNKNOWN,
            cdp_endpoint=request.attach_cdp_endpoint,
            pages=0,
            valid_posts=0,
            inserted_raw_events=0,
            duplicate_raw_events=0,
            duplicate_posts_in_capture=0,
            parse_failures=0,
            cutoff_proven=False,
            cutoff_evidence_count=0,
            first_page_bootstrap_attempted=False,
            first_page_bootstrap_succeeded=False,
            stop_reason=_failure_reason(exc),
            error=str(exc),
        )
    except Exception:
        if run_id is not None:
            from database.repositories import CollectionRunRepository
            from database.session import SessionFactory

            with SessionFactory() as session:
                CollectionRunRepository(session).fail_run(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason="FAILED",
                    summary_json={"error": "unexpected collection or persistence failure"},
                )
                session.commit()
        raise


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be greater than or equal to 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bounded Xueqiu Investor profile-history backfill probe"
    )
    parser.add_argument("--investor-id", required=True, type=UUID)
    parser.add_argument(
        "--xueqiu-user-id", "--platform-user-id", dest="platform_user_id", required=True
    )
    parser.add_argument("--lookback-days", required=True, type=positive_int, choices=(7, 15, 30))
    parser.add_argument(
        "--max-pages", "--max-batches", dest="max_pages", type=positive_int, default=10
    )
    parser.add_argument("--max-idle-cycles", type=positive_int, default=3)
    parser.add_argument("--max-duration", type=positive_int, default=180)
    parser.add_argument("--response-wait-ms", type=int, default=1500)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--human-assisted",
        action="store_true",
        help="launch headed authenticated browser and wait for manual profile navigation",
    )
    parser.add_argument(
        "--attach-cdp",
        dest="attach_cdp_endpoint",
        help="attach to an existing Chromium/Edge CDP endpoint; never launches a new context",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def _run_cli(args: argparse.Namespace) -> int:
    request = InvestorHistoryCollectionRequest.for_lookback(
        investor_id=args.investor_id,
        platform_user_id=args.platform_user_id,
        lookback_days=args.lookback_days,
        max_pages=args.max_pages,
        max_idle_cycles=args.max_idle_cycles,
        max_duration_seconds=args.max_duration,
        human_assisted=args.human_assisted,
        attach_cdp_endpoint=args.attach_cdp_endpoint,
    )
    if (args.human_assisted or args.attach_cdp_endpoint) and args.headless:
        raise ValueError("--human-assisted/--attach-cdp cannot be combined with --headless")
    if not args.dry_run:
        from database.models import Investor
        from database.session import SessionFactory

        with SessionFactory() as session:
            investor = session.get(Investor, args.investor_id)
            if investor is None:
                raise ValueError("investor_id does not exist in the database")
            if (
                investor.platform != HISTORY_SOURCE
                or investor.platform_user_id != args.platform_user_id.strip()
            ):
                raise ValueError("investor_id does not match the supplied Xueqiu platform user id")

    result = await run_history_probe(
        request,
        browser_config(
            headless=False if (args.human_assisted or args.attach_cdp_endpoint) else args.headless,
            response_wait_ms=max(args.response_wait_ms, 0),
        ),
        dry_run=args.dry_run,
    )
    print(result.model_dump_json())
    return 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(asyncio.run(_run_cli(build_parser().parse_args())))
    except (ValueError, XueqiuCollectorError) as exc:
        print(f"stop_reason={_failure_reason(exc).value}")
        print(f"Collection stopped: {exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()


__all__ = [
    "HISTORY_PROFILE_URL_TEMPLATE",
    "InvestorHistoryCapture",
    "InvestorHistoryCompleteness",
    "InvestorHistoryCollectionRequest",
    "InvestorHistoryProbeResult",
    "InvestorHistoryProbeStatus",
    "InvestorHistoryStopReason",
    "HistoryPageControlTrace",
    "ParsedHistoryPage",
    "XueqiuInvestorHistoryAdapter",
    "XueqiuInvestorHistoryBrowser",
    "browser_config",
    "build_parser",
    "parse_history_payload",
    "run_history_probe",
    "summarize_history_pages",
    "validate_current_investor_url",
]
