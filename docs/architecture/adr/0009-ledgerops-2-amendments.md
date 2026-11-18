# ADR-0009: LedgerOps 2.0 Domain & Delivery Amendments (PR 3H)

- **Status:** Accepted
- **Date:** 2026-11-18
- **Amends:** ADR-0001, ADR-0002, ADR-0003, ADR-0004, Phase 1 Blueprint

## Context

PR 3H is a documentation and architecture-alignment PR that follows the successful merge of PR 3 (PostgreSQL foundation). During the architect review session that produced the PR 3H scope, fourteen cross-cutting decisions were resolved that amend or extend earlier ADRs and the Phase 1 blueprint. This record codifies those decisions so that all subsequent PRs (PR 5, PR 4a, PR 4b, PR 6a, PR 6b, PR 7a, …) can reference a single source of truth rather than relying on session transcripts.

The decisions below are numbered for reference in PR descriptions, commit messages, and issue comments. They do not change the Phase 1 database schema; they constrain how later migrations and features must be implemented.

---

## Decisions

### Decision 1 — Merge sequence

**Merge order is `PR 3 → PR 3H → PR 5 → PR 4a → PR 4b`.**

Rationale: PR 3 landed the PostgreSQL/Alembic/Compose foundation. PR 3H records the architectural amendments before implementation work resumes. PR 5 adds the CI gate (GitHub Actions lint, type-check, unit and integration tests) so that all subsequent feature PRs are protected. PR 4a then implements the authentication layer (sessions, login, JWT-free cookie model per ADR-0001). PR 4b integrates the frontend with the API proxy and removes the in-process CORS allowance.

This sequence prevents the React shell from drifting further without a CI gate and avoids merging auth before the test infrastructure exists.

### Decision 2 — Currency model

**Replace `CHECK (currency = 'INR')` with a `currencies` lookup table** seeded with a single active row: `code = 'INR'`, `locale = 'en-IN'`, `minor_units = 2`, `active = true`.

Multi-currency support is enabled in PR 9. Until then, the application layer enforces that all new journal entries reference an active currency code from the lookup table (a foreign-key constraint, not a hard-coded literal). This eliminates the need to change a CHECK constraint when a second currency is added.

Cross-currency conversions post as two balanced entry pairs through a dedicated FX position account; the FX spread posts to a revenue account. Each journal entry remains single-currency.

Amends: ADR-0004 (money representation).

### Decision 3 — Frontend money contract

**Monetary amounts cross the API boundary as decimal strings** (e.g. `"12345.67"`), not integers or floats.

The browser formats values using `Intl.NumberFormat` with the locale supplied by the currency record. The browser **never** performs balance arithmetic; all balance calculations occur in the Python ledger service with `decimal.Decimal`. This prevents floating-point rounding errors from appearing in the UI.

Amends: ADR-0004 (money representation).

### Decision 4 — Corporate customer model

**Replace the 1:1 `customer_profiles` table (`user_id UNIQUE`) with `customers` and `customer_members` tables** in PR 6b.

`customers` represents a legal entity (individual or corporate). `customer_members` maps one or more `users` to a customer with a named role (e.g. `owner`, `operator`, `viewer`). This supports corporate operators, shared accounts for entities, and delegated access patterns without retrofitting a 1:1 model.

The PR 3H schema preview (if any) must not create a `customer_profiles` table with `user_id UNIQUE`; that shape is explicitly superseded.

Amends: Phase 1 Blueprint (customer model section).

### Decision 5 — Transfers vs. payments

**Separate internal book `transfers` from external rail `payments`.**

- **Transfers** (PR 6a): immediate, same-currency book entries between two accounts. Idempotency is enforced by a server-generated idempotency key stored in the database. Approval workflows apply to transfers above a threshold.
- **Payments** (PR 8): external rail operations with a clearing and settlement lifecycle (initiated → clearing → settled / failed / returned). Payments use nostro accounts, suspense accounts, and FX position accounts as system counterparties.

Both share idempotency and approval infrastructure via a polymorphic `subject_type` column in the approvals and idempotency tables. This extends ADR-0003 with four additional system account types: `clearing`, `nostro`, `suspense`, and `fx_position`.

Amends: ADR-0003 (system/settlement accounts).

### Decision 6 — Fund holds

**Add `account_holds` in PR 7a** and enforce:

```
available_balance = ledger_balance - SUM(active_holds)
```

under the **same `SELECT … FOR UPDATE` row lock** that protects the account balance row. This prevents concurrent pending approvals from overdrawing accounts.

The hold lifecycle is: `pending → released | applied`. A hold is applied when the corresponding debit entry posts; it is released on timeout, rejection, or cancellation. Holds that exceed the available balance must be rejected at creation time, not at posting time.

### Decision 7 — Balance projection ownership (default)

**Keep `account_balances` updates inside the single Python append-only ledger service transaction** (as established in ADR-0002) as the **default and required** implementation path.

Rationale: a single transaction boundary guarantees that the projected balance is never visible without the corresponding ledger entries, and it allows the Python service to enforce all business rules (hold deduction, balance floor, single-currency constraint) before committing. `import-linter` contracts must prevent any module outside the ledger service from writing to `account_balances` directly. Reconciliation routines run on a schedule to detect and alert on any drift.

A PostgreSQL `AFTER INSERT` trigger on `journal_entries` is evaluated strictly as an **optional concurrency benchmark** in PR 6a. If benchmarked, it must be implemented on a separate branch and must not be merged unless it demonstrably reduces lock contention at load levels the application is expected to reach. The trigger must not replace the Python-layer update; it must be an alternative path under a feature flag.

