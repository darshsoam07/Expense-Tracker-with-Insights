"""Schema facts for migration 0002 against a real PostgreSQL 17 database."""

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.tables import metadata
from app.modules.auth.policy import ROLE_PERMISSIONS
from app.modules.auth.rbac import rbac_drift

APPEND_ONLY = "audit_events is append-only"
INSERT_AUDIT = (
    "INSERT INTO ledgerops.audit_events (occurred_at, actor_principal, action, outcome) "
    "VALUES (now(), 'system:test', 'test.probe', 'success')"
)


def test_core_definitions_match_the_migrated_database(migrator_engine: Engine) -> None:
    inspector = inspect(migrator_engine)
    assert set(inspector.get_table_names(schema="ledgerops")) == {
        table.name for table in metadata.tables.values()
    } | {"alembic_version"}
    for table in metadata.tables.values():
        actual = {c["name"]: c["nullable"] for c in inspector.get_columns(table.name, "ledgerops")}
        expected = {c.name: c.nullable for c in table.columns}
        assert actual == expected, table.name


def _insert_probe_row(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(INSERT_AUDIT))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledgerops.audit_events SET reason = 'tampered'",
        "DELETE FROM ledgerops.audit_events",
        "TRUNCATE ledgerops.audit_events",
    ],
)
def test_owner_cannot_change_audit_rows(migrator_engine: Engine, statement: str) -> None:
    """Even the table owner is stopped by the trigger. A row exists first, so this is real."""
    _insert_probe_row(migrator_engine)
    with pytest.raises(DBAPIError, match=APPEND_ONLY), migrator_engine.begin() as connection:
        connection.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledgerops.audit_events SET reason = 'x' WHERE false",
        "DELETE FROM ledgerops.audit_events WHERE false",
    ],
)
def test_statements_matching_no_rows_are_still_rejected(
    migrator_engine: Engine, statement: str
) -> None:
    with pytest.raises(DBAPIError, match=APPEND_ONLY), migrator_engine.begin() as connection:
        connection.execute(text(statement))


def test_runtime_role_cannot_change_audit_rows(runtime_engine: Engine) -> None:
    _insert_probe_row(runtime_engine)
    for statement in (
        "UPDATE ledgerops.audit_events SET reason = 'x'",
        "DELETE FROM ledgerops.audit_events",
        "TRUNCATE ledgerops.audit_events",
    ):
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            connection.execute(text(statement))


def test_runtime_privileges_on_protected_tables(runtime_engine: Engine) -> None:
    def has(table: str, privilege: str) -> bool:
        with runtime_engine.connect() as connection:
            return bool(
                connection.execute(
                    text("SELECT has_table_privilege(current_user, :t, :p)"),
                    {"t": f"ledgerops.{table}", "p": privilege},
                ).scalar_one()
            )

    assert has("audit_events", "INSERT")
    assert has("audit_events", "SELECT")
    for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
        assert not has("audit_events", privilege)
    for table in ("roles", "permissions", "role_permissions"):
        assert has(table, "SELECT")
        for privilege in ("INSERT", "UPDATE", "DELETE"):
            assert not has(table, privilege), (table, privilege)
    assert not has("users", "DELETE")
    assert has("users", "UPDATE")
    assert has("sessions", "UPDATE")


def test_runtime_cannot_grant_itself_a_permission(runtime_engine: Engine) -> None:
    with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
        connection.execute(text("INSERT INTO ledgerops.role_permissions VALUES (1, 1)"))


@pytest.mark.parametrize(
    "statement",
    [
        # a null or mismatched actor is rejected
        "INSERT INTO ledgerops.audit_events (occurred_at, actor_principal, action, outcome) "
        "VALUES (now(), 'user:abc', 'test.probe', 'success')",
        "INSERT INTO ledgerops.audit_events (occurred_at, actor_principal, action, outcome) "
        "VALUES (now(), 'somebody', 'test.probe', 'success')",
        "INSERT INTO ledgerops.audit_events (occurred_at, actor_principal, action, outcome) "
        "VALUES (now(), 'system:test', 'NotAnAction', 'success')",
        "INSERT INTO ledgerops.audit_events (occurred_at, actor_principal, action, outcome) "
        "VALUES (now(), 'system:test', 'test.probe', 'maybe')",
        "INSERT INTO ledgerops.users (email, display_name, password_hash, created_at, updated_at) "
        "VALUES ('Upper@Example.test', 'x', 'h', now(), now())",
        "INSERT INTO ledgerops.users (email, display_name, password_hash, status, created_at, "
        "updated_at) VALUES ('ok@example.test', 'x', 'h', 'banned', now(), now())",
    ],
)
def test_check_constraints_reject_bad_rows(runtime_engine: Engine, statement: str) -> None:
    with pytest.raises(IntegrityError), runtime_engine.begin() as connection:
        connection.execute(text(statement))


def test_seeded_rbac_matches_policy_constants(db: Session) -> None:
    assert rbac_drift(db) == []
    assert {role.value for role in ROLE_PERMISSIONS} == {
        "admin",
        "operator",
        "approver",
        "auditor",
        "viewer",
    }
