# LedgerOps

A **simulated** cloud-native banking and financial-operations platform, built as a portfolio project for Backend, Cloud, DevOps and SRE engineering.

> **Scope and honesty notice.** LedgerOps uses synthetic customers and simulated funds only. It does not connect to real banks or payment rails and makes no claim of regulatory compliance, audit certification, or production-banking readiness.

## Current status

| Item | State |
|---|---|
| Phase | **Phase 1, PR 3** (PostgreSQL foundation) |
| New application | FastAPI foundation with health endpoints and a standalone React ledger preview. Transfers use browser memory and reset on reload. |
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

Run `python scripts/init_compose.py` to create local Compose credentials in the root `.env`. Existing files are preserved. From the repository root run `docker compose up --build`, then open <http://localhost:5173>. The browser reads FastAPI readiness at <http://localhost:8000/health/ready>. Source files are bind-mounted for Vite hot reload. Run `docker compose down` to stop the services.

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

1. **Phase 1:** foundation (FastAPI, PostgreSQL, authentication, React shell, CI)
2. **Phase 2:** accounts, double-entry ledger, transfers, idempotency
3. **Phase 3:** customer experience, statements, reports
4. **Phases 4 to 6:** delivery automation, AWS (Terraform), observability and recovery drills
5. **Phase 7:** optional extensions, only where a concrete need is shown

Each phase is approved before it starts. No cloud resources are created without explicit approval.

See [PR 3 setup, roles, verification and rollback](docs/architecture/pr3-database-foundation.md) and the [approved product blueprint](docs/product/LEDGEROPS_2.0_BLUEPRINT.md).
