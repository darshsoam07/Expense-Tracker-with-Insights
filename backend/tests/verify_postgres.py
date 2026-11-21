"""Run in the bootstrap container against a disposable local/CI PostgreSQL database.

Migration round trips are destructive (they drop and recreate the identity tables).
Stop the API first.
"""

import os
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import SCHEMA_REVISION, database_ready, make_engine

# "database" is the Compose service name; override it to run against another host:port.
ADDRESS = os.environ.get("VERIFY_DB_ADDRESS", "database")

runtime = make_engine(
    "postgresql+psycopg://ledgerops_runtime:"
    + os.environ["RUNTIME_PASSWORD"]
    + f"@{ADDRESS}/ledgerops"
)
url = (
    "postgresql+psycopg://ledgerops_migrator:"
    + os.environ["MIGRATION_PASSWORD"]
    + f"@{ADDRESS}/ledgerops"
)
migration = make_engine(url)
environment = dict(os.environ, MIGRATION_DATABASE_URL=url)


def alembic(*arguments: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *arguments], env=environment, check=True)


def revision() -> list[str]:
    with migration.connect() as connection:
        return list(
            connection.execute(text("SELECT version_num FROM ledgerops.alembic_version")).scalars()
        )


def tables() -> set[str]:
    with migration.connect() as connection:
        return set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'ledgerops'")
            ).scalars()
        )


IDENTITY_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "sessions",
    "audit_events",
}
# upgrade head -> downgrade -1 -> upgrade head (PR 4a requirement), then the full base round trip.
alembic("upgrade", "head")
assert database_ready(runtime)
assert tables() >= IDENTITY_TABLES | {"account_holds", "hold_events"}
assert {
    "approval_policies",
    "approval_requests",
    "approval_decisions",
    "approval_events",
} <= tables()
assert {"payment_instructions", "payment_events"} <= tables()
assert "reconciliation_results" in tables()
alembic("downgrade", "-1")
assert revision() == ["0008_platform_nostro"]
assert "settlement_items" in tables()
alembic("downgrade", "-1")
assert revision() == ["0007_payment_instructions"]
assert "settlement_items" not in tables()
alembic("downgrade", "-1")
assert revision() == ["0006_approval_grants"]
assert "payment_instructions" not in tables()
alembic("downgrade", "-1")
assert revision() == ["0005_transfer_approvals"]
alembic("downgrade", "-1")
assert revision() == ["0004_account_holds"]
assert "approval_requests" not in tables()
alembic("downgrade", "-1")
assert revision() == ["0003_financial_integrity"]
assert "hold_events" not in tables()
alembic("downgrade", "-1")
assert revision() == ["0002_identity_rbac_audit"]
assert tables() >= IDENTITY_TABLES
assert "journal_entries" not in tables()
alembic("downgrade", "-1")
assert revision() == ["0001_foundation"]
assert not IDENTITY_TABLES & tables()
alembic("upgrade", "head")
assert database_ready(runtime)
assert tables() >= IDENTITY_TABLES
alembic("downgrade", "base")
assert revision() == []
alembic("upgrade", "head")
assert database_ready(runtime)
with migration.begin() as connection:
    assert int(connection.execute(text("SHOW server_version_num")).scalar_one()) // 10000 == 17
    connection.execute(text("CREATE TABLE ledgerops.integration_probe (value integer NOT NULL)"))
try:
    with Session(runtime) as session:
        session.execute(text("INSERT INTO ledgerops.integration_probe VALUES (1)"))
        session.rollback()
        assert session.scalar(text("SELECT count(*) FROM ledgerops.integration_probe")) == 0
        session.execute(text("INSERT INTO ledgerops.integration_probe VALUES (2)"))
        session.commit()
        assert session.scalar(text("SELECT sum(value) FROM ledgerops.integration_probe")) == 2
    for statement in (
        "CREATE TABLE ledgerops.forbidden (value integer)",
        "CREATE SCHEMA forbidden",
        "DELETE FROM ledgerops.alembic_version",
        "ALTER TABLE ledgerops.integration_probe ADD COLUMN forbidden integer",
    ):
        try:
            with runtime.begin() as connection:
                connection.execute(text(statement))
        except DBAPIError:
            pass
        else:
            raise AssertionError("runtime permission unexpectedly granted")
    # Audit rows are append-only: insert one, then prove UPDATE and DELETE fail for both roles.
    with runtime.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ledgerops.audit_events (occurred_at, actor_principal, action, outcome)"
                " VALUES (now(), 'system:verify', 'verify.probe', 'success')"
            )
        )
    for engine in (runtime, migration):
        for statement in (
            "UPDATE ledgerops.audit_events SET reason = 'tampered'",
            "DELETE FROM ledgerops.audit_events",
        ):
            try:
                with engine.begin() as connection:
                    connection.execute(text(statement))
            except DBAPIError as error:
                reason = str(error.orig).splitlines()[0]
                print(f"blocked as expected ({engine.url.username}): {reason}")
            else:
                raise AssertionError(f"audit row was changed by: {statement}")
    with migration.begin() as connection:
        connection.execute(text("UPDATE ledgerops.alembic_version SET version_num = 'wrong'"))
    assert not database_ready(runtime)
finally:
    with migration.begin() as connection:
        connection.execute(text("DROP TABLE ledgerops.integration_probe"))
        connection.execute(
            text("UPDATE ledgerops.alembic_version SET version_num = :revision"),
            {"revision": SCHEMA_REVISION},
        )
    runtime.dispose()
    migration.dispose()
print("PostgreSQL migration, permissions, transaction rollback and schema readiness checks passed")
