"""Small single-run protection for the operational refresh."""

from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import text

OPERATIONAL_REFRESH_LOCK_KEY = 4_831_927_501
_PROCESS_LOCK = threading.Lock()


class OperationalRefreshLock:
    """Use a PostgreSQL advisory lock, with a local-process test fallback."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self._dialect = session.get_bind().dialect.name
        self._acquired = False
        self._process_acquired = False
        self._connection = None

    def try_acquire(self) -> bool:
        if self._acquired:
            return True
        if self._dialect == "postgresql":
            # A Session.commit() returns its connection to the pool. Hold a
            # separate physical session for the entire canonical operation.
            bind = self._session.get_bind()
            connection = bind.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            try:
                acquired = bool(
                    connection.scalar(
                        text("SELECT pg_try_advisory_lock(:lock_key)"),
                        {"lock_key": OPERATIONAL_REFRESH_LOCK_KEY},
                    )
                )
                connection.commit()
            except BaseException:
                connection.invalidate()
                connection.close()
                raise
            if not acquired:
                connection.close()
                return False
            self._connection = connection
            self._acquired = True
            return acquired
        self._process_acquired = _PROCESS_LOCK.acquire(blocking=False)
        self._acquired = self._process_acquired
        return self._acquired

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            if self._dialect == "postgresql":
                connection = self._connection
                try:
                    if connection is None or connection.closed or connection.invalidated:
                        raise RuntimeError("Refresh lock connection lost before release")
                    released = connection.scalar(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": OPERATIONAL_REFRESH_LOCK_KEY},
                    )
                    if not released:
                        raise RuntimeError("Refresh lock was not held by its pinned connection")
                    connection.commit()
                except BaseException:
                    if connection is not None:
                        connection.invalidate()
                    raise
                finally:
                    if connection is not None:
                        connection.close()
                    self._connection = None
            elif self._process_acquired:
                _PROCESS_LOCK.release()
        finally:
            self._acquired = False
            self._process_acquired = False


__all__ = ["OPERATIONAL_REFRESH_LOCK_KEY", "OperationalRefreshLock"]
