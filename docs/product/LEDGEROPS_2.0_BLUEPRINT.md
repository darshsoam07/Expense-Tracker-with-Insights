# LedgerOps 2.0 â€” Product, Experience, and Engineering Blueprint

**Status:** Approved product direction for implementation planning  
**Product:** LedgerOps  
**Repository:** `darshsoam07/Expense-Tracker-with-Insights`  
**Status:** Approved product direction for implementation planning
**Product:** LedgerOps
**Repository:** `darshsoam07/Expense-Tracker-with-Insights`
**Last specification update:** 17 November 2026

This document is the implementation specification for the LedgerOps 2.0 product direction. It is deliberately separate from `AGENTS.md`: that file tells Codex how to work in the repository; this file defines **what LedgerOps should become**.

---

## 1. Product vision

### Positioning

**LedgerOps is a premium cloud-native banking operations and reliability platform.** It brings together financial integrity, controlled financial operations, auditability, and infrastructure reliability in one coherent application.

Suggested product line:

> **Financial integrity. Operational control. Infrastructure reliability.**

Suggested supporting statement:

> A cloud-native banking operations environment for managing simulated accounts, transfers, ledger activity, approvals, reconciliation, and service health.

### Product goals

1. Demonstrate a correct financial core, not just a visually convincing finance dashboard.
2. Demonstrate real operational workflows: review, approve, investigate, reconcile, and audit.
3. Demonstrate SRE practices through measurable service health, traces, logs, SLOs, and incident workflows.
4. Demonstrate secure engineering through backend authorization, session security, append-only audit records, and least-privilege database roles.
5. Demonstrate cloud-native delivery through containers, repeatable CI/CD, infrastructure as code, and a realistic AWS deployment path.
6. Present the entire product through a cohesive, modern, premium enterprise-fintech interface.

### Product honesty and boundaries

- This is a simulated/educational platform using synthetic customers and simulated funds.
- It does not move real money or connect to actual banking rails.
- It is not a licensed bank, payment institution, or certified core banking system.
- UI data must be labelled as `Demo`, `Sandbox`, or `Synthetic` where appropriate.
- Any seeded service metrics must be identified as demo telemetry until backed by real instrumentation.

---

## 2. Product experiences and information architecture

LedgerOps has two connected experiences. Do not make the entire product a single scrolling dashboard.

### 2.1 Public product website

Purpose: communicate the product and its engineering credibility, then guide a visitor to the sandbox/demo console.

Required sections:

1. **Navigation:** LedgerOps identity, Platform, Operations, Reliability, Architecture, Documentation, Launch Demo.
2. **Hero:** concise product promise, short supporting copy, primary `Explore the Console` CTA, secondary `View Architecture` CTA, and a carefully designed dashboard/product preview.
3. **Capability overview:** Banking Core, Financial Operations, Governance, Reliability Engineering.
4. **Operational workflow:** a visual path such as Initiate â†’ Validate â†’ Approve â†’ Post â†’ Reconcile â†’ Audit.
5. **Cloud-native architecture:** React frontend, FastAPI application, PostgreSQL, worker/outbox where implemented, telemetry, CI/CD, and cloud deployment path. Visually distinguish deployed components from planned components.
6. **Reliability/security:** explain actual safeguards and tested properties only. Do not claim certifications.
7. **Engineering notes / architecture decisions:** link to ADRs and technical documentation.
8. **Footer:** project scope disclaimer, repository, docs, and demo access.

This is a product website, not a long generic marketing template. Use strong hierarchy, concise copy, real diagrams, and real application screenshots.

### 2.2 Banking operations console

Use a persistent application shell with a collapsible sidebar, top utility bar, page title/breadcrumb, page content, contextual actions, and a responsive mobile navigation pattern.

| Group | Navigation item | Purpose |
|---|---|---|
| Workspace | Overview | Financial and operational situation at a glance |
| Workspace | Accounts | Browse and manage simulated customer accounts |
| Workspace | Payments & Transfers | Initiate and track transfers |
| Workspace | Ledger Explorer | Inspect journal entries and postings |
| Operations | Review & Approvals | Maker-checker review and approval queue |
| Operations | Exceptions Queue | Investigate failed, rejected, or suspicious workflow events |
| Operations | Settlements | Monitor settlement batches and their lifecycle |
| Operations | Reconciliation | Compare expected and recorded totals; investigate breaks |
| Governance | Audit Trail | Search append-only history of sensitive actions |
| Platform | Service Health | API/database/worker health and SRE signals |
| Platform | Infrastructure | Deployment, environment, database, and component status |
| Administration | Users & Access | Users, roles, and permission administration |
| Administration | Settings | Workspace and environment settings |