Amends: ADR-0002 (ledger source of truth and balance projection).

### Decision 8 — Database-backed async execution

**Retain synchronous SQLAlchemy with `psycopg` 3 and use a PostgreSQL outbox (`FOR UPDATE SKIP LOCKED`) for deferred or background work** instead of introducing Redis, Kafka, or Celery.

An `outbox_events` table is added when the first asynchronous workflow is implemented (PR 8 or later). A lightweight poll-based worker using a plain Python loop and `asyncio.sleep` reads the outbox under `SKIP LOCKED` to avoid cross-worker contention. This satisfies at-least-once delivery without an external message broker.

Redis and Kafka must not be added until a specific throughput or fan-out requirement is documented and approved.

Amends: AGENTS.md §5 (scope and delivery discipline — no Redis/Kafka without documented need).

### Decision 9 — Rolling deployment readiness

**Evolve `/health/ready` from exact Alembic revision equality to an expand/contract compatible migration range by PR 13.**

PR 3 implemented exact revision matching. This is correct for single-instance deployments but blocks rolling restarts when two application versions run concurrently during a deploy. By PR 13, readiness will check that the current revision falls within a declared compatible range (`[min_revision, head]`) maintained in `backend/app/db/migrations/compat.py`.

No change is required before PR 13; this decision records the intent so that migration authors from PR 4 onwards do not write migrations that break the expand/contract pattern.

### Decision 10 — Transactional audit semantics

**Write `audit_events` in the same database transaction as the business action.**

If the audit insertion fails, the transaction rolls back and the business action does not commit. This provides a hard guarantee that every committed business action has a corresponding audit record. Audit events must never be written in a separate transaction after the business action commits.

Background and system-initiated actions (e.g. outbox worker, reconciliation) are attributed to a named system principal (e.g. `system:outbox-worker`, `system:reconciliation`) stored in the `actor_id` column of `audit_events`. Human actor identity comes from the authenticated session.

Amends: ADR-0007 (backend foundation conventions — audit trail).

### Decision 11 — Deterministic time

**Inject a `Clock` abstraction into all services** that evaluate cut-off times, approval windows, hold expiry, settlement deadlines, or rate-limit windows.

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
    def today(self) -> date: ...
```

Production services receive `SystemClock`. Tests inject `FakeClock`. No service may call `datetime.utcnow()`, `datetime.now()`, or `time.time()` directly; all calls are routed through the injected clock. This makes time-sensitive logic deterministic in tests without monkeypatching.

### Decision 12 — Same-origin API access

**Route frontend API requests through a Vite `/api` proxy in PR 4b** and remove the local CORS `allow_origins` allowance from the FastAPI application.

This change is prerequisite for cookie-based sessions (ADR-0001): same-origin requests carry session cookies automatically; cross-origin requests require `credentials: 'include'` and liberal CORS, which is incompatible with the `SameSite=Strict` cookie policy.

PR 4a may keep a temporary CORS allowance for local development. PR 4b removes it. The production deployment (PR 10 or later) uses a reverse proxy (nginx or ALB) that serves both origins on the same domain.

Amends: ADR-0001 (cookie sessions with CSRF).

### Decision 13 — Cross-platform CI

**Run a Windows CI job alongside Linux PostgreSQL integration jobs.**

The Windows job runs: Ruff lint, mypy strict type-check, frontend TypeScript build, and unit tests (no live PostgreSQL). The Linux job runs: the full test matrix including PostgreSQL 17 integration tests, Alembic upgrade/downgrade/upgrade, and container health checks. Both jobs are required to pass before merge.

This ensures that Windows developer environments are validated in CI and not silently broken by Linux-only assumptions.

Amends: AGENTS.md §7 (quality gates — Windows support).

### Decision 14 — Repository hygiene

**Untrack `.agents/` and `skills-lock.json`** while keeping `AGENTS.md` in version control.

The `.agents/` directory and `skills-lock.json` are tooling artifacts generated by the Antigravity agent environment. They are not application source code, are not needed for reproducible builds, and add significant noise to diffs. Add both paths to `.gitignore` and remove them from tracking with `git rm --cached -r .agents/ skills-lock.json`. `AGENTS.md` remains committed as the authoritative engineering instruction file for all agent sessions.

---

## Consequences

- All PRs from PR 5 onwards must reference the relevant decision number in their description when their scope overlaps one of these decisions.
- `import-linter` contracts (Decision 7) must be in place before the first ledger service implementation PR merges.
- The `currencies` lookup table (Decision 2) must be seeded in the first migration that introduces currency-aware tables.
- The `Clock` abstraction (Decision 11) must be in the backend foundation before any service with time-sensitive logic is implemented.
- The outbox table (Decision 8) is added lazily, not speculatively; it must not be added until the first consumer is implemented.

## References

- [ADR-0001: Cookie sessions with CSRF](0001-cookie-sessions-with-csrf.md)
- [ADR-0002: Ledger source of truth and balance projection](0002-ledger-source-of-truth-and-balance-projection.md)
- [ADR-0003: System and settlement accounts](0003-system-settlement-accounts.md)
- [ADR-0004: Money representation](0004-money-representation.md)
- [ADR-0007: Backend foundation conventions](0007-backend-foundation-conventions.md)
- [ADR-0008: PostgreSQL foundation](0008-postgresql-foundation.md)
- [LedgerOps 2.0 Blueprint](../../product/LEDGEROPS_2.0_BLUEPRINT.md)
- [PR 3 database foundation](../pr3-database-foundation.md)
