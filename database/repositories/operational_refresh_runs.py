"""Repository for full operational refresh execution metadata."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts import (
    OperationalRefreshRunCreate,
    OperationalRefreshRunView,
    OperationalRefreshStatus,
    OperationalRefreshTrigger,
)
from database.models.operational_refresh_run import OperationalRefreshRun


class OperationalRefreshRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, command: OperationalRefreshRunCreate) -> OperationalRefreshRunView:
        entity = OperationalRefreshRun(
            started_at=command.started_at,
            status=OperationalRefreshStatus.RUNNING.value,
            trigger=command.trigger.value,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def create_skipped(
        self,
        *,
        trigger: OperationalRefreshTrigger,
        started_at: datetime,
        summary_json: dict[str, object] | None = None,
    ) -> OperationalRefreshRunView:
        entity = OperationalRefreshRun(
            started_at=started_at,
            finished_at=started_at,
            status=OperationalRefreshStatus.SKIPPED_ALREADY_RUNNING.value,
            trigger=trigger.value,
            summary_json=summary_json,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def finish_run(
        self,
        run_id: UUID,
        *,
        finished_at: datetime,
        status: OperationalRefreshStatus,
        failure_stage: str | None = None,
        failure_code: str | None = None,
        summary_json: dict[str, object] | None = None,
    ) -> OperationalRefreshRunView:
        entity = self._session.get(OperationalRefreshRun, run_id)
        if entity is None:
            raise LookupError(f"OperationalRefreshRun not found: {run_id}")
        entity.finished_at = finished_at
        entity.status = status.value
        entity.failure_stage = failure_stage
        entity.failure_code = failure_code
        if summary_json is not None:
            entity.summary_json = summary_json
        self._session.flush()
        return self._to_view(entity)

    def get(self, run_id: UUID) -> OperationalRefreshRunView | None:
        entity = self._session.get(OperationalRefreshRun, run_id)
        return self._to_view(entity) if entity is not None else None

    def list_recent(self, limit: int = 10) -> list[OperationalRefreshRunView]:
        statement = (
            select(OperationalRefreshRun)
            .order_by(OperationalRefreshRun.started_at.desc(), OperationalRefreshRun.id.desc())
            .limit(limit)
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def get_latest(self) -> OperationalRefreshRunView | None:
        statement = (
            select(OperationalRefreshRun)
            .order_by(
                OperationalRefreshRun.started_at.desc(),
                OperationalRefreshRun.id.desc(),
            )
            .limit(1)
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def get_latest_success(self) -> OperationalRefreshRunView | None:
        statement = (
            select(OperationalRefreshRun)
            .where(OperationalRefreshRun.status == OperationalRefreshStatus.SUCCESS.value)
            .order_by(OperationalRefreshRun.finished_at.desc(), OperationalRefreshRun.id.desc())
            .limit(1)
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    @classmethod
    def _to_view(cls, entity: OperationalRefreshRun) -> OperationalRefreshRunView:
        return OperationalRefreshRunView(
            id=entity.id,
            trigger=OperationalRefreshTrigger(entity.trigger),
            started_at=cls._as_utc(entity.started_at),
            finished_at=cls._as_utc(entity.finished_at) if entity.finished_at else None,
            status=OperationalRefreshStatus(entity.status),
            failure_stage=entity.failure_stage,
            failure_code=entity.failure_code,
            summary_json=entity.summary_json,
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["OperationalRefreshRunRepository"]
