from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import RawEventDTO, RawEventWriteResult
from database.models.raw_event import RawEvent


class RawEventRepository:
    """SQLAlchemy persistence adapter for append-only raw events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, event_id: UUID) -> RawEvent | None:
        return self._session.get(RawEvent, event_id)

    def get_by_hash(self, event_hash: str) -> RawEvent | None:
        statement = select(RawEvent).where(RawEvent.hash == event_hash)
        return self._session.scalar(statement)

    def add_if_absent(self, dto: RawEventDTO) -> RawEventWriteResult:
        existing = self.get_by_hash(dto.hash)
        if existing is not None:
            return self._result(existing, created=False)

        raw_event = RawEvent(
            investor_id=dto.investor_id,
            event_type=dto.event_type,
            source=dto.source,
            url=dto.url,
            published_time=dto.published_time,
            content=dto.content,
            raw_data=dto.raw_data,
            hash=dto.hash,
            collected_time=dto.collected_time,
        )

        try:
            with self._session.begin_nested():
                self._session.add(raw_event)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_hash(dto.hash)
            if existing is None:
                raise
            return self._result(existing, created=False)

        return self._result(raw_event, created=True)

    @staticmethod
    def _result(event: RawEvent, *, created: bool) -> RawEventWriteResult:
        return RawEventWriteResult(event_id=event.id, hash=event.hash, created=created)
