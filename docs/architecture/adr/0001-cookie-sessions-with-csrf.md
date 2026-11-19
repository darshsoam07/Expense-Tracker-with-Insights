# ADR-0001: Authentication with server-side cookie sessions and CSRF protection

- **Status:** Accepted (2026-11-15)
- **Deciders:** Project owner
- **Related:** ADR-0005 (session storage)

## Context

The browser app and the API are served from one origin: an NGINX container locally and an AWS load balancer later, both routing `/api/` to the backend. There is no third-party browser client and no mobile app. The legacy app used signed Flask cookies, a public default secret, and had no CSRF protection.

## Decision

1. Authentication uses an **opaque random session ID in an `HttpOnly; Secure; SameSite=Lax` cookie**. **No JWT.** A JWT would be reconsidered only for a genuine future need (for example a native mobile client) through a new ADR.
2. Sessions are stored server-side (ADR-0005), so logout and revocation take effect immediately.
3. **Every state-changing request** (`POST`, `PUT`, `PATCH`, `DELETE`) must carry a valid CSRF token in the `X-CSRF-Token` header. `GET`, `HEAD` and `OPTIONS` never change state. Logout is therefore a `POST`.
4. The server also checks the `Origin` header (or `Referer` if absent) against the configured application origin on state-changing requests, as defence in depth.
5. There is **no CORS** allowance. The API is same-origin only.

### How the frontend obtains and uses a CSRF token

*Before login or registration (anonymous visitor):*

1. On startup the frontend calls `GET /api/v1/auth/csrf` (a safe, side-effect-free request).
2. The server generates `r = <issued_at>.<32 random bytes>`, sets it in a cookie (`HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=3600`), and returns `{ "csrf_token": HMAC_SHA256(csrf_key, r) }` in the body. `csrf_key` is derived from `SECRET_KEY` and is never sent to the client.
3. The frontend keeps the token **in memory only** (never `localStorage`) and sends it as `X-CSRF-Token` on `POST /api/v1/auth/register` and `POST /api/v1/auth/login`.
4. The server recomputes the HMAC from the cookie value `r`, compares it to the header with a constant-time comparison, and rejects if it differs or if `issued_at` is older than one hour. An attacker on another site can neither read the cookie nor compute the HMAC, so cannot forge the header. This also blocks "login CSRF".

*After login (authenticated):*

5. Login and registration **create a brand-new session** (preventing session fixation) with its own random `csrf_token`, stored on the session row. The anonymous CSRF cookie is cleared.
6. The login response body and `GET /api/v1/me` return the session's `csrf_token`. For authenticated requests the header must equal the session's stored token (constant-time comparison).
7. After a page reload the frontend calls `GET /api/v1/me`: `200` returns the current token, `401` means "anonymous", so it calls `/auth/csrf` again.

*Rotation and invalidation:*

| Event | Effect |
|---|---|
| Login or registration | New session ID and new CSRF token; anonymous CSRF cookie cleared |
| Logout | Session revoked in the database; cookies cleared; frontend fetches a fresh anonymous token |
| Password change, role change, account lock (future features) | All the user's other sessions revoked; current session gets a new ID and CSRF token |
| Idle timeout (30 min) or absolute lifetime (8 h) | Session invalid; the next request gets `401` |
| Failed CSRF check | `403` with error code `csrf_failed`; the event is written to the audit log |

Cookie names: when `COOKIE_SECURE` is true, the `__Host-` prefix is used (forces `Secure`, `Path=/`, no `Domain`).

**Correction (PR 4a review): both cookies use `Path=/`.** An earlier draft scoped the anonymous CSRF cookie to `Path=/api/v1/auth`. A `__Host-` cookie is only accepted by the browser when it has `Path=/`, so a narrower path is impossible in secure mode. For consistency the same cookie attributes apply in plain-HTTP local development. This costs little: the anonymous CSRF cookie is `HttpOnly`, short-lived (1 hour), carries no identity, is useless without the HMAC key, and is cleared at login. The session cookie also uses `Path=/`. `SameSite=Lax` is the policy for both (see ADR-0009, decision 12, corrected). On plain-HTTP local development (`APP_ENV=local` only) the prefix is omitted, because browsers reject `__Host-` cookies without `Secure`.

> This is a design, not an implementation. It will be implemented and tested in PR 4 and PR 5. Until those tests exist, nothing here is verified.

## Consequences

- Instant revocation, and no tokens in JavaScript-readable storage.
- The API cannot be called from other browser origins; a native client would need a new decision.
- Every non-GET frontend call needs the header. The frontend uses one wrapper to enforce this.