Navigation and actions must be role-aware. Do not show an action to a user without the corresponding permission, but always enforce authorization again on the backend.

### 2.3 Recommended console layout

Desktop:

- Left sidebar: approximately 248px expanded, compact icon rail when collapsed.
- Top bar: workspace/environment badge, global search entry point, notifications, help, user menu.
- Main content: generous page gutters, readable maximum width, consistent grid.
- Use cards for high-level summaries; use dense data tables for operational work.
- Avoid excessive rounded cards and decorative charts. Financial data needs clarity and scanning speed.

Mobile:

- Sidebar becomes a drawer or bottom navigation for the most important destinations.
- Tables become horizontally scrollable or purpose-built stacked rows; never clip essential transaction values.
- Critical actions remain reachable and clearly labelled.

---

## 3. Visual identity and design system

### 3.1 Design direction

**Institutional Luxury** â€” a restrained combination of private-banking refinement and modern enterprise operations software.

Desired qualities:

- Premium, mature, calm, precise, credible, and editorial.
- Warm neutral canvas contrasted with deep forest-green navigation.
- Restrained champagne accent for premium details, not as a dominant CTA color.
- Clear data density and excellent typographic hierarchy.
- Purposeful whitespace, hairline borders, subtle elevation, and controlled motion.

Avoid:

- Neon green, excessive glow, heavy gradients, or cyberpunk styling.
- Generic template dashboards with identical KPI cards repeated across every page.
- Excessive glassmorphism, giant empty hero areas, decorative data visualizations, or meaningless animations.
- Emoji in place of interface icons.
- Inconsistent light/dark surfaces. The primary console direction is a warm light workspace with a dark forest sidebar. Dark monitoring surfaces may be used selectively when they improve data legibility, but must remain part of the same design system.

### 3.2 Core color tokens

Use these as the base design tokens. Add semantic variations only where a component needs them; do not introduce competing accent palettes.

| Role | Token suggestion | Hex | Usage |
|---|---|---:|---|
| Main canvas | `--lo-canvas` | `#F3F1EB` | Main application background |
| Sidebar / deep surface | `--lo-forest` | `#111B18` | Primary navigation and dark panels |
| Primary brand action | `--lo-emerald` | `#244F43` | Main CTA, active navigation, key emphasis |
| Premium accent | `--lo-champagne` | `#B89A6A` | Small details, active markers, premium accents |
| Card | `--lo-card` | `#FFFFFF` | Main content cards and panels |
| Border | `--lo-border` | `#E6E1D7` | Dividers and outlines |
| Main text | `--lo-text` | `#18211D` | Body and heading text |
| Muted text | `--lo-muted` | `#747D76` | Secondary labels and supporting text |
| Success | `--lo-success` | `#34775C` | Completed/success state |
| Warning | `--lo-warning` | `#B77B36` | Needs attention/pending state |
| Critical | `--lo-critical` | `#B84F4B` | Failed/critical state |

Do not use champagne for long text or small text on a white background. Maintain WCAG AA contrast for normal text and visible focus states.

### 3.3 Typography

- Primary family: **Manrope** for UI, body, and headings.
- Data/technical family: **IBM Plex Mono** for transaction IDs, account references, request IDs, timestamps, and tabular numeric metadata.
- Use tabular numerals for balances and monetary values.
- Headings should be confident and editorial, not oversized everywhere.
- Avoid mixing more than two font families.

### 3.4 Layout, shape, motion

- Use an 8px spacing rhythm with documented tokens.
- Cards: generally 14â€“18px radius; buttons and inputs can be tighter.
- Borders are subtle and should define structure without outlining every nested element.
- Shadows are restrained and reserved for overlays, floating menus, and modals.
- Hover/focus/pressed transitions: approximately 160â€“220ms, ease-out.
- Respect `prefers-reduced-motion`.
- All interactive controls require visible focus, keyboard support, descriptive labels, and appropriate hit areas.

### 3.5 Shared component system

Build reusable, tested components rather than styling every page independently:

