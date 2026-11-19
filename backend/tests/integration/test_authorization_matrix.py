"""Phase 1 authorization matrix, for the endpoints that exist in PR 4a.

Roles differ from the Phase 1 plan's customer/operations/admin: PR 4a seeds admin, operator,
approver, auditor and viewer. The `customer` role and /customers/me arrive with the customer
model (PR 6b); /ops/ping and registration are not part of PR 4a.
"""

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import UserFactory, login

ROLES: list[tuple[str, ...]] = [
    ("admin",),
    ("operator",),
    ("approver",),
    ("auditor",),
    ("viewer",),
    (),  # authenticated, no role: still allowed to see themselves and log out
]


def test_anonymous_cells(api: TestClient) -> None:
    assert api.get("/api/v1/auth/csrf").status_code == 200
    assert api.get("/api/v1/me").status_code == 401
    # Logout without a session: CSRF is checked first (403 without a token), then 401.
    assert api.post("/api/v1/auth/logout").status_code == 403
    token = api.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert api.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token}).status_code == 401


@pytest.mark.parametrize("roles", ROLES, ids=lambda r: "+".join(r) or "no-role")
def test_every_authenticated_role_can_read_me_and_log_out(
    api: TestClient, make_user: UserFactory, roles: tuple[str, ...]
) -> None:
    user = make_user(roles)
    state = login(api, user.email)
    me = api.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["user"]["roles"] == sorted(roles)
    assert me.json()["csrf_token"] == state["csrf_token"]
    assert api.post("/api/v1/auth/logout").status_code == 403  # no CSRF token
    out = api.post("/api/v1/auth/logout", headers={"X-CSRF-Token": str(state["csrf_token"])})
    assert out.status_code == 204
    assert api.get("/api/v1/me").status_code == 401


def test_the_old_auth_me_path_is_gone(api: TestClient, make_user: UserFactory) -> None:
    login(api, make_user(("viewer",)).email)
    assert api.get("/api/v1/auth/me").status_code == 404
