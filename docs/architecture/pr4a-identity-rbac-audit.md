# PR 4a: identity, sessions, RBAC and the audit trail (backend only)

Migration `0002_identity_rbac_audit` and the services that use it. No frontend change, no
registration endpoint, no password reset, no MFA. The local CORS rule stays until PR 4b.

## What exists

| Area | Where |
|---|---|
| Tables: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `sessions`, `audit_events` | `backend/migrations/versions/0002_identity_rbac_audit.py` |
| Core table definitions (drift-tested against the migrated database) | `app/db/tables.py` |
| `Clock` protocol and `SystemClock` | `app/core/clock.py` |
| Argon2id, token hashing, CSRF helpers | `app/core/security.py` |
| Principals (`user:<id>`, `system:<name>`, `anonymous`) | `app/core/principal.py` |
| Transactional audit writer | `app/modules/audit/service.py` |
| Login, logout, sessions, RBAC, first-admin CLI | `app/modules/auth/` |
| Routes and dependencies | `app/api/auth.py`, `app/api/deps.py` |

Endpoints: `GET /api/v1/auth/csrf`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout` and
`GET /api/v1/me` (the canonical current-user path in ADR-0001 and the Phase 1 plan).

## Behaviour worth knowing

- **Audit is append-only twice over.** A statement-level trigger rejects UPDATE, DELETE and
  TRUNCATE (even when no rows match, and even for the table owner), and the runtime role has
  those privileges revoked. A test inserts a row first, because a trigger test on an empty
  table proves nothing.
- **Audit shares the business transaction.** `AuditWriter.record()` only inserts on the
  caller's session. If it raises, the caller never commits. Failed logins are the exception that
  proves the rule: recording the failed attempt *is* the action, so it commits on its own.
- **No null actors.** Every row has `user:<uuid>`, `system:<name>` or `anonymous`
  (unauthenticated requests such as a failed login for an unknown address).
- **CSRF is global.** `enforce_csrf` is an application-level dependency, so a future
  state-changing route cannot forget it. Before login a signed double-submit pair is used;
  afterwards the per-session token. A foreign `Origin` is rejected as defence in depth.
  Authenticated CSRF failures and permission denials are audited. Anonymous CSRF failures are
  only logged, so unauthenticated traffic cannot flood the audit table.
- **Login never reveals why it failed.** Unknown user, wrong password, disabled and locked
  accounts return the same 401; the audit row records the real reason. Five failures lock the
  account for 15 minutes (configurable).
- **Sessions.** Only the SHA-256 of the token is stored. Idle timeout 30 minutes, absolute
  lifetime 8 hours, both measured with the injected clock. Logging in again revokes the
  session presented with the request.
- **RBAC.** `require_permission("audit.read")` validates the code at import time. Roles and
  permissions are read-only for the runtime role, so a compromised application cannot grant
  itself rights. The seed lives in the migration (frozen); `rbac_drift()` and a test compare it
  with `app/modules/auth/policy.py`.
- **First admin.** `python -m app.modules.auth.bootstrap --email ... --name ... --role admin`
  with the password in `LEDGEROPS_BOOTSTRAP_PASSWORD` (or prompted). Audited as
  `system:bootstrap-cli`.

## Contract alignment (ADR-0001, ADR-0009, Phase 1 plan)

1. **Current user is `GET /api/v1/me`**, as ADR-0001 (steps 6 and 7) and the Phase 1 route table
   and authorization matrix specify. There is no `/api/v1/auth/me`.
2. **`SameSite=Lax`**, as ADR-0001 specifies. ADR-0009 decision 12 said `Strict`; that was a
   slip, now corrected in place with a note. No decision to use Strict was made.
3. **Both cookies use `Path=/`.** The `__Host-` prefix, required whenever `COOKIE_SECURE` is true,
   is only accepted by browsers with `Path=/`, so the narrower `Path=/api/v1/auth` in the earlier
   ADR-0001 text cannot work. ADR-0001 carries the correction and the reasoning.
4. **Roles.** The Phase 1 plan named `customer`, `operations` and `admin`. PR 4a seeds `admin`,
   `operator`, `approver`, `auditor` and `viewer`, as requested. `operator` corresponds to
   `operations`. `customer` and `GET /api/v1/customers/me` arrive with the customer model
   (PR 6b). Registration and `GET /api/v1/ops/ping` are not part of PR 4a; the role-gate
   behaviour they would show is covered by tests that mount a probe route.

## Role and permission mapping (explicit, least privilege)

Every grant is listed; nothing is inherited. A permission added later reaches no role until a
migration and `policy.py` both grant it.

| Role | Permissions |
|---|---|
| admin | `users.read`, `users.manage`, `audit.read`, `platform.read` |
| operator | `platform.read` |
| approver | `platform.read` |
| auditor | `audit.read`, `platform.read` |
| viewer | `platform.read` |

`platform.read` (service health, non-sensitive) is the baseline. User administration is
admin-only. Operator and approver gain working permissions with the features that need them:
transfers (PR 6) and approvals (PR 7a). The auditor reads the audit trail; the audit API in PR 4b
will include actor display details, so it needs no `users.read`.

## Other deviations

- `sessions` has two extra columns, `id` and `last_seen_at`, for the idle timeout.
- Only four permissions exist; permissions arrive with their features, through a migration.
- Import-linter gained layers `modules` and `db`, so the contract reads
  `main -> api -> modules -> db -> core`, plus two forbidden-import contracts.
- Adds `argon2-cffi` (pinned, with its bindings, in `constraints.txt`).

## Verifying locally

    # PostgreSQL 17 with the roles from app.db.bootstrap, migrated to head
    $env:TEST_DATABASE_URL = "postgresql+psycopg://ledgerops_runtime:...@localhost:5432/ledgerops"
    $env:TEST_MIGRATION_DATABASE_URL = "postgresql+psycopg://ledgerops_migrator:...@localhost:5432/ledgerops"
    $env:REQUIRE_DATABASE_TESTS = "1"
    pytest

Without those variables the integration tests are skipped and coverage falls below the gate.
The Compose job in CI also runs `tests/verify_postgres.py`: upgrade, `downgrade -1`, upgrade, a
full base round trip, privilege checks and the audit-immutability checks.
