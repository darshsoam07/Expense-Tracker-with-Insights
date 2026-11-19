from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.tables import audit_events, user_roles, users
from app.modules.auth.bootstrap import BOOTSTRAP_PRINCIPAL, create_user
from tests.helpers import FakeClock


def test_create_user_hashes_password_assigns_roles_and_audits(
    db: Session, runtime_engine: Engine, clock: FakeClock
) -> None:
    email = f"boot-{uuid4().hex[:8]}@Example.test"
    user_id = create_user(
        db,
        clock,
        email=email,
        display_name=" Ada ",
        password="a long enough password",
        role_codes=["admin", "auditor"],
    )
    with Session(runtime_engine) as check:
        row = check.execute(select(users).where(users.c.id == user_id)).one()
        assert row.email == email.lower()
        assert row.display_name == "Ada"
        assert row.password_hash.startswith("$argon2id$")
        assert (
            check.scalar(
                select(func.count()).select_from(user_roles).where(user_roles.c.user_id == user_id)
            )
            == 2
        )
        actions = sorted(
            check.scalars(
                select(audit_events.c.action).where(audit_events.c.target_id == str(user_id))
            )
        )
        principals = set(
            check.scalars(
                select(audit_events.c.actor_principal).where(
                    audit_events.c.target_id == str(user_id)
                )
            )
        )
    assert actions == ["users.created", "users.role_granted", "users.role_granted"]
    assert principals == {BOOTSTRAP_PRINCIPAL.value} == {"system:bootstrap-cli"}


def test_rejects_weak_password_unknown_role_and_duplicates(
    db: Session, runtime_engine: Engine, clock: FakeClock
) -> None:
    email = f"boot-{uuid4().hex[:8]}@example.test"
    with pytest.raises(AppError, match="Password"):
        create_user(
            db, clock, email=email, display_name="A", password="short", role_codes=["admin"]
        )
    with pytest.raises(AppError, match="Unknown role"):
        create_user(
            db,
            clock,
            email=email,
            display_name="A",
            password="a long enough password",
            role_codes=["root"],
        )
    with Session(runtime_engine) as check:
        assert (
            check.scalar(select(func.count()).select_from(users).where(users.c.email == email)) == 0
        )
    create_user(
        db,
        clock,
        email=email,
        display_name="A",
        password="a long enough password",
        role_codes=["viewer"],
    )
    with pytest.raises(AppError) as error:
        create_user(
            db,
            clock,
            email=email,
            display_name="B",
            password="a long enough password",
            role_codes=["viewer"],
        )
    assert error.value.code == "email_in_use"
