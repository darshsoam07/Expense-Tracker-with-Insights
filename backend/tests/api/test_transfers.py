"""Unit tests for the transfers 501 endpoint placeholder (PR 4b)."""

from fastapi.testclient import TestClient


def test_transfer_requires_csrf_and_database(client: TestClient) -> None:
    """State-changing requests require CSRF; unconfigured database returns 503."""
    # 1. Without CSRF header, enforce_csrf rejects immediately with 403
    response_no_csrf = client.post("/api/v1/transfers", json={"amount": 100})
    assert response_no_csrf.status_code == 403
    assert response_no_csrf.json()["error"]["code"] == "csrf_failed"

    # 2. With CSRF token from anonymous bootstrap, database check runs before handler
    csrf_resp = client.get("/api/v1/auth/csrf")
    assert csrf_resp.status_code == 200
    token = csrf_resp.json()["csrf_token"]

    response_with_csrf = client.post(
        "/api/v1/transfers",
        json={"amount": 100},
        headers={"X-CSRF-Token": token},
    )
    # Unit test app has no database configured, so DbSession dependency raises 503
    assert response_with_csrf.status_code == 503
    assert response_with_csrf.json()["error"]["code"] == "database_unavailable"
