# PR 3 database foundation

The branch reconciles PR 3 with main at 5637e29. The frontend and legacy application remain present. PostgreSQL 17 is authoritative for future persistence. This migration creates the application schema and version marker only. Identity, ledger and financial tables arrive with their corresponding roadmap implementations.

## Local setup on Windows

From the repository root in PowerShell:

~~~powershell
python scripts/init_compose.py
docker compose config --quiet
docker compose up --build -d --wait
~~~

The initializer refuses to overwrite an existing root .env. Preserve the current credentials when restarting an existing volume. Changing POSTGRES_PASSWORD does not rotate a database already initialized on disk. Bootstrap updates runtime/migration role passwords using the configured administrator credentials.

Open http://localhost:5173 and http://localhost:8000/health/ready.
The latter requires database connectivity and the exact supported Alembic revision.
Liveness at /health/live is independent of PostgreSQL.

Compose exposes only API and frontend ports on loopback. PostgreSQL stays on the Compose network. The administrator URL is supplied only to bootstrap, migration credentials only to the migration service, and runtime credentials only to the API. The API runs as UID 10001. PostgreSQL storage uses a named volume.

## Verification and rollback

The following integration command uses a real PostgreSQL 17 database and changes the foundation revision. Run it only on a disposable local or CI database, with the API stopped:

~~~powershell
docker compose stop backend
$probePath = (Resolve-Path backend/tests/verify_postgres.py).Path
docker compose run --rm --no-deps --volume "${probePath}:/app/verify_postgres.py:ro" bootstrap python verify_postgres.py
docker compose start backend
~~~

It checks upgrade/downgrade/upgrade, supported schema readiness, committed and rolled-back transactions, and denied runtime DDL/version changes.

To roll the foundation back, stop the API and run:

~~~powershell
docker compose run --rm --no-deps migrate alembic downgrade base
~~~

Downgrade revokes runtime access and removes the version row while retaining the empty schema. Reapply with the migration service's alembic upgrade head command. Future data-bearing migrations require their own rollback procedures.

~~~powershell
docker compose down
~~~

Shutdown preserves the database volume. The application currently has no persisted banking features. Browser transfers remain synthetic, in-memory demonstrations.

## Remaining roadmap

PR 4 introduces identity, sessions, CSRF, RBAC and audit integration. PR 5 applies the approved Institutional Luxury design. PR 6 implements durable accounts, financial posting and idempotency.
