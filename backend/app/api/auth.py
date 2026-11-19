"""Authentication endpoints: CSRF bootstrap, login and logout under /api/v1/auth, and the
current user at GET /api/v1/me (ADR-0001, Phase 1 plan). All paths use the versioned prefix.
"""

from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api import API_V1_PREFIX
from app.api.deps import (
    AppClock,
    AppSettings,
    CurrentSession,
    DbSession,
    OptionalSession,
    build_auth_service,
    csrf_cookie_name,
    request_id_of,
    session_cookie_name,
)
from app.core.config import Settings
from app.core.security import (
    ANONYMOUS_CSRF_MAX_AGE_SECONDS,
    MAX_PASSWORD_LENGTH,
    issue_anonymous_csrf,
)
from app.modules.auth.rbac import effective_permissions, roles_for_user

router = APIRouter(prefix=f"{API_V1_PREFIX}/auth", tags=["auth"])
# ADR-0001 and the Phase 1 plan define the current-user endpoint as GET /api/v1/me.
me_router = APIRouter(prefix=API_V1_PREFIX, tags=["auth"])

_NO_STORE = {"Cache-Control": "no-store"}


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]


class AuthState(BaseModel):
    user: UserOut
    csrf_token: str


class CsrfOut(BaseModel):
    csrf_token: str


def _set_cookie(
    response: Response, settings: Settings, name: str, value: str, max_age: int
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_cookie(response: Response, settings: Settings, name: str) -> None:
    response.delete_cookie(
        name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )


@router.get("/csrf", response_model=CsrfOut)
def csrf(response: Response, settings: AppSettings, clock: AppClock) -> CsrfOut:
    """Issue the anonymous CSRF pair used before login (ADR-0001)."""
    cookie_value, token = issue_anonymous_csrf(settings.secret_key.get_secret_value(), clock.now())
    _set_cookie(
        response, settings, csrf_cookie_name(settings), cookie_value, ANONYMOUS_CSRF_MAX_AGE_SECONDS
    )
    response.headers.update(_NO_STORE)
    return CsrfOut(csrf_token=token)


@router.post("/login", response_model=AuthState)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    existing: OptionalSession,
) -> AuthState:
    result = build_auth_service(settings, clock).login(
        db,
        email=body.email,
        password=body.password,
        request_id=request_id_of(request),
        replacing=existing,
    )
    lifetime = int((result.session.expires_at - clock.now()).total_seconds())
    _set_cookie(response, settings, session_cookie_name(settings), result.session.token, lifetime)
    _clear_cookie(response, settings, csrf_cookie_name(settings))
    response.headers.update(_NO_STORE)
    return AuthState(
        user=UserOut(
            id=result.user_id,
            email=result.email,
            display_name=result.display_name,
            roles=roles_for_user(db, result.user_id),
            permissions=sorted(effective_permissions(db, result.user_id)),
        ),
        csrf_token=result.session.csrf_token,
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    active: CurrentSession,
) -> Response:
    build_auth_service(settings, clock).logout(db, active, request_id_of(request))
    response = Response(status_code=204, headers=_NO_STORE)
    _clear_cookie(response, settings, session_cookie_name(settings))
    return response


@me_router.get("/me", response_model=AuthState)
def me(response: Response, db: DbSession, active: CurrentSession) -> AuthState:
    response.headers.update(_NO_STORE)
    return AuthState(
        user=UserOut(
            id=active.user_id,
            email=active.email,
            display_name=active.display_name,
            roles=roles_for_user(db, active.user_id),
            permissions=sorted(effective_permissions(db, active.user_id)),
        ),
        csrf_token=active.csrf_token,
    )
