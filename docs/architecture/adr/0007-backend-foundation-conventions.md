# ADR-0007: Backend foundation conventions (PR 2)

- **Status:** Accepted (2026-11-16)
- **Amends:** the Phase 1 plan (see "Differences from the plan" below)

## Context

PR 2 creates the backend skeleton. Several small decisions shape every later PR, so they are recorded here.

## Decisions

1. **Application factory, no import-time side effects.** `create_app(settings=None)` builds the app. Run it with `uvicorn app.main:create_app --factory`. Importing `app.main` never reads configuration or starts anything, so tests build isolated apps with explicit settings.
2. **No defaults for `APP_ENV` and `SECRET_KEY`.** A forgotten value fails loudly instead of silently running in a weak mode. Outside `local`/`test` the app refuses to start on a short, placeholder or low-variety secret, on `COOKIE_SECURE=false`, or on `DEBUG=true` (staging and production). Configuration errors are sanitised so the offending value is never printed, and the original validation error (which contains the input) is dropped.
3. **Standard-library JSON logging instead of `structlog`.** About 60 lines, no extra dependency, easier to read. Sensitive structured fields are redacted by key name; free-text messages are not scanned, so developers must never put secrets in message text.
4. **Request IDs.** Reuse an inbound `X-Request-ID` only if it is 8 to 64 characters of letters, digits, `.`, `_` or `-`; otherwise generate a UUID. This keeps correlation across proxies while preventing log or header injection. The ID is returned on every response, including errors.
5. **One middleware owns the last-resort 500.** `RequestContextMiddleware` assigns the request ID, writes the access log (path only, no query string), and converts unexpected exceptions into the standard JSON 500 with the traceback logged server-side only. Doing it there (not in a framework exception handler) guarantees the 500 also carries the request ID header.
6. **One error shape for everything** (`{"error": {"code", "message", "request_id", "details"}}`). Validation errors copy only location, message and type, never the submitted value.
7. **Readiness is honest.** `/health/ready` runs a registry of named checks. Today it has one: `app_started`, false before start-up completes and as soon as shutdown begins. There is **no database check until PR 3**, and the response contains no `database` key. A test guards this. `/health/live` has no dependencies, so a failing dependency can never cause a restart loop.
8. **Docs under the version prefix.** API docs are served at `/api/v1/docs` and `/api/v1/openapi.json`, so a reverse proxy only needs to route `/api/`. Only `/health/*` is outside the prefix.
9. **Dependencies.** Direct dependencies are pinned exactly in `pyproject.toml`; `constraints.txt` pins every transitive package. CI installs with `-c constraints.txt`. For the test client the project uses `httpx2` (the package Starlette 1.x now asks for; `httpx` triggers a deprecation warning, and tests run with warnings as errors). Only three runtime dependencies are used: FastAPI, uvicorn, pydantic-settings.
10. **Architecture boundaries are code, not convention.** `import-linter` enforces `main -> api -> core`. More contracts are added when the modules they name exist (a contract cannot name a module that does not exist yet).
11. **CI actions are pinned to full commit SHAs** with the release in a comment, and the workflow has read-only permissions.

## Differences from the Phase 1 plan

- `structlog` is not used (decision 3).
- `.env.example` lives in `backend/` (next to the code that reads it), not the repository root. A root-level one will be added with Docker Compose in PR 3.
- No `Makefile` is added. Every command is documented directly, which works unchanged in PowerShell and Git Bash.

## Consequences

- Fewer dependencies and fewer surprises, at the cost of a few hand-written helpers that are fully tested.
- The `app_started` check proves only that the process is serving, not that dependencies work. That limitation is stated in the README and API behaviour until PR 3.
