import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes.health import health_check


def test_health_check_reports_application_and_database(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "version": "0.1.0"}


def test_health_check_returns_503_when_database_is_unavailable() -> None:
    class UnavailableDatabase:
        def execute(self, *_: object) -> None:
            raise SQLAlchemyError("unavailable")

    with pytest.raises(HTTPException) as raised:
        health_check(UnavailableDatabase())  # type: ignore[arg-type]

    assert raised.value.status_code == 503
    assert raised.value.detail == "database unavailable"
