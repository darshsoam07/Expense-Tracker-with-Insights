# LedgerOps 2.0 — Repository-Grounded Assessment and Implementation Roadmap

**Delivery update, 20 November 2026.** PR 6a merged in GitHub PR #7. PR 7a implements account holds in local review. PR 7b will consume this subsystem. The earlier baseline below is historical. See [ADR 0011](../architecture/adr/0011-account-holds.md).

**Document status:** Living reference — updated after each PR architect review.  
**Last updated:** 2026-11-19 (PR 4b implementation session)  
**Amends:** `docs/product/LEDGEROPS_2.0_BLUEPRINT.md` delivery sequencing; does not override product requirements.

---

## Section 1 — Repository State as of PR 4b

### 1.1 Verified branch state (2026-11-19)

| Milestone | PR / Branch | Notes |
|---|---|---|
| PR 3 | Merged | PostgreSQL 17, Alembic foundation migration, Docker Compose, health endpoints |
| PR 3H | Merged | ADR-0009 amendments, roadmap docs, repo hygiene |
| PR 5 | Merged (GitHub PR #2) | Institutional Luxury website and console, frontend CI job |
| PR 4a | Merged (GitHub PR #5) | Identity, RBAC, sessions, CSRF, and append-only audit trail |
| PR 4b | `feat/pr4b-frontend-auth-integration` | Frontend auth integration, Vite proxy, CORS removal, Windows CI |

> [!IMPORTANT]
> These SHAs and PR statuses are verified against git log and remote branches. Always run `git log --oneline -5 main` before starting implementation work.

### 1.2 Capability map (verified, not assumed)

| Capability | Status | Location |
|---|---|---|
| Legacy Flask + SQLite expense tracker | ✅ Preserved, runnable | `legacy/expense-tracker/` |
| FastAPI health endpoints (`/health/live`, `/health/ready`) | ✅ Implemented | `backend/app/` |
| Alembic migrations (foundation + auth/sessions/audit) | ✅ Implemented | `backend/alembic/` |
| Docker Compose local stack (PostgreSQL 17, backend, frontend) | ✅ Implemented | `docker-compose.yml` |
| Institutional Luxury website and operations console | ✅ Implemented | `frontend/` |
| Authentication (sessions, login, JWT-free cookies, CSRF) | ✅ Implemented | `backend/app/api/auth.py`, `frontend/src/context/AuthContext.tsx` |
| Same-origin Vite proxy (`/api`, `/health`) and CORS removal | ✅ Implemented | `frontend/vite.config.ts`, `backend/app/main.py` |
| Transfer API | ⚠️ HTTP 501 Stub | `backend/app/api/transfers.py` (durable posting planned PR 6a) |
| CI pipeline (GitHub Actions Linux + Windows) | ✅ Implemented | `.github/workflows/ci.yml` |
| Account APIs (create, list, balance) | ❌ Not implemented | Planned PR 6a |
| Double-entry ledger API | ❌ Not implemented | Planned PR 6a |
| Customer / member model | ❌ Not implemented | Planned PR 6b |
| Fund holds | ❌ Not implemented | Planned PR 7a |
| External payments (clearing lifecycle) | ❌ Not implemented | Planned PR 8 |
| Observability (structured logs, metrics, traces) | ❌ Not implemented | Planned Phase 3 |
| Cloud deployment | ❌ Not implemented | Planned Phase 4+ |

---

## Section 2 — Delivery Sequence (Revised)

The revised merge sequence replaces the original Phase 1 "PR 1–5" ordering:

```
PR 3   →  PR 3H  →  PR 5  →  PR 4a  →  PR 4b  →  PR 6a  →  PR 6b  →  PR 7a  →  PR 8  →  …
```

### Why this order

| Step | Rationale |
|---|---|
| PR 3 → PR 3H | Record architectural amendments before implementation resumes. Zero risk. |
| PR 3H → PR 5 | CI gate first. All feature PRs protected from this point forward. |
| PR 5 → PR 4a | Auth layer needs CI to verify session, CSRF, and login tests automatically. |
| PR 4a → PR 4b | Frontend proxy and CORS removal requires auth to exist first; removing CORS breaks the browser-memory demo unless auth replaces it. |
| PR 4b → PR 6a | Accounts and ledger APIs require a working authenticated session to enforce authorization. |
| PR 6a → PR 6b | Corporate customer model builds on the account model. |
| PR 6b → PR 7a | Fund holds require accounts and member-level authorization. |
| PR 7a → PR 8 | External payments require holds infrastructure. |

---

## Section 3 — PR Scope Definitions

### PR 3H — Architecture alignment (this PR)

**Scope:** documentation only, zero runtime changes.

Deliverables:
- `docs/architecture/adr/0009-ledgerops-2-amendments.md` — 14 architectural decisions (see ADR-0009)
- `docs/product/LedgerOps 2.0 Repository-Grounded Assessment and Implementation Roadmap.md` — this file
- `README.md` — status table updated to reflect PR 3 merged, PR 3H active, PR 5 next

Acceptance criteria:
- [ ] ADR-0009 committed and cross-referenced in this roadmap
- [ ] README current-status table accurate
- [ ] No runtime code changed
- [ ] No `.agents/` or `skills-lock.json` changes committed (see Decision 14)

### PR 5 — CI pipeline

**Scope:** GitHub Actions workflows for Linux (PostgreSQL integration) and Windows (lint, unit, frontend build).

Key constraints from ADR-0009:
- Decision 13: Windows job required alongside Linux
- Decision 7: `import-linter` contracts for the ledger service must be introduced here
- PostgreSQL integration tests use real PostgreSQL 17; no SQLite fallback

Deliverables:
- `.github/workflows/ci-linux.yml`
- `.github/workflows/ci-windows.yml`
- `pyproject.toml` import-linter configuration
- Coverage threshold enforcement

### PR 4a — Authentication layer

**Status:** ✅ Merged (GitHub PR #5).

**Scope:** FastAPI session management, login/logout endpoints, CSRF middleware, password hashing, session storage in PostgreSQL (`user_sessions` table per ADR-0005), RBAC, and append-only audit trail.

### PR 4b — Frontend auth integration and Windows CI

**Status:** 🔄 Active (`feat/pr4b-frontend-auth-integration`).

**Scope:** Vite `/api` and `/health` dev proxy, removal of CORS allowance from FastAPI, replace browser-memory transfer simulation with API-backed stub returning HTTP 501, React central API client and auth context, login/logout UI, and Windows CI workflow job.

### PR 6a — Accounts and ledger

**Scope:** `accounts`, `journal_entries`, `account_balances`, `currencies` tables; account CRUD; double-entry posting endpoint; transfer endpoint (internal book transfers only).

Key constraints from ADR-0009:
- Decision 2: `currencies` lookup table, INR seeded, FK constraint on journal entries
- Decision 5: internal `transfers` only (no external rail)
- Decision 6: `available_balance` enforced under row lock (placeholder; holds implemented in PR 7a)
- Decision 7: `account_balances` updated in Python ledger service transaction; `import-linter` enforced
- Decision 8: synchronous SQLAlchemy; no outbox yet (no async workflows)

### PR 6b — Corporate customer model

**Scope:** `customers` and `customer_members` tables; customer CRUD; member role assignment; authorization middleware updated to check member roles.

Key constraints from ADR-0009:
- Decision 4: `customers` + `customer_members` replaces 1:1 `customer_profiles`

### PR 7a — Fund holds

**Scope:** `account_holds` table; hold create/release/apply lifecycle; `available_balance` enforcement under the same row lock as the hold check.

Key constraints from ADR-0009:
- Decision 6: full implementation of available_balance = ledger_balance − active_holds

### PR 8 — External payments

**Scope:** `payments` table; clearing lifecycle state machine; nostro, suspense, FX position system accounts; outbox table and worker for clearing events.

Key constraints from ADR-0009:
- Decision 5: separate from transfers; shares idempotency via `subject_type`
- Decision 8: outbox (`FOR UPDATE SKIP LOCKED`) introduced here (first async workflow)

---

## Section 4 — Schema Evolution Constraints

The following constraints must be respected by all migration authors:

| Rule | Source |
|---|---|
| `currencies` table must be seeded with INR before any currency-aware table is created | Decision 2 |
| `journal_entries` has a FK to `currencies(code)`, not a CHECK constraint | Decision 2 |
| `account_balances` may only be written by the Python ledger service module | Decision 7 |
| `audit_events` are written in the same transaction as the business action | Decision 10 |
| `outbox_events` table is added in PR 8, not speculatively | Decision 8 |
| `customers` / `customer_members` replaces `customer_profiles`; do not create `customer_profiles` | Decision 4 |
| All time columns use `timestamptz`; services use the `Clock` abstraction, not `datetime.now()` | Decision 11 |

---

## Section 5 — Architectural Amendment Summary

> See [ADR-0009](../architecture/adr/0009-ledgerops-2-amendments.md) for the full rationale of each decision. This section is a cross-reference index.

| Decision | Topic | Affects |
|---|---|---|
| 1 | Merge sequence | Delivery planning |
| 2 | Currency model: lookup table, FK | ADR-0004, PR 6a migration |
| 3 | Frontend money as decimal strings | ADR-0004, PR 4b, all API responses |
| 4 | Corporate customer model | Phase 1 Blueprint, PR 6b |
| 5 | Transfers vs. payments separation | ADR-0003, PR 6a, PR 8 |
| 6 | Fund holds and available balance | PR 7a |
| 7 | Balance projection in Python (default) | ADR-0002, `import-linter`, PR 6a |
| 8 | PostgreSQL outbox, no Redis/Kafka | AGENTS.md §5, PR 8 |
| 9 | Rolling deployment readiness range | PR 13 |
| 10 | Transactional audit events | ADR-0007, all feature PRs |
| 11 | Clock abstraction | PR 4a, all time-sensitive services |
| 12 | Same-origin API, Vite proxy | ADR-0001, PR 4b |
| 13 | Cross-platform CI (Windows + Linux) | PR 5, AGENTS.md §7 |
| 14 | Untrack `.agents/`, `skills-lock.json` | Repository hygiene |

---

## Section 6 — Quality Gate Checklist (per PR)

Each PR must pass the following before merge:

### Backend
- [ ] `ruff check .` — zero violations
- [ ] `ruff format --check .` — no formatting changes
- [ ] `mypy --strict backend/` — zero errors
- [ ] `import-linter` — no contract violations (from PR 5 onwards)
- [ ] `pytest` unit tests — all pass
- [ ] PostgreSQL integration tests (Linux CI) — all pass against PostgreSQL 17
- [ ] `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` — clean

### Frontend
- [ ] `tsc --noEmit` — zero type errors
- [ ] `vite build` — clean production build
- [ ] Unit / component tests — all pass
- [ ] No `Intl.NumberFormat` gaps for monetary display

### Containers
- [ ] `docker compose config` — valid
- [ ] `docker compose up --build` — all services healthy
- [ ] `docker compose down` — clean shutdown

### Repository
- [ ] No secrets in diff (token, password, key)
- [ ] No `.agents/` or `skills-lock.json` changes committed
- [ ] No unrelated generated files
- [ ] No accidental legacy-app changes
- [ ] ADR cross-references current

---

## Section 7 — Non-Negotiable Honesty Constraints

The following labels and behaviors are required in the UI and documentation regardless of which PR introduces the feature:

| Item | Required label / behavior |
|---|---|
| In-memory browser transfer simulation | "Demo — resets on reload, not durable" |
| Seeded / synthetic accounts | "Synthetic demo data" badge |
| Hard-coded metrics or telemetry | "Seeded demo telemetry — not live infrastructure" |
| Development Compose stack | Not described as a production deployment |
| Any mock or stub endpoint | Returns `501 Not Implemented` with a `{"detail": "not implemented"}` body, never a fake success |

---

## Section 8 — Open Questions (as of PR 3H)

| # | Question | Owner | Target PR |
|---|---|---|---|
| OQ-1 | Does `feat/postgresql-alembic-compose` contain any work not in `main`? Must reconcile before PR 5. | Engineer | Pre-PR 5 |
| OQ-2 | Approval threshold for transfers: configurable per account type or global? | Product | PR 6a spec |
| OQ-3 | Should `customer_members` support time-bounded roles (start/end date)? | Product | PR 6b spec |
| OQ-4 | FX rate source for cross-currency benchmarks: manual seed or external feed? (No real FX feed without approval.) | Product | PR 9 spec |
| OQ-5 | What is the target hold expiry policy (absolute TTL or relative to approval window)? | Product | PR 7a spec |
| OQ-6 | Rolling deployment readiness range format: semver-style or Alembic revision list? | Engineering | Pre-PR 13 |

---

## Section 9 — Screen-Recording Verification Notes (PR 3 Acceptance)

The following observations were recorded during the PR 3 acceptance screen-recording session:

- **Docker Compose startup:** `docker compose up --build` completes with all three services (`db`, `backend`, `frontend`) reporting healthy. No credential warnings.
- **Readiness endpoint:** `GET http://localhost:8000/health/ready` returns `{"status":"ok","revision":"<head>"}` with HTTP 200 after migrations complete.
- **Liveness endpoint:** `GET http://localhost:8000/health/live` returns `{"status":"ok"}` before the database is ready (process-only check confirmed).
- **Frontend shell:** Vite dev server at `http://localhost:5173` renders the LedgerOps shell. The API readiness indicator polls and transitions from "connecting" to "connected" once the backend is healthy.
- **In-browser transfer demo:** Initiating a transfer between the two hard-coded sample accounts updates the displayed balance in the browser. Refreshing the page resets all balances, confirming the simulation is browser-memory only (no durable state).
- **Alembic migration:** `alembic upgrade head` from inside the backend container applies the foundation migration cleanly. `alembic downgrade -1` reverts it. `alembic upgrade head` re-applies. No errors.
- **Role separation:** Connecting to PostgreSQL as the runtime role and attempting `CREATE TABLE` returns `ERROR: permission denied` — role boundary is enforced.
- **Legacy app:** `python app.py` from `legacy/expense-tracker/` starts the Flask app on port 4949. Login, add expense, and delete expense flows work. No change to legacy behavior.

> [!NOTE]
> These observations were made against the commit recorded in Section 1.1. Re-verify after any schema or Compose change.

---

## References

- [ADR-0009: LedgerOps 2.0 amendments](../architecture/adr/0009-ledgerops-2-amendments.md)
- [LedgerOps 2.0 Blueprint](LEDGEROPS_2.0_BLUEPRINT.md)
- [PR 3 database foundation](../architecture/pr3-database-foundation.md)
- [ADR-0001: Cookie sessions with CSRF](../architecture/adr/0001-cookie-sessions-with-csrf.md)
- [ADR-0002: Ledger source of truth and balance projection](../architecture/adr/0002-ledger-source-of-truth-and-balance-projection.md)
- [ADR-0003: System and settlement accounts](../architecture/adr/0003-system-settlement-accounts.md)
- [ADR-0004: Money representation](../architecture/adr/0004-money-representation.md)
- [ADR-0008: PostgreSQL foundation](../architecture/adr/0008-postgresql-foundation.md)
- [AGENTS.md](../../AGENTS.md)
