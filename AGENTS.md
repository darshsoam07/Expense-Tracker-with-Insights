# Codex Repository Instructions — LedgerOps

> **Read this file and `docs/product/LEDGEROPS_2.0_BLUEPRINT.md` before making changes.**  
> These documents define the product direction and engineering constraints. Treat the blueprint as an approved specification, not loose inspiration.

## 1. Mission and product identity

LedgerOps is a **simulated cloud-native banking and financial-operations platform** built to demonstrate financial correctness, operational controls, security engineering, SRE practices, and cloud-native delivery.

The product is intended to feel like a premium enterprise fintech operations platform, not a basic expense tracker or a static portfolio landing page.

The platform has two distinct experiences:

1. **Public product website** — communicates the product, capabilities, architecture, reliability approach, and demo access.
2. **Banking operations console** — the working application for customer accounts, transfers, ledger inspection, operations workflows, governance, and platform health.

### Non-negotiable honesty statement

- Use synthetic customers and simulated funds only.
- Do not connect to real banking rails, payment providers, or real customer accounts.
- Do not claim regulatory approval, production-banking readiness, compliance certification, or real-money settlement.
- Label demo/synthetic data clearly in the UI and documentation.
- Never display invented operational metrics as if they came from live infrastructure. Clearly label seeded/demo telemetry.

## 2. Source-of-truth hierarchy

When making a decision, use this order:

1. The user's latest explicit instruction in the active task.
2. `docs/product/LEDGEROPS_2.0_BLUEPRINT.md` for approved product requirements and visual direction.
3. This `AGENTS.md` for repository-level engineering rules and workflow constraints.
4. Existing code, tests, ADRs, and migration records as evidence of the current implementation.
5. Your own assumptions only where the documents and code do not decide the issue. Record those assumptions; do not silently change the specification.

If the blueprint conflicts with existing code, **do not silently bend the blueprint to match the code**. First inspect the code, identify the mismatch, preserve existing behavior that must remain, and implement the smallest safe change that moves the repository toward the blueprint. Explain any unavoidable deviation in the PR notes.

## 3. Repository context and current reality

Repository: `darshsoam07/Expense-Tracker-with-Insights`  
Product name: `LedgerOps`  
Primary stack: React + TypeScript + Vite + Tailwind CSS; FastAPI + Python; PostgreSQL; SQLAlchemy 2.x; Alembic; Docker Compose; GitHub Actions.

### Verified state snapshot (2026-11-17)

- `main` was observed at commit `5637e29` (`Add LedgerOps frontend and local Compose stack`). Re-check live refs before every implementation task; this SHA is a historical snapshot, not a permanent branch pointer.
- `feat/postgresql-alembic-compose` was observed at `0d6e7ab`, with zero commits ahead of `main` and one commit behind it. It must be reconciled with current `main` before PR 3 implementation continues. Do not overwrite or discard the frontend/design-system commit on `main`.
- PR 1 and PR 2 were previously completed and accepted. Preserve their work.
- The legacy Flask + SQLite tracker is retained under `legacy/expense-tracker/`. Do not rewrite, delete, or reformat that historical application unless explicitly requested.
- The current React frontend is an early preview. It has a single-page hero, two hard-coded sample accounts, browser-memory transfer simulation, architecture cards, a transaction journal, and an API readiness indicator.
- The current browser simulator is **not** a backend-backed banking system. Do not describe its in-memory transfers, balances, or idempotency as durable or authoritative.
- The FastAPI backend currently provides the PR 2 foundation and health endpoints. Authentication, sessions, account APIs, transfers, ledger APIs, settlement APIs, and operational workflows are not yet implemented unless verified in the current code.
- The existing `design-system/ledgerops/MASTER.md` and `tokens.css` describe an earlier dark navy/green design. The approved new visual direction is in the product blueprint and supersedes those visual tokens for the LedgerOps 2.0 redesign. Update both the design-system docs and actual CSS tokens together when implementing the redesign.
- A recent commit introduced a very large `.agents/skills/` collection. Treat those as local agent/tooling references, not application product functionality. Do not add more third-party skill corpora or bulk-copy unrelated files into the application.

**Always re-inspect the live repository and git refs.** This snapshot can become stale. Do not assume that a previous chat summary describes the latest commit tree.

## 4. Engineering principles