- `AppShell`, `Sidebar`, `Topbar`, `Breadcrumbs`, `PageHeader`.
- `Button` variants: primary, secondary, ghost, destructive.
- `StatusBadge` with explicit semantic state mapping.
- `MetricCard` with label, value, context/source timestamp, and optional sparkline only when data exists.
- `DataTable` with sort, filter, pagination, empty/loading/error states, and responsive handling.
- `FilterBar`, `DateRangePicker`, `SearchInput`.
- `AmountDisplay` with currency, sign, precision, and tabular numerals.
- `ActivityTimeline`, `AuditEventRow`, `ApprovalPanel`, `ExceptionPanel`.
- `ChartPanel` with accessible labels, legend, and truthful data provenance.
- `ConfirmDialog`, `Drawer`, `Toast`, `Skeleton`, `EmptyState`, `ErrorState`.

Use the existing React + TypeScript + Vite + Tailwind stack unless a specific technical limitation is demonstrated. Do not replace the stack just for stylistic preference.

---

## 4. Product capability specification

The following capabilities define the product target. Their implementation state must always be verified against code and tests. A roadmap item is not an implemented feature.

### 4.1 Banking core

#### Accounts

- Create and view synthetic customer accounts.
- Support account reference, owner/customer, currency, account type, lifecycle status, created date, and available/current balance projections.
- Enforce account ownership/tenant scope on every read and mutation.
- Support account lifecycle states with validated transitions (for example active, restricted, frozen, closed).
- Do not allow direct balance mutation. Balances are derived from the ledger/projection rules.

#### Double-entry ledger

- Journal entries contain one or more postings; every posted journal entry must balance (total debits equal total credits).
- Store exact money values; no floating-point calculations.
- Distinguish debit/credit direction and ledger account identity.
- Posted entries are immutable.
- Corrections occur through explicit reversal journal entries linked to the original entry.
- Validate account currency and ledger-account mapping.
- Include database constraints and transactional tests, not only Python validation.
- Provide a ledger explorer that lets an operator inspect a journal entry and all associated postings.

#### Transfers

- Model a transfer lifecycle: initiated, pending approval/review, processing, settled, failed, rejected, reversed. Use only states that have a defined transition and implementation.
- Validate source/destination, ownership/permissions, currency, account status, available funds, configured limits, and duplicate request.
- Post debit and credit atomically.
- Enforce idempotency with a unique database key scoped to the submitting actor/customer and operation. Store a request payload hash; same key with a different payload must be rejected.
- Support safe, explicit retry behavior; never duplicate a financial posting on retry.
- Maintain a user-visible transfer reference and internal correlation/request ID.
- A failed or rejected transfer must not leave partial postings.

### 4.2 Financial operations workbench

#### Review and approvals

- Implement maker-checker separation: the initiating user cannot approve their own restricted transaction when the policy requires independent approval.
- Approval decisions are approve/reject with mandatory reason/comment where configured.
- Record reviewer, decision, timestamp, reason, policy/rule, and associated transaction.
- Use explicit state transitions and prevent duplicate approval.
- Display queue filters: status, amount band, age, risk/reason, assigned operator.

#### Exceptions queue

- Centralize failed, rejected, delayed, and reconciliation-break work items.
- Show severity, exception type, reference, amount, age, owner/assignee, and next action.
- Support assignment, comments, resolution codes, and auditable resolution.
- Do not claim automated investigation/AI capabilities until a real implementation and tests exist.

#### Settlements

- Represent settlement batches with unique identifiers, expected totals, recorded totals, counts, lifecycle state, timestamps, and related transfers.
- Support simulated settlement generation and controlled state transitions.
- Detect mismatch and route it to an exception/reconciliation workflow.
- Explicitly label settlement as internal simulation, not a real rail connection.

#### Reconciliation

- Compare ledger totals against a simulated external/source statement or settlement batch.
- Track matched, unmatched, missing, duplicated, and amount-mismatch records.
- Support drill-down and auditable resolution.
- Never silently rewrite posted ledger rows to force a match.

### 4.3 Security and governance

- Authentication with secure sessions and logout.
- Role-based access control, with at least customer, operations, auditor, and administrator personas where the product scope supports them.
- Enforce permissions in backend dependencies/services and test allowed and forbidden access.
- Password hashing using a suitable password hashing scheme; no plaintext or reversible password storage.
- CSRF defenses for cookie-authenticated state-changing requests.
- Session expiry/revocation and secure cookie settings appropriate to environment.
- Append-only audit records for sensitive actions. Record actor, action, target, timestamp, request/correlation ID, and safe metadata/reason.
- Audit history must not be editable/deletable by ordinary runtime application roles.
- Never expose secrets or sensitive credentials in logs, API errors, UI, or audit metadata.

