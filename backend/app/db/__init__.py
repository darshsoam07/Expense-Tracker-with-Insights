"""PostgreSQL connections and schema readiness."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

SCHEMA_REVISION = "0008_platform_nostro"


def make_engine(url: str) -> Engine:
    """Create a bounded PostgreSQL pool without connecting during configuration."""
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("DATABASE_URL must use postgresql+psycopg")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )


def database_ready(engine: Engine) -> bool:
    """Require connectivity and exactly the schema revision supported by this binary."""
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM ledgerops.alembic_version")
        ).scalars().all() == [SCHEMA_REVISION]


def sessions(engine: Engine) -> Iterator[Session]:
    """Callers explicitly commit their unit of work. Uncommitted work rolls back."""
    with Session(engine) as session:
        yield session


def migration_url() -> str:
    """Read migration credentials separately from the runtime application."""
    return os.environ["MIGRATION_DATABASE_URL"]


@contextmanager
def open_session(engine: Engine) -> Iterator[Session]:
    """Context-manager form of `sessions` for code that is not a FastAPI dependency."""
    with Session(engine) as session:
        yield session
