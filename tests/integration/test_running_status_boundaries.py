from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.main import app
from config import Settings
from contracts import (
    OperationalRefreshRunCreate,
    OperationalRefreshStatus,
    OperationalRefreshTrigger,
)
from database.base import Base
from database.models import CollectionRun
from database.repositories import OperationalRefreshRunRepository
from operations.status import OperationalStatusService


def rows(factory):
    with factory() as session:
        return {
            table.name: sorted(repr(tuple(row)) for row in session.execute(select(table)))
            for table in Base.metadata.sorted_tables
        }


@pytest.mark.parametrize(
    ("latest_status", "expected"),
    [
        ("SUCCESS", "HEALTHY"),
        ("FAILED", "ACTION_REQUIRED"),
        ("PARTIAL_FAILURE", "ACTION_REQUIRED"),
        ("RUNNING", "UNKNOWN"),
    ],
)
def test_historical_running_does_not_override_latest_or_mutate_history(
    db_session_factory, monkeypatch, latest_status, expected
):
    now = datetime(2026, 10, 11, 6, tzinfo=UTC)
    with db_session_factory() as session:
        repo = OperationalRefreshRunRepository(session)
        historical = repo.create_run(
            OperationalRefreshRunCreate(
                trigger=OperationalRefreshTrigger.SCHEDULED, started_at=now - timedelta(days=19)
            )
        )
        # Incomplete source provenance does not prove an end, failure, or current activity.
        session.add(
            CollectionRun(
                source="xueqiu",
                adapter_name="fixture",
                collection_mode="ENTITY_HISTORY",
                transport="BROWSER_CDP",
                started_at=historical.started_at,
                run_status="RUNNING",
                coverage_status="UNKNOWN",
            )
        )
        success = repo.create_run(
            OperationalRefreshRunCreate(
                trigger=OperationalRefreshTrigger.MANUAL, started_at=now - timedelta(minutes=15)
            )
        )
        repo.finish_run(
            success.id,
            finished_at=now - timedelta(minutes=14),
            status=OperationalRefreshStatus.SUCCESS,
        )
        latest = repo.create_run(
            OperationalRefreshRunCreate(
                trigger=OperationalRefreshTrigger.SCHEDULED, started_at=now - timedelta(minutes=2)
            )
        )
        if latest_status != "RUNNING":
            repo.finish_run(
                latest.id,
                finished_at=now - timedelta(minutes=1),
                status=OperationalRefreshStatus(latest_status),
                failure_stage="COLLECTION" if latest_status != "SUCCESS" else None,
                failure_code="CDP_UNAVAILABLE" if latest_status != "SUCCESS" else None,
            )
        session.commit()
    before = rows(db_session_factory)
    service = OperationalStatusService(
        db_session_factory,
        settings=Settings(database_url="sqlite+pysqlite:///:memory:"),
        now_factory=lambda: now,
    )
    import backend.app.api.routes.operations as route

    monkeypatch.setattr(route, "OperationalStatusService", lambda: service)
    with TestClient(app) as client:
        response = client.get("/api/operations/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected
    assert payload["latest_status"] == latest_status
    assert payload["last_refresh_started_at"] == latest.started_at.isoformat().replace(
        "+00:00", "Z"
    )
    if latest_status == "RUNNING":
        assert payload["last_refresh_finished_at"] is None
        assert payload["latest_failure_code"] is None
    assert rows(db_session_factory) == before
    with db_session_factory() as session:
        retained = OperationalRefreshRunRepository(session).get(historical.id)
        assert retained.status is OperationalRefreshStatus.RUNNING
        assert retained.finished_at is None


def test_only_unfinished_record_is_unknown_even_without_source_or_logs(db_session_factory):
    with db_session_factory() as session:
        OperationalRefreshRunRepository(session).create_run(
            OperationalRefreshRunCreate(
                trigger=OperationalRefreshTrigger.SCHEDULED,
                started_at=datetime(2026, 9, 22, tzinfo=UTC),
            )
        )
        session.commit()
    before = rows(db_session_factory)
    result = OperationalStatusService(db_session_factory).get_status()
    assert result.status.value == "UNKNOWN"
    assert result.latest_status.value == "RUNNING"
    assert result.last_refresh_finished_at is None
    assert result.freshness.value == "UNKNOWN"
    assert rows(db_session_factory) == before


def test_unfinished_history_does_not_control_canonical_entry_eligibility(db_session_factory):
    from operations.refresh import OperationalRefreshService, RefreshSummary

    with db_session_factory() as session:
        historical = OperationalRefreshRunRepository(session).create_run(
            OperationalRefreshRunCreate(
                trigger=OperationalRefreshTrigger.SCHEDULED,
                started_at=datetime(2026, 9, 22, tzinfo=UTC),
            )
        )
        session.commit()
    service = OperationalRefreshService(db_session_factory)
    # Exercise real entry/finish and lock boundaries; never run collection or providers.
    execution = service._begin_execution(OperationalRefreshTrigger.MANUAL)
    assert execution is not None
    try:
        contender = service._begin_execution(OperationalRefreshTrigger.MANUAL)
        assert contender is None
    finally:
        service._finish_execution(execution, RefreshSummary(
            started_at=datetime.now(UTC), result='FAILED',
            errors=[{'stage': 'COLLECTION', 'code': 'FIXTURE_NO_COLLECTION'}],
        ))
    with db_session_factory() as session:
        repo = OperationalRefreshRunRepository(session)
        assert repo.get(historical.id).status.value == 'RUNNING'
        assert repo.get(execution.run_id).failure_code == 'FIXTURE_NO_COLLECTION'