### 4.4 SRE and platform operations

#### Service health

- Monitor API, database, and background worker dependencies when those processes exist.
- Separate liveness from readiness. Readiness must reflect required dependencies and migration/schema compatibility.
- Show last check time and the source of the status.

#### Golden signals and diagnostics

- Request rate, error rate, latency (including p50/p95/p99 where data supports it), saturation/resource indicators, database connection pool health, and worker/queue state.
- Trace a request across application boundaries using correlation/trace IDs.
- Link UI diagnostics to request IDs and structured logs without exposing sensitive values.
- Use OpenTelemetry instrumentation and Prometheus-compatible metrics where appropriate.
- Grafana dashboards should describe real instrumented metrics, not static illustrative numbers.

#### SLO and incident workflows

- Define a small, defensible set of service-level indicators and objectives.
- Show error budget burn only when backed by actual measurement windows.
- Incident record should include severity, affected service, start/end, status, timeline, owner, mitigation, and post-incident notes.
- Provide runbooks for common failures: DB unavailable, migration mismatch, elevated 5xx, high latency, failed worker jobs, and reconciliation differences.

### 4.5 Cloud-native delivery

- Reproducible local Docker Compose stack with health checks and named persistent volumes.
- Non-root application container and least-privilege database roles.
- CI quality gates for frontend/backend, migration round trips, integration tests, and container build/config validation.
- Build/publish/deploy workflows with environment separation and protected secrets.
- Terraform for cloud infrastructure only after local application behavior and deployment topology are stable.
- Initial AWS target may use ECS Fargate, RDS PostgreSQL, Secrets Manager, CloudWatch, and a suitable ingress/load-balancing layer. Treat this as a deployment target, not as already provisioned infrastructure.
- Do not add Kubernetes, Kafka, Redis, or a microservice fleet without an accepted requirement and measurable operational reason.

---

## 5. Important data and domain design rules

These are architectural constraints, not a mandate to create every table in the first migration.

- Use UUIDs for externally addressable domain entities unless an ADR justifies otherwise.
- Use UTC-aware timestamps (`timestamptz` in PostgreSQL).
- Keep customer identity and account ownership explicit.
- Keep ledger accounts separate from customer-facing accounts.
- Model journal entries separately from ledger postings.
- Model account balance as a projection/cache derived from ledger events, never as the independent source of truth.
- Use explicit currency codes and scale/precision rules.
- Keep transaction state transitions explicit and validated.
- Keep idempotency records with scope, key, payload hash, and result reference.
- Use an outbox record in the same DB transaction when reliable asynchronous publication is introduced.
- Keep audit events append-only and distinct from application log lines.
- Introduce database indexes for real query patterns; verify with explain plans when volumes become meaningful.
- Schema changes are Alembic migrations. No manual production schema changes.

Potential domain groups for later phases:

- Identity: `users`, `roles`, `user_roles`, `sessions`, `customer_profiles`.
- Ledger: `accounts`, `ledger_accounts`, `journal_entries`, `ledger_postings`, `account_balances` (projection).
- Transfers: `transfers`, `idempotency_keys`, `transfer_state_history`.
- Operations: `approval_requests`, `approval_decisions`, `exceptions`, `settlement_batches`, `reconciliation_runs`, `reconciliation_items`.
- Governance: `audit_events`.
- Platform integration: `outbox_events`, worker job records if required.

Choose the minimal schema for the active PR. Do not create speculative tables without a near-term use and corresponding tests.

---

## 6. Delivery roadmap and dependencies

The sequence intentionally separates infrastructure foundations, identity, user experience, financial domain logic, operations, and SRE. Each PR must be reviewable and independently verified.

