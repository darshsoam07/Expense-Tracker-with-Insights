"""Integration tests for the transfers 501 endpoint (PR 4b).

Requires the real PostgreSQL database. Proves that:
1. Authenticated requests with valid CSRF receive 501 Not Implemented.
2. Authenticated requests without CSRF are rejected with 403 Forbidden.
3. No financial records, tables, or balance changes occur.
"""

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.integration.conftest import UserFactory, login

TRANSFERS = "/api/v1/transfers"


def test_authenticated_transfer_returns_501(
    api: TestClient, make_user: UserFactory, runtime_engine: Engine
) -> None:
    user = make_user(("operator",))
    session_data = login(api, user.email)
    csrf_token = str(session_data["csrf_token"])

    # 1. State-changing request without CSRF is rejected
    no_csrf_resp = api.post(TRANSFERS, json={"amount": 5000})
    assert no_csrf_resp.status_code == 403
    assert no_csrf_resp.json()["error"]["code"] == "csrf_failed"

    # 2. Authenticated request with valid CSRF returns honest 501
    resp = api.post(
        TRANSFERS,
        json={"amount": 5000, "source": 0, "destination": 1},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 501
    error = resp.json()["error"]
    assert error["code"] == "not_implemented"
    assert error["message"] == "Transfers are not available yet."
    assert "request_id" in error

    # 3. Prove no financial tables or records exist in the database
    with runtime_engine.connect() as conn:
        tables = set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'ledgerops'")
            ).scalars()
        )
        assert "transfers" not in tables
        assert "journal_entries" not in tables
        assert "accounts" not in tables
