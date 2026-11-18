import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.readiness import ReadinessRegistry
from tests.helpers import json_lines


def test_liveness_is_ok(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["cache-control"] == "no-store"


def test_readiness_requires_database_configuration(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"app_started": "ok", "database": "fail"},
    }
    assert response.headers["cache-control"] == "no-store"


def test_missing_database_is_not_ready(client: TestClient) -> None:
    """Missing database configuration must fail closed."""
    checks = client.get("/health/ready").json()["checks"]
    assert checks["database"] == "fail"


def test_not_ready_before_startup_completes_but_still_alive(app: FastAPI) -> None:
    client = TestClient(app)  # no "with": start-up has NOT run
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "not_ready",
        "checks": {"app_started": "fail", "database": "fail"},
    }
    assert client.get("/health/live").status_code == 200


def test_readiness_fails_as_soon_as_shutdown_begins(app: FastAPI, client: TestClient) -> None:
    app.state.readiness.mark_stopping()
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/live").status_code == 200  # liveness unaffected


def test_readiness_is_false_after_the_server_stops(app: FastAPI) -> None:
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 503
    assert app.state.readiness.run() == {"app_started": False, "database": False}


def test_a_failing_check_makes_the_service_not_ready_but_not_dead(
    app: FastAPI, client: TestClient
) -> None:
    app.state.readiness.register("example_dependency", lambda: False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"app_started": "ok", "database": "fail", "example_dependency": "fail"},
    }
    assert client.get("/health/live").status_code == 200


def test_a_passing_extra_check_is_reported(app: FastAPI, client: TestClient) -> None:
    app.state.readiness.register("example_dependency", lambda: True)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {
        "app_started": "ok",
        "database": "fail",
        "example_dependency": "ok",
    }


def test_a_crashing_check_is_a_failure_and_its_error_stays_in_the_logs(
    app: FastAPI, client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken() -> bool:
        raise ConnectionError("db password is hunter2")

    app.state.readiness.register("broken_dependency", broken)
    capsys.readouterr()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["broken_dependency"] == "fail"
    assert "hunter2" not in response.text
    warning = next(
        r for r in json_lines(capsys.readouterr().out) if r["event"] == "readiness.check_error"
    )
    assert warning["check"] == "broken_dependency"


def test_registering_the_same_check_twice_is_an_error() -> None:
    registry = ReadinessRegistry()
    registry.register("dependency", lambda: True)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dependency", lambda: True)


def test_health_endpoints_are_outside_the_versioned_api(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").status_code == 404
    assert client.get("/api/v1/health/ready").status_code == 404


def test_health_endpoints_are_not_part_of_the_public_api_docs(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert not any(path.startswith("/health") for path in paths)
