"""Run in the bootstrap container against a disposable local/CI PostgreSQL database.

Migration round trips are destructive to the foundation revision. Stop the API first.
"""

import os
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import database_ready, make_engine

runtime = make_engine(
    "postgresql+psycopg://ledgerops_runtime:"
    + os.environ["RUNTIME_PASSWORD"]
    + "@database/ledgerops"
)
url = (
    "postgresql+psycopg://ledgerops_migrator:"
    + os.environ["MIGRATION_PASSWORD"]
    + "@database/ledgerops"
)
migration = make_engine(url)
environment = dict(os.environ, MIGRATION_DATABASE_URL=url)
for target in ("head", "base", "head"):
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade" if target == "head" else "downgrade", target],
        env=environment,
        check=True,
    )
    if target == "head":
        assert database_ready(runtime)
    else:
        with migration.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM ledgerops.alembic_version")
                ).scalar_one()
                == 0
            )
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
    with migration.begin() as connection:
        connection.execute(text("UPDATE ledgerops.alembic_version SET version_num = 'wrong'"))
    assert not database_ready(runtime)
finally:
    with migration.begin() as connection:
        connection.execute(text("DROP TABLE ledgerops.integration_probe"))
        connection.execute(
            text("UPDATE ledgerops.alembic_version SET version_num = '0001_foundation'")
        )
    runtime.dispose()
    migration.dispose()
print("PostgreSQL migration, permissions, transaction rollback and schema readiness checks passed")
