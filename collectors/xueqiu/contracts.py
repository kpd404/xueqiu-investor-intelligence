from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator

from contracts import EventType, FeedPostItem


class FeedItemParseFailure(BaseModel):
    """Safe diagnostics for one feed item that could not be normalized."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_index: int = Field(ge=0)
    source_event_id: str | None = Field(default=None, min_length=1)
    error_code: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=255)
    structural_context: dict[str, JsonValue] = Field(default_factory=dict)


class FollowingFeedBatch(BaseModel):
    """A validated response batch from the Xueqiu Following feed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[FeedPostItem, ...] = ()
    item_failures: tuple[FeedItemParseFailure, ...] = ()
    next_id: str | None = None
    next_max_id: str | None = None
    observed_at: AwareDatetime
    batch_sequence: int | None = Field(default=None, ge=1)

    @field_validator("next_id", "next_max_id", mode="before")
    @classmethod
    def normalize_cursor(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, str | int):
            raise ValueError("feed cursor must be a string or integer")
        normalized = str(value).strip()
        return normalized or None


class ParsedXueqiuPost(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_event_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    event_type: EventType = EventType.POST
    url: str = Field(min_length=1)
    published_time: AwareDatetime
    content: str = Field(min_length=1)
    raw_data: dict[str, JsonValue]


class XueqiuBrowserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    storage_state_path: str = ".local/xueqiu/storage_state.json"
    persistent_profile_path: str = ".local/xueqiu/profile"
    browser_channel: str = Field(default="msedge", min_length=1)
    browser_executable_path: str | None = None
    headless: bool = False
    navigation_timeout_ms: int = Field(default=30_000, ge=1_000)
    response_wait_ms: int = Field(default=5_000, ge=0)
    max_idle_cycles_without_progress: int = Field(default=8, ge=1)
    max_scroll_attempts_without_progress: int | None = Field(
        default=None,
        ge=1,
        description="Deprecated compatibility alias for the bounded idle-cycle limit.",
    )


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
