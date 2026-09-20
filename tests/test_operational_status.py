import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from config import Settings
from contracts import (
    OperationalRefreshRunCreate,
    OperationalRefreshStatus,
    OperationalRefreshTrigger,
    OperationalStatusLevel,
)
from database.repositories import OperationalRefreshRunRepository
from operations.locking import OperationalRefreshLock
from operations.status import OperationalStatusService


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        operational_refresh_interval_minutes=60,
        operational_refresh_stale_after_minutes=90,
    )


def _run(
    factory,
    *,
    started_at: datetime,
    status: OperationalRefreshStatus,
    failure_code: str | None = None,
) -> None:
    with factory() as session:
        repo = OperationalRefreshRunRepository(session)
        run = repo.create_run(
            OperationalRefreshRunCreate(
                trigger=OperationalRefreshTrigger.SCHEDULED,
                started_at=started_at,
            )
        )
        repo.finish_run(
            run.id,
            finished_at=started_at + timedelta(minutes=1),
            status=status,
            failure_stage="COLLECTION" if failure_code else None,
            failure_code=failure_code,
        )
        session.commit()


def test_status_is_unknown_without_a_run(db_session_factory) -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    status = OperationalStatusService(
        db_session_factory,
        settings=_settings(),
        now_factory=lambda: now,
    ).get_status()

    assert status.status is OperationalStatusLevel.UNKNOWN
    assert status.freshness.value == "UNKNOWN"
    assert status.last_successful_refresh_at is None


def test_successful_run_is_fresh(db_session_factory) -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    _run(
        db_session_factory,
        started_at=now - timedelta(minutes=12),
        status=OperationalRefreshStatus.SUCCESS,
    )

    status = OperationalStatusService(
        db_session_factory,
        settings=_settings(),
        now_factory=lambda: now,
    ).get_status()

    assert status.status is OperationalStatusLevel.HEALTHY
    assert status.freshness.value == "FRESH"
    assert status.freshness_age_seconds == 11 * 60


def test_old_successful_run_is_stale(db_session_factory) -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    _run(
        db_session_factory,
        started_at=now - timedelta(hours=3),
        status=OperationalRefreshStatus.SUCCESS,
    )

    status = OperationalStatusService(
        db_session_factory,
        settings=_settings(),
        now_factory=lambda: now,
    ).get_status()

    assert status.status is OperationalStatusLevel.STALE
    assert status.freshness.value == "STALE"


def test_auth_failure_is_action_required(db_session_factory) -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    _run(
        db_session_factory,
        started_at=now - timedelta(minutes=3),
        status=OperationalRefreshStatus.FAILED,
        failure_code="COLLECTION_AUTH_REQUIRED",
    )

    status = OperationalStatusService(
        db_session_factory,
        settings=_settings(),
        now_factory=lambda: now,
    ).get_status()

    assert status.status is OperationalStatusLevel.ACTION_REQUIRED
    assert status.latest_failure_code == "COLLECTION_AUTH_REQUIRED"
    assert status.last_successful_refresh_at is None


def test_success_after_failure_recovers_healthy(db_session_factory) -> None:
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    _run(
        db_session_factory,
        started_at=now - timedelta(hours=2),
        status=OperationalRefreshStatus.FAILED,
        failure_code="CDP_UNAVAILABLE",
    )
    _run(
        db_session_factory,
        started_at=now - timedelta(minutes=10),
        status=OperationalRefreshStatus.SUCCESS,
    )

    status = OperationalStatusService(
        db_session_factory,
        settings=_settings(),
        now_factory=lambda: now,
    ).get_status()

    assert status.status is OperationalStatusLevel.HEALTHY
    assert status.latest_status is OperationalRefreshStatus.SUCCESS
    assert status.last_successful_refresh_at is not None


def test_process_lock_skips_second_holder() -> None:
    class FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    first = OperationalRefreshLock(FakeSession())
    second = OperationalRefreshLock(FakeSession())
    assert first.try_acquire() is True
    assert second.try_acquire() is False
    first.release()
    assert second.try_acquire() is True
    second.release()


def test_scheduler_uses_scheduled_trigger(monkeypatch) -> None:
    import operations.scheduler as scheduler

    calls = []

    class FakeService:
        async def run(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                result=OperationalRefreshStatus.SUCCESS.value,
                counts={"operational_run_id": "test"},
            )

    monkeypatch.setattr(scheduler, "OperationalRefreshService", FakeService)
    result = asyncio.run(
        scheduler.run_scheduler(
            cdp_endpoint="http://127.0.0.1:9222",
            interval_minutes=60,
            once=True,
        )
    )

    assert result == 0
    assert calls[0]["trigger"] is OperationalRefreshTrigger.SCHEDULED
    assert calls[0]["cdp_endpoint"] == "http://127.0.0.1:9222"
    assert calls[0]["require_cdp"] is True


def test_scheduler_missing_endpoint_still_uses_canonical_failure(monkeypatch) -> None:
    import operations.scheduler as scheduler

    calls = []

    class FakeService:
        async def run(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                result=OperationalRefreshStatus.FAILED.value,
                counts={"operational_run_id": "missing-cdp"},
            )

    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            xueqiu_cdp_endpoint=None,
            operational_refresh_interval_minutes=60,
        ),
    )
    monkeypatch.setattr(scheduler, "OperationalRefreshService", FakeService)

    assert scheduler.main(["--once"]) == 1
    assert calls[0]["cdp_endpoint"] is None
    assert calls[0]["require_cdp"] is True
