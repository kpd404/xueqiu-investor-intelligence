from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from contracts import EventType


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


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
