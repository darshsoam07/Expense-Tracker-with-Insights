# ADR-0006: Strangler migration with the legacy app preserved in the repository

- **Status:** Accepted (2026-11-15)

## Context

The original Expense Tracker works but cannot safely hold financial data (see the Phase 0 audit). A big-bang rewrite would risk losing working behaviour and Git history.

## Decision

- Tag the baseline commit `e1b3984` as the annotated tag **`legacy-v1`**.
- Move every tracked file into `legacy/expense-tracker/` in a **rename-only commit** with no content changes, so Git records 100% renames and `git log --follow` keeps history.
- Build the new FastAPI, React and PostgreSQL application **beside** it. Reuse ideas and the visual language, not code blindly.
- Legacy data migration is **not required**. Any future importer must go through the new ledger service, never by inserting rows directly.
- Retire the legacy app (tag `legacy-final`) only after the new customer journey passes end-to-end tests.
- Never force-push or rewrite published history. PR 1 is merged with a merge commit so the rename-only commit stays distinct.
- The repository is **not renamed** without presenting the change first.

## Consequences

- The old app stays runnable throughout the migration.
- The repository temporarily holds two applications.
- Docker note: Docker Compose derives its project name from the compose file's folder, so the relocated legacy stack uses a different project and volume name than before. See `docs/legacy-migration.md`.
