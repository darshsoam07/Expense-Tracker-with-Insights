"""The audit writer shares the caller's transaction (ADR-0009, decision 10)."""

from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.principal import ANONYMOUS, Principal
from app.db.tables import audit_events, users
from app.modules.audit import AuditWriter
from tests.helpers import FakeClock


def _count_users(engine: Engine, email: str) -> int:
    with Session(engine) as session:
        return (
            session.scalar(select(func.count()).select_from(users).where(users.c.email == email))
            or 0
        )


def _insert_user(db: Session, email: str, clock: FakeClock) -> None:
    now = clock.now()
    db.execute(
        insert(users).values(
            email=email, display_name="T", password_hash="h", created_at=now, updated_at=now
        )
    )


def test_business_change_and_audit_row_commit_together(
    runtime_engine: Engine, db: Session, clock: FakeClock
) -> None:
    email = f"{uuid4().hex[:10]}@example.test"
    request_id = uuid4().hex
    _insert_user(db, email, clock)
    AuditWriter(clock).record(
        db,
        principal=Principal.system("unit-test"),
        action="users.created",
        target_type="user",
        target_id=email,
        request_id=request_id,
        metadata={"k": "v"},
    )
    db.commit()
    assert _count_users(runtime_engine, email) == 1
    with Session(runtime_engine) as check:
        row = check.execute(
            select(audit_events).where(audit_events.c.request_id == request_id)
        ).one()
    assert row.actor_principal == "system:unit-test"
    assert row.actor_user_id is None
    assert row.occurred_at == clock.now()
    assert row.metadata == {"k": "v"}


def test_failed_audit_insert_rolls_back_the_business_change(
    runtime_engine: Engine, db: Session, clock: FakeClock
) -> None:
    """The principal points at a user that does not exist, so the audit INSERT fails."""
    email = f"{uuid4().hex[:10]}@example.test"
    _insert_user(db, email, clock)
    ghost = Principal.user(uuid4())
    with pytest.raises(IntegrityError):
        AuditWriter(clock).record(db, principal=ghost, action="users.created")
    db.rollback()  # what any caller does when the audit write raises: nothing is committed
    assert _count_users(runtime_engine, email) == 0


def test_invalid_action_is_rejected_before_any_write(db: Session, clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="audit action"):
        AuditWriter(clock).record(db, principal=ANONYMOUS, action="Bad Action")


def test_anonymous_and_system_principals_are_never_null(
    runtime_engine: Engine, db: Session, clock: FakeClock
) -> None:
    request_id = uuid4().hex
    writer = AuditWriter(clock)
    writer.record(
        db, principal=ANONYMOUS, action="auth.login", outcome="failure", request_id=request_id
    )
    writer.record(
        db, principal=Principal.system("outbox-worker"), action="outbox.run", request_id=request_id
    )
    db.commit()
    with Session(runtime_engine) as check:
        principals = set(
            check.scalars(
                select(audit_events.c.actor_principal).where(
                    audit_events.c.request_id == request_id
                )
            )
        )
    assert principals == {"anonymous", "system:outbox-worker"}


def test_system_principal_names_are_validated() -> None:
    with pytest.raises(ValueError, match="system principal"):
        Principal.system("Not Valid")
