"""Fixtures for tests that need the PostgreSQL 17 test database.

Provide two environment variables (a disposable database that is already migrated to head):

    TEST_DATABASE_URL            postgresql+psycopg://ledgerops_runtime:...@host:port/ledgerops
    TEST_MIGRATION_DATABASE_URL  postgresql+psycopg://ledgerops_migrator:...@host:port/ledgerops

Without them these tests are skipped locally. CI sets REQUIRE_DATABASE_TESTS=1 so a missing
database fails the build instead of silently skipping the tests.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import database_ready, make_engine
from app.db.tables import roles, user_roles, users
from app.main import create_app
from app.modules.finance.provision import provision
from app.modules.finance.queries import accounts
from tests.helpers import FakeClock, make_settings

PASSWORD = "correct horse battery staple"
_RUNTIME_URL = os.environ.get("TEST_DATABASE_URL")
_MIGRATION_URL = os.environ.get("TEST_MIGRATION_DATABASE_URL")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in str(item.path):
            item.add_marker(pytest.mark.integration)


def _require_database() -> None:
    if _RUNTIME_URL and _MIGRATION_URL:
        return
    if os.environ.get("REQUIRE_DATABASE_TESTS") == "1":
        pytest.fail(
            "REQUIRE_DATABASE_TESTS=1 but TEST_DATABASE_URL/TEST_MIGRATION_DATABASE_URL unset"
        )
    pytest.skip("PostgreSQL test database not configured")


@pytest.fixture(scope="session")
def runtime_engine() -> Iterator[Engine]:
    _require_database()
    assert _RUNTIME_URL
    engine = make_engine(_RUNTIME_URL)
    assert database_ready(engine), "test database is not migrated to the supported revision"
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrator_engine() -> Iterator[Engine]:
    _require_database()
    assert _MIGRATION_URL
    engine = make_engine(_MIGRATION_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def password_hash() -> str:
    """Hash once per run: Argon2 is deliberately slow."""
    return hash_password(PASSWORD)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def db(runtime_engine: Engine) -> Iterator[Session]:
    with Session(runtime_engine) as session:
        yield session


@dataclass(frozen=True)
class TestUser:
    __test__ = False  # not a pytest test class

    id: UUID
    email: str


class UserFactory(Protocol):
    def __call__(self, role_codes: tuple[str, ...] = (), status: str = "active") -> TestUser: ...


@pytest.fixture
def make_user(db: Session, clock: FakeClock, password_hash: str) -> UserFactory:
    def factory(role_codes: tuple[str, ...] = (), status: str = "active") -> TestUser:
        email = f"user-{uuid4().hex[:12]}@example.test"
        now = clock.now()
        user_id = db.execute(
            insert(users)
            .values(
                email=email,
                display_name="Test User",
                password_hash=password_hash,
                status=status,
                created_at=now,
                updated_at=now,
            )
            .returning(users.c.id)
        ).scalar_one()
        for code in role_codes:
            role_id = db.execute(select(roles.c.id).where(roles.c.code == code)).scalar_one()
            db.execute(
                insert(user_roles).values(
                    user_id=user_id, role_id=role_id, granted_at=now, granted_by="system:test"
                )
            )
        db.commit()
        return TestUser(user_id, email)

    return factory


@pytest.fixture
def api_app(clock: FakeClock) -> FastAPI:
    assert _RUNTIME_URL
    settings = make_settings(database_url=_RUNTIME_URL)
    return create_app(settings, clock=clock)


@pytest.fixture
def api(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app, raise_server_exceptions=False) as client:
        yield client


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, object]:
    """Run the real browser flow: anonymous CSRF first, then the login POST."""
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


@dataclass
class Workspace:
    actor: UUID
    email: str
    src: UUID
    dst: UUID


@pytest.fixture
def workspace(make_user: UserFactory, migrator_engine: Engine) -> Workspace:
    user = make_user(("operator",))
    with Session(migrator_engine) as db, db.begin():
        provision(db, user.id)
        provision(db, user.id)
        rows = sorted(
            accounts(db, user.id), key=lambda a: Decimal(str(a["ledger_balance"])), reverse=True
        )
        assert [r["available_balance"] for r in rows] == ["1000.00", "0.00"]
        return Workspace(user.id, user.email, UUID(str(rows[0]["id"])), UUID(str(rows[1]["id"])))
