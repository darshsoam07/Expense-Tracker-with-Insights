# LedgerOps

A **simulated** cloud-native banking and financial-operations platform, built as a portfolio project for Backend, Cloud, DevOps and SRE engineering.

> **Scope and honesty notice.** LedgerOps uses synthetic customers and simulated funds only. It does not connect to real banks or payment rails and makes no claim of regulatory compliance, audit certification, or production-banking readiness.

## Current status

| Item | State |
|---|---|
| Phase | PR 7a account holds in local review |
| PR 3 | ✅ Merged — PostgreSQL 17, Alembic foundation migration, Docker Compose stack, FastAPI health endpoints |
| PR 3H | ✅ Merged — ADR-0009 amendments, implementation roadmap, README update, repo hygiene |
| PR 5 | ✅ Merged (GitHub PR #2) — Institutional Luxury website and operations console, frontend CI job |
| PR 4a | ✅ Merged (GitHub PR #5) — Identity, RBAC, sessions, CSRF, and append-only audit trail |
| PR 4b | Merged — Frontend auth integration, login/logout UI, same-origin Vite proxy, CORS removal, Windows CI job |
| PR 6a | Merged in GitHub PR #7 |
| Application | Cookie-authenticated console with scoped INR accounts, posted journals and simulated internal transfers |
| Legacy Expense Tracker | Preserved and runnable in `legacy/expense-tracker/` |
| Cloud resources | **None.** Nothing is deployed anywhere |

LedgerOps evolves an earlier Flask expense-tracker project. The old app is kept intact while the replacement is built beside it (a "strangler" migration, see [ADR-0006](docs/architecture/adr/0006-strangler-migration.md)).

## Repository layout

```
legacy/expense-tracker/   Original Flask + SQLite app, byte-identical to tag legacy-v1
backend/                  New FastAPI backend (see backend/README.md)
.github/workflows/        CI: lint, types, architecture rules, tests
docs/architecture/        Phase 0 audit, Phase 1 plan, architecture decision records
docs/legacy-migration.md  How the relocation was done and verified
scripts/                  Cross-platform (Python) verification scripts
```

## Documentation

- [Phase 0 audit](docs/architecture/phase0-audit.md): findings on the original app, including security issues
- [Phase 1 plan](docs/architecture/phase1-plan.md): approved plan for the foundation
- [Architecture decision records](docs/architecture/adr/): why each major decision was made
- [Legacy migration record](docs/legacy-migration.md): relocation, verification, Docker instructions

## Running both services with Docker Compose

Run `python scripts/init_compose.py` to create local Compose credentials in the root `.env`. Existing files are preserved. From the repository root run `docker compose up --build`, then open <http://localhost:5173>. The browser interacts with the frontend on <http://localhost:5173>, which proxies `/api` and `/health` requests to the FastAPI backend with same-origin cookies and in-memory CSRF tokens. Direct CORS configuration has been removed. Source files are bind-mounted for Vite hot reload. Run `docker compose down` to stop the services.

## Running the new backend

To run the ledger preview from the repository root:

```sh
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open the local URL printed by Vite. The preview runs independently. The API indicator polls FastAPI readiness every 15 seconds through the Vite proxy. Run the backend on port 8000 to see its status. Click the indicator to refresh immediately.

See [`backend/README.md`](backend/README.md) for setup, run and test commands (PowerShell and Git Bash).

## Running the legacy app locally

> The legacy app has known security issues (see the audit): debug mode, a default secret, no CSRF protection. **Run it on your own machine only. Never deploy it.**

Requires Python 3.10 or newer. These commands were written for Windows but **have not been tested on Windows**; the Linux equivalent was.

**PowerShell**

```powershell
cd legacy\expense-tracker
py -m venv .venv
.\.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
$env:FLASK_SECRET_KEY = py -c "import secrets; print(secrets.token_hex(32))"
py app.py
```

**Git Bash**

```bash
cd legacy/expense-tracker
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
export FLASK_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python app.py
```

Then open <http://localhost:4949>. Windows may show a firewall prompt because the legacy app listens on all interfaces; choose "Cancel" or allow private networks only.

## Verifying the repository

From the repository root, in PowerShell or Git Bash (no Bash-only scripts are used):

```
py scripts/verify_relocation.py     # Git history and file-content checks
py scripts/verify_legacy.py         # starts the legacy app in a temp folder and smoke-tests it
```

(On Git Bash, `python` may be used instead of `py`.)

## Roadmap

The active delivery sequence (revised in PR 3H) is:

`PR 3 → PR 3H → PR 5 → PR 4a → PR 4b → PR 6a → PR 6b → PR 7a → PR 8 → …`

| PR | Scope | Status |
|---|---|---|
| PR 3 | PostgreSQL foundation, Alembic, Compose, health endpoints | ✅ Merged |
| PR 3H | ADR-0009 amendments, roadmap, README | ✅ Merged |
| PR 5 | Institutional Luxury UI & frontend CI | ✅ Merged |
| PR 4a | Authentication — identity, sessions, CSRF, RBAC, audit | ✅ Merged |
| PR 4b | Frontend auth integration, Vite proxy, CORS removal, Windows CI | Merged |
| PR 6a | Accounts, double-entry ledger, internal transfers | Merged |
| PR 6b | Corporate customer model (`customers` + `customer_members`) | ⏳ Planned |
| PR 7a | Account holds, expiry, available balance and capture through internal transfer | In local review |
| PR 8 | External payments, clearing lifecycle, outbox worker | ⏳ Planned |
| PR 9+ | Multi-currency, statements, observability, cloud deployment | ⏳ Future |

Each phase is approved before it starts. No cloud resources are created without explicit approval.

See [ADR-0009 amendments](docs/architecture/adr/0009-ledgerops-2-amendments.md), the [implementation roadmap](docs/product/LedgerOps%202.0%20Repository-Grounded%20Assessment%20and%20Implementation%20Roadmap.md), [PR 3 setup and rollback](docs/architecture/pr3-database-foundation.md), and the [approved product blueprint](docs/product/LEDGEROPS_2.0_BLUEPRINT.md).

See the [financial core decision and provisioning guide](docs/architecture/adr/0010-internal-financial-core.md) for account access, journal posting, and transfer retries.

Account detail shows ledger, held and available INR balances. See the [hold lifecycle, API and verification guide](docs/architecture/adr/0011-account-holds.md).
