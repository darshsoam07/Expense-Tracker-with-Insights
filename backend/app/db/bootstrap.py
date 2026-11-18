"""Local Compose bootstrap. Credentials are supplied through the environment."""

import os

import psycopg
from psycopg import sql


def main() -> None:
    with psycopg.connect(os.environ["ADMIN_DATABASE_URL"], autocommit=True) as connection:
        for role, variable in (
            ("ledgerops_migrator", "MIGRATION_PASSWORD"),
            ("ledgerops_runtime", "RUNTIME_PASSWORD"),
        ):
            exists = connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            ).fetchone()
            if not exists:
                connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            connection.execute(
                sql.SQL(
                    "ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(os.environ[variable]))
            )
        connection.execute("REVOKE ALL ON DATABASE ledgerops FROM PUBLIC")
        connection.execute("GRANT CONNECT, CREATE ON DATABASE ledgerops TO ledgerops_migrator")
        connection.execute("GRANT CONNECT ON DATABASE ledgerops TO ledgerops_runtime")
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")


if __name__ == "__main__":
    main()
