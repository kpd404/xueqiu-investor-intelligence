"""Overlay explicit user progress after existing effective Feed selection."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, model_validator
from sqlalchemy import select

from database.models import InboxUserState, IntelligenceFeedItem
from database.models._types import utc_now
from intelligence.feed.query import IntelligenceFeedQueryService


class EditInboxState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read: StrictBool | None = None
    processed: StrictBool | None = None

    @model_validator(mode="after")
    def explicit(self):
        if not self.model_fields_set or any(
            getattr(self, k) is None for k in self.model_fields_set
        ):
            raise ValueError("必须明确指定阅读或处理状态。")
        return self


class InboxService:
    def __init__(self, sessions):
        self.sessions = sessions

    def edit(self, feed_id: UUID, body: EditInboxState):
        with self.sessions() as session:
            # Serialize user updates per real Feed, without changing that Feed.
            if (
                session.scalar(
                    select(IntelligenceFeedItem)
                    .where(IntelligenceFeedItem.id == feed_id)
                    .with_for_update()
                )
                is None
            ):
                raise LookupError("Feed 不存在。")
            record = session.get(InboxUserState, feed_id)
            if record is None:
                record = InboxUserState(feed_id=feed_id, read=False, processed=False)
                session.add(record)
            changed = False
            for key in body.model_fields_set:
                value = getattr(body, key)
                if getattr(record, key) != value:
                    setattr(record, key, value)
                    changed = True
            if changed:
                record.updated_at = utc_now()
            session.commit()
            return {"read": record.read, "processed": record.processed}

    def list(
        self, *, filter: Literal["ALL", "UNREAD", "PENDING"] = "ALL", limit=20, offset=0, **scope
    ):
        if offset < 0:
            raise ValueError("offset must be nonnegative")
        states = {}

        def overlay(items):
            with self.sessions() as s:
                rows = (
                    s.scalars(
                        select(InboxUserState).where(
                            InboxUserState.feed_id.in_([v.id for v in items])
                        )
                    ).all()
                    if items
                    else []
                )
                states.update({r.feed_id: {"read": r.read, "processed": r.processed} for r in rows})
            return [
                v
                for v in items
                if filter == "ALL"
                or (filter == "UNREAD" and not states.get(v.id, {}).get("read", False))
                or (filter == "PENDING" and not states.get(v.id, {}).get("processed", False))
            ]

        result = IntelligenceFeedQueryService.from_production(self.sessions).list_feed(
            limit=limit, _offset=offset, _transform=overlay, **scope
        )
        return {
            "items": [
                dict(
                    v.model_dump(mode="json"),
                    user_state=states.get(v.id, {"read": False, "processed": False}),
                )
                for v in result.items
            ],
            "total": result.total,
            "limit": limit,
            "offset": offset,
            "has_more": result.has_more,
        }
