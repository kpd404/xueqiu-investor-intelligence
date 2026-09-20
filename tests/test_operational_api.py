from datetime import UTC, datetime

from contracts import (
    OperationalFreshness,
    OperationalRefreshStatus,
    OperationalRefreshTrigger,
    OperationalStatusLevel,
    OperationalStatusView,
)


def test_operational_status_route_projects_safe_user_facing_contract(client, monkeypatch) -> None:
    from backend.app.api.routes import operations

    payload = OperationalStatusView(
        status=OperationalStatusLevel.SOURCE_LIMITED,
        freshness=OperationalFreshness.STALE,
        freshness_age_seconds=7200,
        last_refresh_started_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
        last_refresh_finished_at=datetime(2026, 9, 20, 8, 1, tzinfo=UTC),
        last_successful_refresh_at=datetime(2026, 9, 20, 6, tzinfo=UTC),
        latest_status=OperationalRefreshStatus.FAILED,
        latest_trigger=OperationalRefreshTrigger.SCHEDULED,
        latest_failure_stage="COLLECTION",
        latest_failure_code="COLLECTION_RISK_CONTROLLED",
        next_expected_refresh_at=datetime(2026, 9, 20, 9, tzinfo=UTC),
    )

    class FakeStatusService:
        def get_status(self):
            return payload

    monkeypatch.setattr(operations, "OperationalStatusService", FakeStatusService)
    response = client.get("/api/operations/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SOURCE_LIMITED"
    assert body["freshness"] == "STALE"
    assert body["latest_failure_code"] == "COLLECTION_RISK_CONTROLLED"
    assert "stack" not in str(body).lower()