- Prefer a **modular monolith** for the initial platform. Keep clear domain boundaries inside FastAPI. Do not create microservices simply to make an architecture diagram look sophisticated.
- Use PostgreSQL as the authoritative persistence layer for financial and operational data. No SQLite fallback for database-dependent tests.
- Use SQLAlchemy 2.x and Alembic for persistence and schema evolution.
- Store money in exact numeric/minor-unit representations. Never use binary floating-point for financial calculations.
- Financial posting must be atomic and enforce double-entry balance. A transfer must never partially post.
- Posted ledger records are immutable. Correct mistakes with reversal entries and explicit audit events, not edits to historical postings.
- Idempotency must be enforced server-side and in the database, not with an in-memory JavaScript `Set`.
- Enforce authorization on the backend. Hiding a button in React is not an authorization control.
- Sensitive operator actions need actor identity, request/correlation ID, timestamp, action, target, and reason in the audit trail.
- Use explicit transaction boundaries and concurrency control. Write tests for duplicate submissions, concurrent posting, rollback, invalid transitions, and permission failures.
- Use structured logs and correlation/request IDs. Never log passwords, tokens, secrets, full payment credentials, or unnecessary personal information.
- Keep Docker containers non-root, use health checks, and avoid embedding secrets in images or committed files.
- Keep the API and frontend contracts explicit and typed. Use generated/shared schemas only when they reduce drift without coupling unrelated layers.

## 5. Scope and delivery discipline

The product roadmap is defined in `docs/product/LEDGEROPS_2.0_BLUEPRINT.md`.

- Implement one coherent PR-sized scope at a time.
- Do not combine the database foundation, authentication, entire banking domain, UI redesign, observability, and cloud deployment into one mega-change.
- Do not start a later phase while a prerequisite is incomplete or unverified.
- Do not change `main` directly. Use a feature branch and PR.
- Keep PRs reviewable: clear commits, focused diffs, tests, docs, migration/rollback notes, and acceptance checklist.
- Preserve PR 1/PR 2 behavior and the legacy application.
- Avoid speculative dependencies. Add a library only when a concrete requirement needs it.
- Do not introduce Redis, Kafka, Kubernetes, Celery, or additional services until a specific use case and operational need are documented. A worker and transactional outbox may be added when the relevant asynchronous workflows are implemented.
- Do not provision AWS resources or incur cloud costs without explicit approval. Local Docker Compose and CI are the default development/test environment.

## 6. Codex execution protocol

At the start of a task:

1. Read this file and `docs/product/LEDGEROPS_2.0_BLUEPRINT.md` completely.
2. Inspect `git status`, current branch, `main`, recent commits, repository tree, and relevant PRs. Never assume branch SHAs from prior chat sessions are still current.
3. Inspect the actual implementation and tests for every file you intend to change.
4. Compare current behavior with the blueprint. Separate **implemented**, **partially implemented**, **mock/demo-only**, and **not implemented** capabilities.
5. Identify dependencies and acceptance criteria before editing.
6. Implement only the active PR scope. Preserve unrelated changes and user work.
7. Add or update tests with the implementation. Update user-facing docs and ADRs when a decision changes.
8. Run the relevant checks and report exact commands and actual results. Never claim a test, build, container, migration, or Windows workflow passed unless it was run and its output was inspected.
9. Review the final diff for accidental scope expansion, secrets, generated files, broken links, and mismatched docs.
10. Report changed files, behavior, verification, remaining gaps, and exact next step.

### When the specification is clear

Do not ask the user to repeat decisions already recorded here. Follow the specification as written. If an ambiguity blocks safe implementation, choose the least surprising reversible option, document it, and ask only if the choice has material product/security/data consequences.

### No pretend completion

- A page with mock data is not an implemented backend feature.
- A button that only triggers a toast is not a completed workflow.
- A chart with hard-coded values is not observability.
- A schema table without tested business logic is not a banking capability.
- A health endpoint is not full monitoring.
- A local Compose file is not a cloud deployment.

Mark demo/placeholder functionality visibly and keep it separate from implemented functionality.

## 7. Quality gates

Run the project-specific checks documented in the backend and frontend READMEs. At minimum, when the corresponding code is touched:

- Backend: Ruff lint/format, strict mypy, import-linter, pytest, coverage threshold, PostgreSQL integration tests, Alembic upgrade/downgrade/upgrade.
- Frontend: TypeScript typecheck, production build, unit/component tests, responsive checks, accessibility checks.
- Containers: Docker Compose config validation, image build, service health checks, clean startup, and shutdown.
- Repository: secret scan/diff review, no unrelated generated files, no accidental legacy changes.

PostgreSQL integration tests must use real PostgreSQL (PostgreSQL 17 is the project target); they must not silently switch to SQLite or mocks for database behavior.

Windows is a supported developer environment. Include PowerShell commands and avoid Bash-only setup assumptions. Linux CI does not prove Windows compatibility; state that limitation and provide Windows verification steps when needed.

## 8. Required response format for implementation tasks

At completion, report:

1. **Scope completed** — what is genuinely implemented.
2. **Files changed** — grouped by backend, frontend, infrastructure, docs/tests.
3. **Behavior** — user-visible and API behavior, including limitations.
4. **Verification** — exact commands and pass/fail status; distinguish local and CI results.
5. **Known gaps/risks** — anything not verified or deliberately deferred.
6. **Next step** — one concrete next PR/task.

Do not claim production readiness. LedgerOps is a portfolio-grade simulated platform unless the owner explicitly changes that scope and funds the necessary security, operational, legal, and compliance work.
