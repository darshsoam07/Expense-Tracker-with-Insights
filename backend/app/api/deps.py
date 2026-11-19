"""Request-scoped dependencies: database session, clock, authentication, CSRF and RBAC.

`enforce_csrf` is installed on the whole application, so a new state-changing route cannot
forget it. `require_permission(...)` is declared per route.
"""

import logging
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.principal import Principal
from app.core.security import (
    ANONYMOUS_CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    cookie_name,
    equal_constant_time,
    verify_anonymous_csrf,
)
from app.db import open_session, sessions
from app.modules.audit import AuditWriter
from app.modules.auth.policy import as_permission
from app.modules.auth.rbac import effective_permissions
from app.modules.auth.service import AuthPolicy, AuthService
from app.modules.auth.sessions import ActiveSession, SessionService

logger = logging.getLogger("app.auth")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_db(request: Request) -> Iterator[Session]:
    engine = request.app.state.engine
    if engine is None:
        raise AppError(503, "database_unavailable", "The database is not available.")
    yield from sessions(engine)


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
AppClock = Annotated[Clock, Depends(get_clock)]


def build_session_service(settings: Settings, clock: Clock) -> SessionService:
    return SessionService(
        clock,
        timedelta(minutes=settings.session_idle_minutes),
        timedelta(hours=settings.session_absolute_hours),
    )


def build_auth_service(settings: Settings, clock: Clock) -> AuthService:
    return AuthService(
        clock,
        build_session_service(settings, clock),
        AuditWriter(clock),
        AuthPolicy(
            max_failed_logins=settings.login_max_failures,
            lock_duration=timedelta(minutes=settings.login_lock_minutes),
        ),
    )


def session_cookie_name(settings: Settings) -> str:
    return cookie_name(SESSION_COOKIE, secure=settings.cookie_secure)


def csrf_cookie_name(settings: Settings) -> str:
    return cookie_name(ANONYMOUS_CSRF_COOKIE, secure=settings.cookie_secure)


def request_id_of(request: Request) -> str | None:
    value: str | None = getattr(request.state, "request_id", None)
    return value


def _resolve_cookie_session(
    request: Request, db: Session, settings: Settings, clock: Clock
) -> ActiveSession | None:
    token = request.cookies.get(session_cookie_name(settings))
    if not token:
        return None
    service = build_session_service(settings, clock)
    active = service.resolve(db, token)
    if active is not None and service.touch(db, active):
        db.commit()
    return active


def get_optional_session(
    request: Request, db: DbSession, settings: AppSettings, clock: AppClock
) -> ActiveSession | None:
    return _resolve_cookie_session(request, db, settings, clock)


OptionalSession = Annotated[ActiveSession | None, Depends(get_optional_session)]


def get_current_session(active: OptionalSession) -> ActiveSession:
    if active is None:
        raise AppError(401, "not_authenticated", "Authentication is required.")
    return active


CurrentSession = Annotated[ActiveSession, Depends(get_current_session)]


def _origin_is_allowed(request: Request, settings: Settings) -> bool:
    """Defence in depth (ADR-0001): the Origin, or else the Referer, must be our own site.

    A request carrying neither is accepted here because the CSRF token is the primary control.
    """
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer is None:
            return True
        parts = urlsplit(referer)
        origin = f"{parts.scheme}://{parts.netloc}"
    own = f"{request.url.scheme}://{request.url.netloc}"
    return origin == own or origin in settings.allowed_origins


def _csrf_failure(request: Request, active: ActiveSession | None, clock: Clock) -> AppError:
    logger.warning("auth.csrf_failed", extra={"path": request.url.path})
    engine = request.app.state.engine
    if active is not None and engine is not None:
        # Own short transaction: the rejected request has no business change to join.
        with open_session(engine) as db:
            AuditWriter(clock).record(
                db,
                principal=Principal.user(active.user_id),
                action="auth.csrf.failed",
                outcome="denied",
                request_id=request_id_of(request),
                metadata={"method": request.method, "path": request.url.path},
            )
            db.commit()
    return AppError(403, "csrf_failed", "The request could not be verified.")


def enforce_csrf(request: Request) -> None:
    """Reject state-changing requests without a valid CSRF token and an acceptable Origin."""
    if request.method in SAFE_METHODS:
        return
    settings = get_settings(request)
    clock = get_clock(request)
    engine = request.app.state.engine
    active: ActiveSession | None = None
    if engine is not None and request.cookies.get(session_cookie_name(settings)):
        with open_session(engine) as db:
            active = _resolve_cookie_session(request, db, settings, clock)
    if not _origin_is_allowed(request, settings):
        raise _csrf_failure(request, active, clock)
    header = request.headers.get(CSRF_HEADER)
    if active is not None:
        if header and equal_constant_time(header, active.csrf_token):
            return
        raise _csrf_failure(request, active, clock)
    cookie_value = request.cookies.get(csrf_cookie_name(settings))
    if verify_anonymous_csrf(
        settings.secret_key.get_secret_value(), cookie_value, header, clock.now()
    ):
        return
    raise _csrf_failure(request, None, clock)


def require_permission(code: str) -> Callable[..., ActiveSession]:
    """Dependency factory: `Depends(require_permission("audit.read"))`.

    The code is validated against the permission catalogue immediately, so a typo fails at
    import time. A denied request is audited and answered with 403.
    """
    permission = as_permission(code)

    def dependency(
        request: Request, active: CurrentSession, db: DbSession, clock: AppClock
    ) -> ActiveSession:
        if permission.value in effective_permissions(db, active.user_id):
            return active
        AuditWriter(clock).record(
            db,
            principal=Principal.user(active.user_id),
            action="authz.permission_denied",
            outcome="denied",
            request_id=request_id_of(request),
            metadata={"permission": permission.value, "path": request.url.path},
        )
        db.commit()
        raise AppError(403, "forbidden", "You do not have permission to perform this action.")

    return dependency
