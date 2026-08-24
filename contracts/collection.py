from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


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
