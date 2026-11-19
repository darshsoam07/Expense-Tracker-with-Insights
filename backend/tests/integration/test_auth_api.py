"""Login, logout, session lifetime, revocation and CSRF, through the real HTTP stack."""

import hashlib
from datetime import timedelta
from uuid import uuid4

import httpx2
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.security import hash_session_token
from app.db.tables import audit_events, sessions, users
from app.main import create_app
from tests.helpers import FakeClock, make_settings
from tests.integration.conftest import _RUNTIME_URL, PASSWORD, TestUser, UserFactory, login

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/me"
LOGOUT = "/api/v1/auth/logout"
CSRF = "/api/v1/auth/csrf"


def _audit(engine: Engine, request_id: str) -> list[tuple[str, str, str, str | None]]:
    with Session(engine) as db:
        rows = db.execute(
            select(
                audit_events.c.action,
                audit_events.c.outcome,
                audit_events.c.actor_principal,
                audit_events.c.reason,
            ).where(audit_events.c.request_id == request_id)
        )
        return [tuple(r) for r in rows]


def _anon_login(api: TestClient, email: str, password: str) -> httpx2.Response:
    token = api.get(CSRF).json()["csrf_token"]
    return api.post(
        LOGIN, json={"email": email, "password": password}, headers={"X-CSRF-Token": token}
    )


