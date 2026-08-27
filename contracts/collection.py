from datetime import UTC, datetime
from enum import StrEnum
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


class CollectionRequest(BaseModel):
    """Source-independent request identifying an investor and collection window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    platform_user_id: str = Field(min_length=1, max_length=255)
    homepage_url: str | None = Field(default=None, max_length=2048)
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    limit: int | None = Field(default=None, ge=1)
    requested_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_collection_window(self) -> "CollectionRequest":
        if self.since is not None and self.until is not None and self.since > self.until:
            raise ValueError("since must be earlier than or equal to until")
        return self


class FeedPostKind(StrEnum):
    """Source-neutral classification for a feed item."""

    ORIGINAL = "ORIGINAL"
    REPOST = "REPOST"
    COLUMN = "COLUMN"
    UNKNOWN = "UNKNOWN"


# Short alias for callers that do not need to distinguish the feed context.
PostKind = FeedPostKind


class FeedCollectionRequest(BaseModel):
    """Bounded request for consuming batches from a feed response stream.

    ``max_batches`` counts valid response batches, not scroll gestures or page
    numbers. The contract is intentionally independent of any browser or
    source implementation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_batches: int = Field(default=1, ge=1)
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    only_author_ids: tuple[str, ...] = ()

    @field_validator("only_author_ids")
    @classmethod
    def normalize_author_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for author_id in value:
            candidate = author_id.strip()
            if not candidate:
                raise ValueError("only_author_ids must not contain blank values")
            if candidate not in normalized:
                normalized.append(candidate)
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_collection_window(self) -> "FeedCollectionRequest":
        if self.since is not None and self.until is not None and self.since > self.until:
            raise ValueError("since must be earlier than or equal to until")
        return self


class FeedPostItem(BaseModel):
    """Immutable, source-neutral item emitted by a feed parser.

    ``content`` is the current status' top-level text. Source-specific
    provenance, including a nested reposted status, remains in ``raw_data``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_event_id: str = Field(min_length=1)
    author_id: str = Field(min_length=1)
    event_type: EventType = EventType.POST
    post_kind: FeedPostKind = FeedPostKind.UNKNOWN
    url: str | None = Field(default=None, max_length=2048)
    published_time: AwareDatetime
    content: str = Field(min_length=1)
    raw_data: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("source_event_id", "author_id", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: object) -> str:
        if value is None or isinstance(value, bool):
            raise ValueError("identifier must be a non-empty value")
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("identifier must not be blank")
        return normalized

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value

    @property
    def author_user_id(self) -> str:
        """Compatibility spelling for adapters exposing platform IDs."""

        return self.author_id
