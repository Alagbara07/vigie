import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.api.health import build_health_response


def test_health_reports_api_and_database(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "vigie-api",
        "api": "ok",
        "database": "ok",
    }


def test_database_accepts_a_query(engine: Engine) -> None:
    assert engine.dialect.name == "postgresql"
    assert engine.url.database == "vigie_test"

    with engine.connect() as connection:
        value = connection.execute(text("SELECT 1")).scalar_one()

    assert value == 1


def test_health_is_degraded_when_database_is_unavailable() -> None:
    response = build_health_response("unavailable")

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "degraded",
        "service": "vigie-api",
        "api": "ok",
        "database": "unavailable",
    }


def test_unknown_route_is_not_an_internal_error(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
