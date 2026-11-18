# ADR-0008 — PostgreSQL foundation and role boundaries

Status: Accepted for the PR 3 implementation.

The LedgerOps 2.0 blueprint selects PostgreSQL 17, SQLAlchemy 2.x and Alembic. This supersedes the earlier plan's PostgreSQL version assumption.

A one-shot local bootstrap creates distinct login roles. The migrator owns the ledgerops schema and its objects. The runtime role has CONNECT, schema USAGE and default table DML/sequence privileges, with no CREATE or ownership privileges. The Alembic version table is SELECT-only to runtime. PostgreSQL administrator credentials are restricted to the database/bootstrap services.

The runtime engine uses bounded pooling, connection and statement timeouts and pre-ping. Session callers explicitly commit; leaving a session uncommitted rolls back. Readiness checks exact Alembic revision compatibility and connectivity. Liveness remains process-only.

The foundation migration contains no speculative domain tables. Later audit and ledger migrations must override the default DML grants for append-only records and enforce their domain constraints. Runtime DML privileges alone provide no financial integrity guarantees.

Local role bootstrap is idempotent and updates role passwords from the local environment. Existing volume administrator credentials must be retained or explicitly rotated using PostgreSQL administration.
