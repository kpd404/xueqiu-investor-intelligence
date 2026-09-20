"""Query-time operational status and freshness projection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from config import Settings, get_settings
from contracts import (
    OperationalFreshness,
    OperationalRefreshStatus,
    OperationalStatusLevel,
    OperationalStatusView,
)
from database.repositories import OperationalRefreshRunRepository
from database.session import SessionFactory


class OperationalStatusService:
    def __init__(
        self,
        session_factory: Callable = SessionFactory,
        *,
        settings: Settings | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings or get_settings()
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    def get_status(self) -> OperationalStatusView:
        with self._session_factory() as session:
            repository = OperationalRefreshRunRepository(session)
            runs = repository.list_recent(limit=20)
            latest = repository.get_latest()
            latest_success = repository.get_latest_success()

        now = self._normalize(self._now_factory())
        successful_at = latest_success.finished_at if latest_success else None
        age_seconds = (
            max(0.0, (now - self._normalize(successful_at)).total_seconds())
            if successful_at is not None
            else None
        )
        freshness = self._freshness(age_seconds)
        level = self._status_level(latest, freshness)
        next_expected = (
            self._normalize(successful_at)
            + timedelta(minutes=self._settings.operational_refresh_interval_minutes)
            if successful_at is not None
            else None
        )
        latest_failure = next(
            (
                run
                for run in runs
                if run.status
                in {
                    OperationalRefreshStatus.FAILED,
                    OperationalRefreshStatus.PARTIAL_FAILURE,
                }
            ),
            None,
        )
        return OperationalStatusView(
            status=level,
            freshness=freshness,
            freshness_age_seconds=age_seconds,
            last_refresh_started_at=latest.started_at if latest else None,
            last_refresh_finished_at=latest.finished_at if latest else None,
            last_successful_refresh_at=successful_at,
            latest_status=latest.status if latest else None,
            latest_trigger=latest.trigger if latest else None,
            latest_failure_stage=latest_failure.failure_stage if latest_failure else None,
            latest_failure_code=latest_failure.failure_code if latest_failure else None,
            next_expected_refresh_at=next_expected,
        )

    def _freshness(self, age_seconds: float | None) -> OperationalFreshness:
        if age_seconds is None:
            return OperationalFreshness.UNKNOWN
        if age_seconds <= self._settings.operational_refresh_stale_after_minutes * 60:
            return OperationalFreshness.FRESH
        return OperationalFreshness.STALE

    @staticmethod
    def _status_level(
        latest,
        freshness: OperationalFreshness,
    ) -> OperationalStatusLevel:
        if latest is None:
            return OperationalStatusLevel.UNKNOWN
        if latest.status in {
            OperationalRefreshStatus.SUCCESS,
            OperationalRefreshStatus.SKIPPED_ALREADY_RUNNING,
        }:
            return (
                OperationalStatusLevel.HEALTHY
                if freshness is OperationalFreshness.FRESH
                else OperationalStatusLevel.STALE
            )
        if latest.failure_code in {
            "AUTH_REQUIRED",
            "COLLECTION_AUTH_REQUIRED",
            "CDP_UNAVAILABLE",
        }:
            return OperationalStatusLevel.ACTION_REQUIRED
        if latest.failure_code in {"RISK_CONTROLLED", "COLLECTION_RISK_CONTROLLED"}:
            return OperationalStatusLevel.SOURCE_LIMITED
        return OperationalStatusLevel.ACTION_REQUIRED

    @staticmethod
    def _normalize(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["OperationalStatusService"]
