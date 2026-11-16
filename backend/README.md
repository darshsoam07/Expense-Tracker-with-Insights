# LedgerOps backend

FastAPI backend for LedgerOps (a **simulated** banking platform; synthetic data only).

## Status (PR 2: backend skeleton)

| Exists and is tested | Does **not** exist yet |
|---|---|
| App factory, validated configuration, JSON logging, request IDs, standard error responses, `/health/live` and `/health/ready`, lint/type/architecture/test tooling, CI | PostgreSQL and **any database check** (PR 3), login and sessions (PR 4), accounts, ledger, transfers (Phase 2), Docker image (PR 3), frontend (PR 5) |

`/health/ready` currently reports only whether the app has finished starting and is not shutting down. It says nothing about a database, because there is no database yet.

## Requirements

- **Python 3.12** (check with `py -3.12 --version` on Windows, `python3.12 --version` elsewhere)
- Git

Commands are given for **PowerShell** and **Git Bash**. They have been run on Linux; **they have not yet been run on Windows**, so please report anything that differs.

## Setup

Run these inside the `backend/` folder.

**PowerShell**

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -c constraints.txt -e ".[dev]"
Copy-Item .env.example .env
```

**Git Bash**

```bash
cd backend
py -3.12 -m venv .venv
source .venv/Scripts/activate
pip install -c constraints.txt -e ".[dev]"
cp .env.example .env
```

`.env` is git-ignored. The placeholder secret in `.env.example` works only for `APP_ENV=local` or `test`. To use a real one, generate it and paste it into `.env`:

```
py -c "import secrets; print(secrets.token_hex(32))"
```

## Run

```
uvicorn app.main:create_app --factory --reload
```

Then open <http://127.0.0.1:8000/api/v1/docs>. In PowerShell use `curl.exe` (plain `curl` is an alias for another command):

```powershell
curl.exe -i http://127.0.0.1:8000/health/live
curl.exe -i http://127.0.0.1:8000/health/ready
curl.exe -i http://127.0.0.1:8000/api/v1/nothing     # standard JSON 404 with X-Request-ID
```

## Quality checks (the same commands CI runs)

```
ruff check .
ruff format --check .
mypy
lint-imports
pytest
```

`pytest` also measures coverage and fails below 85%. To auto-format: `ruff format .`

## Configuration

Read from environment variables or `.env`. `APP_ENV` and `SECRET_KEY` have **no defaults**: forgetting them is an error, not a silent weak mode.

| Variable | Required | Rules |
|---|---|---|
| `APP_ENV` | yes | `local`, `test`, `staging` or `production` |
| `SECRET_KEY` | yes | Never empty. In `staging`/`production`: at least 32 characters, no placeholder words, enough variety |
| `LOG_LEVEL` | no (`INFO`) | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `COOKIE_SECURE` | no (`true`) | Must be `true` in `staging`/`production` |
| `DEBUG` | no (`false`) | Must be `false` in `staging`/`production` |
| `ENABLE_DOCS` | no (`true`) | Serves `/api/v1/docs` and `/api/v1/openapi.json` |

Invalid configuration makes the app **refuse to start**, listing every problem. The message never contains the secret. `COOKIE_SECURE` is validated now but first used when cookies arrive in PR 4.

## Endpoints

| Path | Purpose |
|---|---|
| `GET /health/live` | The process is running. `200` always |
| `GET /health/ready` | Safe to receive traffic? `200` if every check passes, else `503`. Today: `app_started` only |
| `GET /api/v1/docs`, `/api/v1/openapi.json` | API documentation |

All application endpoints will live under `/api/v1/`. Only `/health/*` sits outside it.

## Error responses

Every failure has this shape (including 404, 405, 422 and 500):

```json
{"error": {"code": "not_found", "message": "Not Found", "request_id": "…", "details": []}}
```

Bodies never contain tracebacks or the values a client sent. The same `request_id` is in the `X-Request-ID` header and in every log line for that request. To raise an expected error in code: `raise AppError(409, "duplicate_request", "Already processed.")`.

## Logging

One JSON object per line on stdout. Structured fields named like `password`, `token`, `cookie`, `authorization`, `secret`, `csrf` or `session` are replaced with `[REDACTED]`. **Redaction does not cover free text:** never put secrets or personal data inside a log message string. Access logs record the path **without** the query string. Audit events (later) are stored in the database, not in logs.

## Project layout

```
app/
  main.py                 create_app(): builds the application
  core/                   config, logging, errors, request_context, readiness
  api/                    HTTP routers (health now; versioned endpoints later)
tests/{unit,api}/         pytest
pyproject.toml            dependencies (exact pins) and tool configuration
constraints.txt           pinned versions of every package, direct and transitive
```

**Architecture rule, enforced by `lint-imports`:** imports only point downward: `main` may use `api` and `core`; `api` may use `core`; `core` may use neither. Module-level rules (for example "only the ledger writes balances") are added when those modules exist.

## Changing dependencies

Edit `pyproject.toml`, then regenerate `constraints.txt` from a clean virtualenv (instructions in its header) and review the diff before committing.
