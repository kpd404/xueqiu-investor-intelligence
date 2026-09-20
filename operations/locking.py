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

    def try_acquire(self) -> bool:
        if self._dialect == "postgresql":
            acquired = bool(
                self._session.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": OPERATIONAL_REFRESH_LOCK_KEY},
                )
            )
            self._acquired = acquired
            if acquired:
                self._session.commit()
            return acquired
        self._process_acquired = _PROCESS_LOCK.acquire(blocking=False)
        self._acquired = self._process_acquired
        return self._acquired

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            if self._dialect == "postgresql":
                self._session.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": OPERATIONAL_REFRESH_LOCK_KEY},
                )
                self._session.commit()
            elif self._process_acquired:
                _PROCESS_LOCK.release()
        finally:
            self._acquired = False
            self._process_acquired = False


__all__ = ["OPERATIONAL_REFRESH_LOCK_KEY", "OperationalRefreshLock"]
