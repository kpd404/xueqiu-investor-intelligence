"""Real PostgreSQL session/pool boundary; explicit isolated database only."""

import asyncio
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from operations.locking import OPERATIONAL_REFRESH_LOCK_KEY, OperationalRefreshLock


@pytest.fixture
def pools():
    url = os.getenv("SNOWBALL_LOCK_TEST_URL")
    if not url:
        pytest.skip("Explicit isolated PostgreSQL URL required")
    assert make_url(url).database.startswith("snowball_lock_test_")
    engines = [create_engine(url, pool_size=3, max_overflow=0) for _ in range(2)]
    try:
        yield engines
    finally:
        for engine in engines:
            engine.dispose()


def contender(engine):
    with engine.connect() as c:
        acquired = c.scalar(
            text("select pg_try_advisory_lock(:k)"), {"k": OPERATIONAL_REFRESH_LOCK_KEY}
        )
        if acquired:
            assert c.scalar(
                text("select pg_advisory_unlock(:k)"), {"k": OPERATIONAL_REFRESH_LOCK_KEY}
            )
        return acquired


def test_commits_pool_turnover_and_release(pools):
    first, second = pools
    with sessionmaker(first)() as session:
        lock = OperationalRefreshLock(session)
        assert lock.try_acquire()
        physical_pid = lock._connection.scalar(text("select pg_backend_pid()"))
        lock._connection.commit()
        # Hold the returned pooled connection: old implementation unlocks on another backend.
        with first.connect() as borrowed:
            borrowed.scalar(text("select pg_backend_pid()"))
            for _ in range(3):
                session.execute(text("select 1"))
                session.commit()
                assert not contender(second)
                assert lock._connection.scalar(text("select pg_backend_pid()")) == physical_pid
                lock._connection.commit()
            session.rollback()
            lock.release()
        assert contender(second), (
            "Session advisory lock leaked after release on different connection"
        )


def test_repeated_acquire_is_not_reentrant_pg_count(pools):
    first, second = pools
    with sessionmaker(first)() as s:
        lock = OperationalRefreshLock(s)
        assert lock.try_acquire()
        assert lock.try_acquire()
        assert not contender(second)
        lock.release()
        lock.release()
        assert contender(second)


def test_exception_rollback_and_cancel_finally(pools):
    first, second = pools

    async def work(cancel):
        with sessionmaker(first)() as s:
            lock = OperationalRefreshLock(s)
            assert lock.try_acquire()
            try:
                s.execute(text("select 1"))
                s.rollback()
                assert not contender(second)
                if cancel:
                    raise asyncio.CancelledError()
                raise ValueError("stage failed")
            finally:
                lock.release()

    for cancel in [False, True]:
        with pytest.raises(asyncio.CancelledError if cancel else ValueError):
            asyncio.run(work(cancel))
        assert contender(second)


def test_failed_acquire_does_not_pin_or_execute(pools):
    first, second = pools
    with sessionmaker(first)() as a, sessionmaker(second)() as b:
        holder, rejected = OperationalRefreshLock(a), OperationalRefreshLock(b)
        assert holder.try_acquire()
        assert not rejected.try_acquire()
        rejected.release()
        assert not contender(second)
        holder.release()
        assert rejected.try_acquire()
        rejected.release()
        assert contender(first)


@pytest.mark.parametrize("mode", ["unlocked", "disconnected", "invalidated"])
def test_release_failure_discards_physical_connection(pools, mode):
    first, second = pools
    with sessionmaker(first)() as s:
        lock = OperationalRefreshLock(s)
        assert lock.try_acquire()
        pinned = lock._connection
        old_pid = pinned.scalar(text("select pg_backend_pid()"))
        pinned.commit()
        if mode == "unlocked":
            pinned.scalar(
                text("select pg_advisory_unlock(:k)"), {"k": OPERATIONAL_REFRESH_LOCK_KEY}
            )
            pinned.commit()
        elif mode == "disconnected":
            pinned.connection.driver_connection.close()
        else:
            pinned.invalidate()
        with pytest.raises((RuntimeError, DBAPIError)):
            lock.release()
        assert lock._connection is None
        assert contender(second)
        with first.connect() as c:
            assert c.scalar(text("select pg_backend_pid()")) != old_pid


@pytest.mark.parametrize(
    "outcome", ["success", "stage_failure", "cancel", "finalize_failure", "release_failure"]
)
def test_canonical_lock_covers_all_real_stages_and_cleanup(pools, outcome):
    import database.models  # noqa: F401
    from database.base import Base
    from operations.refresh import (
        CollectionStageResult,
        OperationalRefreshService,
        RefreshStage,
        RefreshStageError,
    )

    first, second = pools
    Base.metadata.create_all(first)
    visited = []

    def observe(stage):
        visited.append(stage)
        assert not contender(second), "Lock missing at canonical stage boundary"
        if stage == RefreshStage.FEED and outcome == "stage_failure":
            raise RefreshStageError(stage, "ISOLATED_FAILURE", "isolated failure")
        if stage == RefreshStage.FEED and outcome == "cancel":
            raise asyncio.CancelledError()

    class FixtureCollection(OperationalRefreshService):
        async def _collect(self, **kwargs):
            # Only external source is fixture; all downstream stages remain real.
            return CollectionStageResult(run_id=None, stop_reason="ISOLATED_NO_INPUT")

        def _finish_execution(self, execution, summary):
            assert not contender(second)
            if outcome == "finalize_failure":
                raise RuntimeError("isolated finalizer failure")
            if outcome == "release_failure":
                pinned = execution.lock._connection
                pinned.scalar(
                    text("select pg_advisory_unlock(:k)"), {"k": OPERATIONAL_REFRESH_LOCK_KEY}
                )
                pinned.commit()
            return super()._finish_execution(execution, summary)

    service = FixtureCollection(sessionmaker(first), stage_observer=observe)
    if outcome in {"cancel", "finalize_failure", "release_failure"}:
        with pytest.raises(asyncio.CancelledError if outcome == "cancel" else RuntimeError):
            asyncio.run(service.run())
    else:
        result = asyncio.run(service.run())
        assert result.result == ("SUCCESS" if outcome == "success" else "FAILED")
        if outcome == "stage_failure":
            assert result.errors[0]["stage"] == "FEED"
    assert visited
    if outcome == "success":
        assert visited[-1] == RefreshStage.PRODUCT_VERIFICATION
    assert contender(second)
    if outcome == "release_failure":
        with first.connect() as c:
            latest = c.execute(
                text(
                    "select status,failure_stage from operational_refresh_runs "
                    "order by started_at desc limit 1"
                )
            ).one()
            assert latest == ("FAILED", "LOCK_RELEASE")


def test_canonical_rejected_never_collects(pools):
    from database.base import Base
    from operations.refresh import OperationalRefreshService

    first, second = pools
    Base.metadata.create_all(second)

    class RefuseCollection(OperationalRefreshService):
        async def _collect(self, **kwargs):
            raise AssertionError("Rejected invocation must not execute")

    with sessionmaker(first)() as s:
        holder = OperationalRefreshLock(s)
        assert holder.try_acquire()
        result = asyncio.run(RefuseCollection(sessionmaker(second)).run())
        assert result.result == "SKIPPED_ALREADY_RUNNING"
        holder.release()
    assert contender(second)