def test_login_me_logout_flow_sets_safe_cookies_and_audits(
    api: TestClient, make_user: UserFactory, runtime_engine: Engine
) -> None:
    user: TestUser = make_user(("viewer",))
    token = api.get(CSRF).json()["csrf_token"]
    response = api.post(
        LOGIN,
        json={"email": user.email.upper(), "password": PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == user.email
    assert body["user"]["roles"] == ["viewer"]
    assert body["user"]["permissions"] == ["platform.read"]
    cookie = response.headers["set-cookie"].lower()
    for attribute in ("httponly", "samesite=lax", "path=/"):
        assert attribute in cookie
    assert response.headers["cache-control"] == "no-store"
    assert _audit(runtime_engine, response.headers["x-request-id"]) == [
        ("auth.login", "success", f"user:{user.id}", None)
    ]

    me = api.get(ME)
    assert me.status_code == 200
    assert me.json()["csrf_token"] == body["csrf_token"]

    out = api.post(LOGOUT, headers={"X-CSRF-Token": body["csrf_token"]})
    assert out.status_code == 204
    assert api.get(ME).status_code == 401
    assert ("auth.logout", "success", f"user:{user.id}", None) in _audit(
        runtime_engine, out.headers["x-request-id"]
    )


def test_session_token_is_stored_only_as_a_hash(
    api: TestClient, make_user: UserFactory, db: Session
) -> None:
    user = make_user()
    login(api, user.email)
    raw = api.cookies["ledgerops_session"]
    row = db.execute(select(sessions).where(sessions.c.user_id == user.id)).one()
    assert bytes(row.token_hash) == hashlib.sha256(raw.encode()).digest()
    assert raw not in (row.csrf_token, row.token_hash.hex())


def test_wrong_password_and_unknown_user_are_indistinguishable(
    api: TestClient, make_user: UserFactory, runtime_engine: Engine
) -> None:
    user = make_user()
    wrong = _anon_login(api, user.email, "not the password")
    unknown = _anon_login(api, f"nobody-{uuid4().hex[:8]}@example.test", "whatever password")
    assert wrong.status_code == unknown.status_code == 401
    wb, ub = wrong.json(), unknown.json()
    assert wb["error"]["code"] == ub["error"]["code"] == "invalid_credentials"
    assert wb["error"]["message"] == ub["error"]["message"]
    wa = _audit(runtime_engine, wrong.headers["x-request-id"])
    ua = _audit(runtime_engine, unknown.headers["x-request-id"])
    assert wa == [("auth.login", "failure", f"user:{user.id}", "wrong_password")]
    assert ua == [("auth.login", "failure", "anonymous", "unknown_user")]


def test_lockout_after_repeated_failures_then_recovers(
    api: TestClient, make_user: UserFactory, clock: FakeClock, runtime_engine: Engine
) -> None:
    user = make_user()
    for _ in range(5):
        assert _anon_login(api, user.email, "bad password!!").status_code == 401
    locked = _anon_login(api, user.email, PASSWORD)
    assert locked.status_code == 401
    assert _audit(runtime_engine, locked.headers["x-request-id"])[0][3] == "account_locked"
    clock.advance(timedelta(minutes=16))
    assert _anon_login(api, user.email, PASSWORD).status_code == 200


def test_disabled_account_cannot_log_in(
    api: TestClient, make_user: UserFactory, runtime_engine: Engine
) -> None:
    user = make_user(status="disabled")
    response = _anon_login(api, user.email, PASSWORD)
    assert response.status_code == 401
    assert _audit(runtime_engine, response.headers["x-request-id"])[0][3] == "account_disabled"


def test_idle_timeout_expires_the_session(
    api: TestClient, make_user: UserFactory, clock: FakeClock
) -> None:
    login(api, make_user().email)
    clock.advance(timedelta(minutes=29))
    assert api.get(ME).status_code == 200
    clock.advance(timedelta(minutes=31))
    assert api.get(ME).status_code == 401


def test_absolute_lifetime_ends_an_active_session(
    api: TestClient, make_user: UserFactory, clock: FakeClock
) -> None:
    login(api, make_user().email)
    for _ in range(23):  # 7h40m of steady activity stays valid
        clock.advance(timedelta(minutes=20))
        assert api.get(ME).status_code == 200
    clock.advance(timedelta(minutes=30))  # now past 8 hours
    assert api.get(ME).status_code == 401


def test_revoked_session_and_disabled_user_are_rejected(
    api: TestClient, make_user: UserFactory, db: Session, clock: FakeClock
) -> None:
    user = make_user()
    login(api, user.email)
    db.execute(update(sessions).where(sessions.c.user_id == user.id).values(revoked_at=clock.now()))
    db.commit()
    assert api.get(ME).status_code == 401

    other = make_user()
    login(api, other.email)
    db.execute(update(users).where(users.c.id == other.id).values(status="disabled"))
    db.commit()
    assert api.get(ME).status_code == 401


def test_login_replaces_an_existing_session(
    api: TestClient, make_user: UserFactory, db: Session
) -> None:
    user = make_user()
    first = login(api, user.email)
    old_token = api.cookies["ledgerops_session"]
    second = api.post(
        LOGIN,
        json={"email": user.email, "password": PASSWORD},
        headers={"X-CSRF-Token": str(first["csrf_token"])},
    )
    assert second.status_code == 200
    assert api.cookies["ledgerops_session"] != old_token
    old = db.execute(
        select(sessions.c.revoked_at).where(sessions.c.token_hash == hash_session_token(old_token))
    ).scalar_one()
    assert old is not None


def test_csrf_is_required_for_login_and_logout(
    api: TestClient, make_user: UserFactory, runtime_engine: Engine
) -> None:
    user = make_user()
    payload = {"email": user.email, "password": PASSWORD}
    assert api.post(LOGIN, json=payload).status_code == 403
    api.get(CSRF)
    assert api.post(LOGIN, json=payload, headers={"X-CSRF-Token": "forged"}).status_code == 403
    state = login(api, user.email)
    assert api.post(LOGOUT).status_code == 403
    bad = api.post(LOGOUT, headers={"X-CSRF-Token": "forged"})
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "csrf_failed"
    assert ("auth.csrf.failed", "denied", f"user:{user.id}", None) in _audit(
        runtime_engine, bad.headers["x-request-id"]
    )
    assert api.post(LOGOUT, headers={"X-CSRF-Token": str(state["csrf_token"])}).status_code == 204


def test_anonymous_csrf_token_expires(
    api: TestClient, make_user: UserFactory, clock: FakeClock
) -> None:
    user = make_user()
    token = api.get(CSRF).json()["csrf_token"]
    clock.advance(timedelta(hours=2))
    response = api.post(
        LOGIN, json={"email": user.email, "password": PASSWORD}, headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 403


def test_foreign_origin_is_rejected_even_with_a_valid_token(
    api: TestClient, make_user: UserFactory
) -> None:
    user = make_user()
    token = api.get(CSRF).json()["csrf_token"]
    response = api.post(
        LOGIN,
        json={"email": user.email, "password": PASSWORD},
        headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_secure_mode_uses_host_prefixed_cookies(make_user: UserFactory, clock: FakeClock) -> None:
    assert _RUNTIME_URL
    app = create_app(make_settings(database_url=_RUNTIME_URL, cookie_secure=True), clock=clock)
    user = make_user()
    with TestClient(app, base_url="https://testserver") as client:
        token = client.get(CSRF).json()["csrf_token"]
        assert "__host-ledgerops_csrf" in client.cookies.jar.__repr__().lower()
        response = client.post(
            LOGIN, json={"email": user.email, "password": PASSWORD}, headers={"X-CSRF-Token": token}
        )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("__host-ledgerops_session=")
    for attribute in ("secure", "httponly", "path=/"):
        assert attribute in cookie
    assert "domain" not in cookie


def test_unauthenticated_me_is_401_and_health_still_works(api: TestClient) -> None:
    assert api.get(ME).status_code == 401
    assert api.get("/health/live").status_code == 200