| PR | Scope | Exit criteria |
|---|---|---|
| **PR 3** | PostgreSQL, SQLAlchemy 2.x, Alembic, Docker Compose, runtime/migration roles, DB-backed readiness | PostgreSQL 17 integration tests; migration upgrade/downgrade/upgrade; least-privilege roles; non-root API container; Compose config/build/start checks; PR 1/2 tests remain green |
| **PR 4** | Authentication, secure sessions, CSRF, RBAC, customer profile, audit integration | Positive and negative authorization matrix; secure session lifecycle; CSRF tests; audit immutability and actor/context coverage |
| **PR 5** | Premium design system, public website, operations console shell, responsive navigation | Approved palette/tokens implemented; app shell and navigation; page routes and role-aware nav; accessible shared components; no fake workflow claims; typecheck/build/component tests |
| **PR 6** | Accounts, ledger, transfers, idempotency, atomic posting | Real PostgreSQL-backed domain logic; balanced journals; reversal flow; concurrency/duplicate tests; API and UI integrated end-to-end |
| **PR 7** | Review/approval, exceptions, settlements, reconciliation | Maker-checker rules; valid state transitions; exception ownership/resolution; reconciliation-break tests; full audit coverage |
| **PR 8** | OpenTelemetry, metrics, dashboards, SLOs, incident/runbook support | Instrumented services; trace/request correlation; real metrics; useful dashboards; SLO calculations validated against sample data; runbooks tested where practical |
| **PR 9** | Terraform, CI/CD deployment workflow, AWS environment | Reviewed infrastructure plan; secret handling; staged deployment; health checks/rollback; cost and teardown documentation; owner approval before provisioning |

### Current sequencing constraint

PR 3 is the immediate infrastructure milestone. Do not combine the premium UI redesign with PR 3. Finish/reconcile the PostgreSQL foundation first, then proceed to PR 4, then redesign the frontend in PR 5 with the database/auth contracts understood.

The PR 3 feature branch was observed behind `main` in the 17 November 2026 repository snapshot. Re-check the refs and reconcile it with current `main` before continuing. Preserve the recent frontend and design-system work on `main`.

---

## 7. Page-level experience requirements

The console should be data-driven and operationally useful. These are page requirements for the roadmap; pages may be delivered incrementally.

### Overview

- Show environment (`Sandbox`/`Demo`), last updated timestamp, and data provenance.
- Financial summary: total simulated balances, active accounts, transfers in selected period, pending review amount/count, exceptions count.
- Operations summary: approval queue, failed transfers, settlement status, unresolved reconciliation breaks.
- Platform strip: API, database, worker, and deployment status only when backed by real checks.
- Recent activity feed with traceable transaction/actor references.
- Useful period and status filters.

### Accounts

- Search by account reference, customer, status, or currency.
- Account detail page with profile summary, status, available/current balance, activity, ledger linkage, and audit timeline.
- Controlled actions (freeze/restrict/close) based on role and state machine, always with confirmation and reason where necessary.

### Payments & Transfers

- Transfer list with reference, source, destination, amount/currency, status, initiated time, owner, and idempotency/reference metadata appropriate to the user's role.
- Transfer creation flow with validation and explicit confirmation.
- Transfer detail timeline with state changes, linked journal entry, approval details, and audit events.
- Clear distinction between initiated, approved, posted, settled, failed, and reversed states.

### Ledger Explorer

- Search/filter by journal ID, account, date, reference, direction, and amount.
- Journal detail shows all postings and a visible balanced debit/credit total.
- Make immutable state explicit; corrections link to reversal entries.

### Review & Approvals

- Prioritized queue with age, amount, risk/reason, and assigned reviewer.
- Clear maker/checker identity and prohibited self-approval state.
- Approve/reject flow with required reason and a final confirmation.

### Exceptions Queue

- Filter by severity, type, status, age, service, and owner.
- Detail view includes event context, linked transaction, diagnostic request ID, timeline, assignment, notes, and resolution code.

### Settlements and Reconciliation

- Batch overview with totals, record counts, lifecycle state, and timestamps.
- Reconciliation shows match/mismatch totals and individual break items.
- Provide drill-down and controlled resolution rather than hiding discrepancies.

### Audit Trail

- Filter by actor, action, target, date, and request ID.
- Show append-only metadata in a readable timeline/detail view.
- Never allow ordinary users to edit/delete audit history.

### Service Health

- API/database/worker health, request rate, error rate, latency, saturation, queue depth, recent deployments/incidents.
- Display the measurement source and timestamp.
- Distinguish a configured check from an unavailable metric; missing telemetry must not display as zero incidents/errors.

### Users & Access

- User list, role assignments, status, last activity, and access history.
- Role change/revoke actions require suitable authorization and audit events.

---

## 8. Demo and seed-data rules

