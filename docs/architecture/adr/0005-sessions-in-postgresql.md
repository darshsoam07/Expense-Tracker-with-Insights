# ADR-0005: Sessions stored in PostgreSQL

- **Status:** Accepted (2026-11-15)
- **Related:** ADR-0001

## Context

Server-side sessions need a store. Redis is deferred to Phase 3 (when background workers arrive), so adding it now would add an unneeded moving part.

## Decision

- Sessions live in a PostgreSQL `sessions` table.
- The browser holds a random token. **The database stores only its SHA-256 hash**, so a database leak cannot be replayed as live sessions.
- Idle timeout 30 minutes, absolute lifetime 8 hours. These are proposed defaults and are configurable.
- A per-account failed-login counter with a temporary lock is also stored in PostgreSQL. Per-IP rate limiting is deferred to the load balancer or WAF layer and will be documented as such.

## Consequences

- One fewer service in Phase 1 and a single backup target.
- Each authenticated request reads the database. This is acceptable at this scale and can move to Redis later through a new ADR if measurements justify it.
