"""Explicit user state writes; existing Feed evidence rules remain authoritative."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect

from contracts import FeedState
from database.session import SessionFactory
from intelligence.product.inbox import EditInboxState, InboxService

router = APIRouter(prefix="/api/inbox", tags=["inbox-user-progress"])


def get_inbox_service():
    if not inspect(SessionFactory.kw["bind"]).has_table("inbox_user_states"):
        raise HTTPException(503, "Inbox 用户处理存储未安装；本轮只在隔离环境启用。")
    return InboxService(SessionFactory)


Service = Annotated[InboxService, Depends(get_inbox_service)]


@router.get("")
def list_inbox(
    service: Service,
    filter: Literal["ALL", "UNREAD", "PENDING"] = "ALL",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    state: FeedState | None = FeedState.ACTIVE,
    since: datetime | None = None,
):
    try:
        return service.list(filter=filter, limit=limit, offset=offset, state=state, since=since)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/{feed_id}/user-state")
def edit_inbox(feed_id: UUID, body: EditInboxState, service: Service):
    try:
        return service.edit(feed_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