- Seed data must be deterministic and clearly marked as synthetic.
- Provide enough sample entities to demonstrate account, transfer, approval, exception, settlement, reconciliation, and audit workflows once those capabilities exist.
- Do not seed contradictory records (for example, a settled transfer with no journal posting or a balanced flag with unbalanced postings).
- Demo data should be resettable without manual SQL editing.
- In every page, distinguish `No data`, `Loading`, `Unavailable`, `Failed to load`, and `Zero` states. These are not interchangeable.
- Do not manufacture KPI trends or chart history just to fill space. If there is insufficient data, show an honest empty state or explicitly labelled demo dataset.

---

## 9. Non-functional requirements and acceptance standards

### Security

- Validate authorization at the API/service boundary.
- Validate input with typed request/response schemas.
- Avoid leaking secrets or internal stack traces.
- Use least privilege for database/runtime roles.
- Treat audit and financial records as sensitive data.

### Correctness

- Money precision and currency are explicit.
- Posting is atomic and balanced.
- Posted history is immutable; corrections are reversals.
- Idempotency protects against duplicate financial effects.
- State transitions are deterministic and tested.
- Reconciliation detects mismatch; it does not silently alter the ledger.

### Reliability

- Readiness checks required dependencies; liveness tests process health.
- Migrations are repeatable and reversible where the migration supports a safe downgrade.
- Background jobs, where used, need retries, bounded attempts, idempotency, and dead-letter/exception handling.
- Failures should be diagnosable through request IDs, structured logs, and traces.

### UX and accessibility

- Responsive at 375px, 768px, 1024px, and 1440px.
- No unintended horizontal page overflow.
- Keyboard-operable navigation/dialogs/filters/tables.
- Visible focus states and semantic labels.
- WCAG AA contrast for ordinary text.
- Loading, empty, error, permission-denied, and success states are designed.
- Respect reduced motion.

### Testing

- Unit tests for domain rules and state transitions.
- PostgreSQL integration tests for constraints, permissions, transactions, triggers, and migrations.
- API tests for success, validation, authorization, conflict, and failure paths.
- Frontend tests for important interaction paths and error/loading states.
- End-to-end tests for critical user journeys once the relevant frontend/backend modules exist.
- Keep fixtures and seeded demo data internally consistent.

---

## 10. Critical user journeys to build and verify

These journeys define the product's integrated behavior. Implement them as the underlying phases become available.

1. **Initiate and post a transfer:** an authorized actor selects valid accounts, enters amount/currency, submits once, receives a stable reference, and the backend atomically posts a balanced journal entry.
2. **Retry safely:** the same idempotency key and request returns the original result without another posting; the same key with a different payload is rejected.
3. **Maker-checker approval:** an initiator submits a transaction requiring review; a different authorized reviewer approves/rejects it; every decision is auditable.
4. **Investigate an exception:** a failed/rejected event appears in the queue; an operator assigns and investigates it; resolution is recorded without rewriting immutable ledger history.
5. **Reconcile a batch:** a settlement batch is compared with ledger records; matched and mismatched items are shown; an operator resolves a break with an auditable action.
6. **Trace an operational failure:** a user follows a request/correlation ID from UI transaction detail to API logs/traces and identifies whether the application, database, or worker caused the issue.
7. **Enforce permissions:** a user without the required role cannot access or mutate protected records even by calling the API directly.

---

## 11. Implementation instructions for Codex

When asked to implement LedgerOps 2.0:

1. Read `AGENTS.md` and this file before changing code.
2. Inspect the live repository; establish exact branch and commit state.
3. Produce a concise current-state matrix: implemented, partial, demo-only, missing.
4. Identify the next incomplete PR in section 6 and verify prerequisites.
5. Do not skip PR 3 database foundations to jump directly to UI polish or domain features.
6. Do not mix PR 3 database work with PR 5 design work.
7. Implement the exact active PR scope, including tests, docs, migration and rollback where applicable.
8. Use the visual direction in section 3 exactly when PR 5 begins. Do not substitute a different palette or typography without the owner's approval.
9. Keep demo-only functionality explicitly labelled until a real backend implementation replaces it.
10. Report actual validation results and leave unverified items clearly marked.

**Definition of done:** a requirement is done only when its implementation, tests, user-facing behavior, documentation, and applicable acceptance checks are present. A mockup or placeholder does not satisfy a functional requirement.
