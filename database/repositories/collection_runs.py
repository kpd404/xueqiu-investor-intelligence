from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts import (
    CollectionRunCreate,
    CollectionRunStatus,
    CollectionRunView,
)
from database.models.collection_run import CollectionRun


class CollectionRunRepository:
    """Persistence adapter for CollectionRun lifecycle records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, command: CollectionRunCreate) -> CollectionRunView:
        entity = CollectionRun(
            source=command.source,
            adapter_name=command.adapter_name,
            collection_mode=command.collection_mode.value,
            transport=command.transport.value,
            started_at=command.started_at,
            ended_at=command.ended_at,
            run_status=command.run_status.value,
            stop_reason=command.stop_reason,
            coverage_status=command.coverage_status.value,
            requested_window_start=command.requested_window_start,
            requested_window_end=command.requested_window_end,
            scope_type=command.scope_type,
            scope_key=command.scope_key,
            collector_version=command.collector_version,
            parameters_json=command.parameters_json,
            summary_json=command.summary_json,
            created_at=command.created_at,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def get_run(self, run_id: UUID) -> CollectionRunView | None:
        entity = self._session.get(CollectionRun, run_id)
        return self._to_view(entity) if entity is not None else None

    def list_runs(self) -> list[CollectionRunView]:
        statement = select(CollectionRun).order_by(
            CollectionRun.started_at,
            CollectionRun.id,
        )
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def finish_run(
        self,
        run_id: UUID,
        *,
        ended_at: datetime,
        stop_reason: str | None = None,
        summary_json: dict[str, object] | None = None,
    ) -> CollectionRunView:
        return self._close_run(
            run_id,
            ended_at=ended_at,
            status=CollectionRunStatus.COMPLETED,
            stop_reason=stop_reason,
            summary_json=summary_json,
        )

    def fail_run(
        self,
        run_id: UUID,
        *,
        ended_at: datetime,
        stop_reason: str | None = None,
        summary_json: dict[str, object] | None = None,
    ) -> CollectionRunView:
        return self._close_run(
            run_id,
            ended_at=ended_at,
            status=CollectionRunStatus.FAILED,
            stop_reason=stop_reason,
            summary_json=summary_json,
        )

    def abort_run(
        self,
        run_id: UUID,
        *,
        ended_at: datetime,
        stop_reason: str | None = None,
        summary_json: dict[str, object] | None = None,
    ) -> CollectionRunView:
        return self._close_run(
            run_id,
            ended_at=ended_at,
            status=CollectionRunStatus.ABORTED,
            stop_reason=stop_reason,
            summary_json=summary_json,
        )

    def _close_run(
        self,
        run_id: UUID,
        *,
        ended_at: datetime,
        status: CollectionRunStatus,
        stop_reason: str | None,
        summary_json: dict[str, object] | None,
    ) -> CollectionRunView:
        entity = self._session.get(CollectionRun, run_id)
        if entity is None:
            raise LookupError(f"CollectionRun not found: {run_id}")
        entity.ended_at = ended_at
        entity.run_status = status.value
        entity.stop_reason = stop_reason
        if summary_json is not None:
            entity.summary_json = summary_json
        self._session.flush()
        return self._to_view(entity)

    @classmethod
    def _to_view(cls, entity: CollectionRun) -> CollectionRunView:
        return CollectionRunView(
            id=entity.id,
            source=entity.source,
            adapter_name=entity.adapter_name,
            collection_mode=entity.collection_mode,
            transport=entity.transport,
            started_at=cls._as_utc(entity.started_at),
            ended_at=cls._as_utc(entity.ended_at) if entity.ended_at is not None else None,
            run_status=entity.run_status,
            stop_reason=entity.stop_reason,
            coverage_status=entity.coverage_status,
            requested_window_start=(
                cls._as_utc(entity.requested_window_start)
                if entity.requested_window_start is not None
                else None
            ),
            requested_window_end=(
                cls._as_utc(entity.requested_window_end)
                if entity.requested_window_end is not None
                else None
            ),
            scope_type=entity.scope_type,
            scope_key=entity.scope_key,
            collector_version=entity.collector_version,
            parameters_json=entity.parameters_json,
            summary_json=entity.summary_json,
            created_at=cls._as_utc(entity.created_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["CollectionRunRepository"]
