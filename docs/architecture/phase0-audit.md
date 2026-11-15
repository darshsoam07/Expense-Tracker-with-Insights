# LedgerOps Phase 0: Repository Audit and Migration Plan

Baseline: `darshsoam07/Expense-Tracker-with-Insights`, branch `main`, commit `e1b3984` (5 commits). Audit date: 15 November 2026. No application code was modified.

## 0. What was and was not verified

**Verified by running it:** the repository was cloned, `requirements.txt` installed into a fresh Python 3.12 venv (resolved to Flask 3.1.3, Werkzeug 3.1.9, openpyxl 3.1.5), `python app.py` started, and probed with `curl`. Everything marked *(verified)* was observed on the running app.

**Read only, not run:** the Dockerfile and `docker-compose.yml` (Docker was unavailable in the sandbox), the frontend JS/CSS, and the README.

**Not reviewed:** the StarAgile reference repository and the Banking Domain Fundamentals PDF. They matter for Phase 2 domain modelling, not for this audit.

## (a) Current architecture and file map

A single-process Flask app: server-rendered shell plus a vanilla-JS dashboard calling a JSON API, SQLite on a Docker volume.

| File | Lines | Role |
|---|---|---|
| `app.py` | 507 | Everything backend: config, DB helpers, schema creation (`init_db()` runs at import), auth routes, expense CRUD, summary/KPI aggregation, Excel export |
| `templates/base.html`, `auth.html`, `index.html` | 56 / 90 / 311 | Jinja shell, login/signup, dashboard |
| `static/js/dashboard.js` | 572 | Fetches the API, renders KPIs, Chart.js charts, ledger table, modal CRUD, CSV export |
| `static/css/app.css` | 326 | Dark theme styling |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | | `python:3.12-slim`, runs `python app.py` on port 4949, named volume for `/app/instance` |
| `requirements.txt` | | `Flask>=3.0,<4.0`, `openpyxl>=3.1,<4.0` (ranges, not pinned) |

**Routes:** `GET /`, `POST /signup`, `POST /login`, `GET /dashboard`, `GET /logout`, `GET|POST /api/expenses`, `PUT|DELETE /api/expenses/<id>`, `GET /api/expenses/summary`, `GET /api/expenses/export/excel`.

**Schema (SQLite):** `users(id, name, email UNIQUE, password, created_at)` and `expenses(id, user_id FK, description, merchant, amount REAL CHECK>0, category, date TEXT, created_at)` with indexes on user, date, category. No migrations, roles or accounts.

**Absent entirely (verified):** tests, CI configuration, linting, type checking, health endpoints, logging setup, metrics.

## (b) Run, build and test instructions

Verified locally (no Docker):

```bash
git clone https://github.com/darshsoam07/Expense-Tracker-with-Insights.git
cd Expense-Tracker-with-Insights
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") python app.py
# -> http://localhost:4949
```

Docker (`docker compose up --build`) was **not verified**. The compose file ships a placeholder secret. There are no tests to run.

## (c) Feature inventory worth preserving

| Feature | Where | Verdict |
|---|---|---|
| Per-user data scoping on every query (`WHERE user_id = ?`) | `app.py` | **Keep the pattern.** Ownership checks worked in testing: another user's PUT returned 404, DELETE returned `deleted:false` *(verified)* |
| Server-side filters: period, category, free-text search | `_period_dates`, `_build_query` | **Port** to transaction queries, with tests |
| KPI/summary aggregation | `/api/expenses/summary` | **Port logic, rewrite math** on `Decimal`/`NUMERIC` and ledger postings |
| Category taxonomy (6 categories, server allowlist) | `VALID_CATEGORIES` | **Keep as seed data** |
| Excel export with formatting | `/api/expenses/export/excel` | **Port** to statements via a background job (Phase 3) |
| Dashboard UI: KPI cards, three Chart.js charts, ledger table, modal, responsive layout | `dashboard.js`, `index.html`, `app.css` | **Reuse the visual design** in React components; do not port the vanilla JS verbatim |
| Output escaping (`escapeHTML`) | `dashboard.js` | Good practice. React escapes by default |
| Parameterised SQL, password hashing (Werkzeug) | `app.py` | Keep the principles; ORM and Argon2id in the new stack |

