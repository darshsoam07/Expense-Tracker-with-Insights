"""Alembic environment using separate migration credentials."""

from alembic import context

from app.db import make_engine, migration_url

engine = make_engine(migration_url())
with engine.connect() as connection:
    context.configure(
        connection=connection,
        version_table_schema="ledgerops",
        transactional_ddl=True,
    )
    with context.begin_transaction():
        connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS ledgerops")
        context.run_migrations()
engine.dispose()
