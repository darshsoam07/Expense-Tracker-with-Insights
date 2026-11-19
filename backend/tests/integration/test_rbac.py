"""require_permission(): effective permissions, denial audit and import-time validation."""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.tables import audit_events
from app.modules.auth.rbac import effective_permissions
from app.modules.auth.sessions import ActiveSession
from tests.integration.conftest import UserFactory, login

router = APIRouter(prefix="/api/v1/_test")


@router.get("/audit")
def read_audit(
    active: Annotated[ActiveSession, Depends(require_permission("audit.read"))],
) -> dict[str, str]:
    return {"user": str(active.user_id)}


@router.post("/manage")
def manage(
    active: Annotated[ActiveSession, Depends(require_permission("users.manage"))],
) -> dict[str, str]:
    return {"user": str(active.user_id)}


@pytest.fixture
def rbac_client(api: TestClient) -> TestClient:
    assert isinstance(api.app, FastAPI)
    api.app.include_router(router)
    return api


def test_unauthenticated_request_gets_401(rbac_client: TestClient) -> None:
    assert rbac_client.get("/api/v1/_test/audit").status_code == 401


def test_permission_is_granted_through_the_role(
    rbac_client: TestClient, make_user: UserFactory
) -> None:
    login(rbac_client, make_user(("auditor",)).email)
    assert rbac_client.get("/api/v1/_test/audit").status_code == 200


def test_missing_permission_is_403_and_audited(
    rbac_client: TestClient, make_user: UserFactory, runtime_engine: Engine
) -> None:
    user = make_user(("viewer",))
    login(rbac_client, user.email)
    response = rbac_client.get("/api/v1/_test/audit")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    with Session(runtime_engine) as db:
        row = db.execute(
            select(audit_events).where(
                audit_events.c.request_id == response.headers["x-request-id"]
            )
        ).one()
    assert (row.action, row.outcome, row.actor_principal) == (
        "authz.permission_denied",
        "denied",
        f"user:{user.id}",
    )
    assert row.metadata["permission"] == "audit.read"


def test_user_without_roles_has_no_permissions(
    rbac_client: TestClient, make_user: UserFactory
) -> None:
    login(rbac_client, make_user().email)
    assert rbac_client.get("/api/v1/_test/audit").status_code == 403


def test_state_changing_route_needs_csrf_before_permission(
    rbac_client: TestClient, make_user: UserFactory
) -> None:
    state = login(rbac_client, make_user(("admin",)).email)
    assert rbac_client.post("/api/v1/_test/manage").status_code == 403  # csrf
    ok = rbac_client.post(
        "/api/v1/_test/manage", headers={"X-CSRF-Token": str(state["csrf_token"])}
    )
    assert ok.status_code == 200


def test_effective_permissions_are_the_union_of_roles(db: Session, make_user: UserFactory) -> None:
    user = make_user(("viewer", "auditor"))
    assert effective_permissions(db, user.id) == {
        "platform.read",
        "audit.read",
        "accounts.read",
        "ledger.read",
        "holds.read",
    }
    assert effective_permissions(db, make_user(("admin",)).id) == {
        "users.read",
        "users.manage",
        "accounts.read",
        "ledger.read",
        "holds.read",
        "transfers.create",
        "holds.create",
        "holds.release",
        "audit.read",
        "platform.read",
    }


def test_unknown_permission_fails_at_declaration_time() -> None:
    with pytest.raises(ValueError, match="unknown permission"):
        require_permission("audit.raed")