The tracker models **outflow only**: no income, balance or account. Deposits, transfers and balances are net-new, so this is a re-platform with selective reuse, not a refactor.

## (d) Security and technical-debt findings, ranked

### Critical

1. **Debug mode is on and exposed on all interfaces.** `app.run(debug=True, host="0.0.0.0")` is also the Docker `CMD`. An invalid amount returned a full Werkzeug debugger page with source paths *(verified)*; `/console` responds `200` *(verified, PIN-locked)*.
2. **Forgeable sessions via a public default secret.** `SECRET_KEY` falls back to `"change-this-secret-before-production"`, and `docker-compose.yml` ships another public placeholder. A cookie signed with the default key for `user_id=1` was accepted by the live server, which returned that user's data *(verified)*.

### High

3. **Money stored and summed as binary floats.** `0.1 + 0.2` came back as `0.30000000000000004` from the summary API *(verified)*.
4. **Input validation gap crashes the endpoint.** `amount: "nan"` and `"inf"` pass `float()` and the `<= 0` check, then fail at the database with an unhandled `500` *(verified)*. After the `nan` failure a normal valid insert also returned `500` *(verified)*; an earlier run showed `database is locked`. Connections are not closed in `try/finally`, the likely cause, which was not isolated.
5. **No CSRF protection.** No tokens *(code review)*. The cookie is `HttpOnly` only, with no `Secure` or `SameSite` *(verified)*. `GET /logout` changes state *(verified)*. JSON endpoints are partly shielded by the content-type requirement; cross-site abuse was not tested.
6. **No rate limiting.** 30 consecutive wrong-password logins all returned `302` *(verified)*.

### Medium

7. No security headers (CSP, `X-Frame-Options`, HSTS, `nosniff`) *(verified)*.
8. Third-party scripts unpinned and without SRI (Tailwind CDN, `chart.js@4`, `lucide@latest`). Tailwind's CDN build is not intended for production.
9. Signup confirms whether an email is registered. Password policy is length >= 6 only.
10. Container runs as root, no `HEALTHCHECK`, base image not pinned by digest, dependencies are ranges.
11. SQLite with a single file and the debug reloader: no concurrent-write story, no backup.

### Low

12. `.gitignore` is corrupted: a pasted patch fragment sits inside it. The real rules on its first lines still apply.
13. 507-line `app.py` mixes config, data access, auth, domain logic and export. `init_db()` runs on import. Add/update validation is duplicated. There is an inline `__import__("datetime")`.
14. README has a screenshot placeholder and no tests/CI section.

Not everything is poor: output escaping, parameterised queries, category allowlisting, password hashing and ownership scoping are done correctly.

## (e) Target architecture mapped to current files

| Current | Target | Treatment |
|---|---|---|
| `app.py` auth routes | `backend/app/modules/auth` | Rewrite: new auth model, roles, CSRF |
| `app.py` expense CRUD | `modules/ledger`, `modules/transfers` | **Replace.** Expenses become journal postings with category metadata |
| `/api/expenses/summary` | `modules/reporting` | Port filter/aggregation logic; rewrite on `NUMERIC` |
| Excel export | background worker and S3 | Port formatting |
| SQLite `init_db()` | Alembic migrations on PostgreSQL | Replace |
| `templates/*` and `dashboard.js` | `frontend/src` (React, TypeScript, Tailwind) | Reuse visual language; rebuild components |
| `Dockerfile`, compose | per-service Dockerfiles, `deployment/docker-compose.yml` | Replace: production server, non-root, healthchecks |
| (none) | `.github/workflows`, `infrastructure/terraform`, `observability/` | New |

The decisions approved from this audit are recorded in ADR-0001 to ADR-0006.

## (f) Migration plan: no big-bang rewrite

1. Freeze a baseline: tag `legacy-v1`; move the app to `legacy/expense-tracker/` unchanged.
2. Build the new stack beside it.
3. Legacy data migration is not required. A future importer must use the ledger service.
4. Retire legacy after the new customer journey passes end-to-end tests.
5. The legacy app is not publicly deployed (confirmed by the project owner), so no standalone hotfix is needed.

## (g) Prioritised backlog

The approved sequence is in the [Phase 1 plan](phase1-plan.md) (PR 1 to PR 5), followed by the Phase 2 banking-core PRs.
