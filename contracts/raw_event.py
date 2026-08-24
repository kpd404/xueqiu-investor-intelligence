import hashlib
import json
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from contracts.enums import EventType


def utc_now() -> datetime:
    return datetime.now(UTC)


def compute_raw_event_hash(
    *,
    investor_id: UUID,
    event_type: EventType,
    source: str,
    url: str,
    published_time: datetime,
    content: str,
) -> str:
    """Build the canonical identity for an observed external fact."""

    if published_time.tzinfo is None or published_time.utcoffset() is None:
        raise ValueError("published_time must be timezone-aware")

    canonical = {
        "content": content.replace("\r\n", "\n").strip(),
        "event_type": event_type.value,
        "investor_id": str(investor_id),
        "published_time": published_time.astimezone(UTC).isoformat(timespec="microseconds"),
        "source": source.strip().lower(),
        "url": url.strip(),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RawEventDTO(BaseModel):
    """Immutable, normalized fact emitted by a source adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    event_type: EventType
    source: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=2048)
    published_time: AwareDatetime
    content: str = Field(min_length=1)
    raw_data: dict[str, JsonValue] = Field(default_factory=dict)
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    collected_time: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("source must not be blank")
        return normalized

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("url must not be blank")
        return normalized

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value

    @field_validator("published_time", "collected_time")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_hash(self) -> "RawEventDTO":
        expected = compute_raw_event_hash(
            investor_id=self.investor_id,
            event_type=self.event_type,
            source=self.source,
            url=self.url,
            published_time=self.published_time,
            content=self.content,
        )
        if self.hash != expected:
            raise ValueError("hash does not match the canonical raw event payload")
        return self

    @classmethod
    def build(
        cls,
        *,
        investor_id: UUID,
        event_type: EventType,
        source: str,
        url: str,
        published_time: datetime,
        content: str,
        raw_data: dict[str, JsonValue] | None = None,
        collected_time: datetime | None = None,
    ) -> Self:
        event_hash = compute_raw_event_hash(
            investor_id=investor_id,
            event_type=event_type,
            source=source,
            url=url,
            published_time=published_time,
            content=content,
        )
        return cls(
            investor_id=investor_id,
            event_type=event_type,
            source=source,
            url=url,
            published_time=published_time,
            content=content,
            raw_data=raw_data or {},
            hash=event_hash,
            collected_time=collected_time or utc_now(),
        )


class RawEventWriteResult(BaseModel):
    """Repository result that does not expose a persistence entity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created: bool


class RawEventView(BaseModel):
    """Immutable persisted-fact view provided to downstream processors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    investor_id: UUID
    event_type: EventType
    source: str
    url: str
    published_time: AwareDatetime
    content: str
    raw_data: dict[str, JsonValue]
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    collected_time: AwareDatetime
