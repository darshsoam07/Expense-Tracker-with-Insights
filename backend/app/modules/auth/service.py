"""Login and logout. Every outcome is audited in the same transaction as its state change."""

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import AppError
from app.core.principal import ANONYMOUS, Principal
from app.core.security import (
    burn_password_verification,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.db.tables import users
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession, IssuedSession, SessionService


def invalid_credentials() -> AppError:
    return AppError(401, "invalid_credentials", "Invalid email or password.")


@dataclass(frozen=True, slots=True)
class AuthPolicy:
    max_failed_logins: int
    lock_duration: timedelta


@dataclass(frozen=True, slots=True)
class LoginResult:
    user_id: UUID
    email: str
    display_name: str
    session: IssuedSession


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _email_fingerprint(email: str) -> str:
    """A short hash so audit rows can be correlated without storing attempted addresses."""
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]


class AuthService:
    def __init__(
        self,
        clock: Clock,
        sessions: SessionService,
        audit: AuditWriter,
        policy: AuthPolicy,
    ) -> None:
        self._clock = clock
        self._sessions = sessions
        self._audit = audit
        self._policy = policy

    def login(
        self,
        db: Session,
        *,
        email: str,
        password: str,
        request_id: str | None,
        replacing: ActiveSession | None = None,
    ) -> LoginResult:
        """Authenticate and open a new session, committing the work. Raises a generic 401.

        The response never says whether the account exists, is locked or is disabled; the
        audit row records the real reason.
        """
        email = normalise_email(email)
        now = self._clock.now()
        row = db.execute(
            select(users).where(users.c.email == email).with_for_update()
        ).one_or_none()

        if row is None:
            burn_password_verification(password)
            self._fail(db, ANONYMOUS, email, "unknown_user", request_id)

        principal = Principal.user(row.id)
        locked = row.locked_until is not None and row.locked_until > now
        password_ok = verify_password(row.password_hash, password)

        if row.status != "active":
            self._fail(db, principal, email, "account_disabled", request_id)
        if locked:
            self._fail(db, principal, email, "account_locked", request_id)
        if not password_ok:
            failures = row.failed_login_count + 1
            lock_now = failures >= self._policy.max_failed_logins
            db.execute(
                update(users)
                .where(users.c.id == row.id)
                .values(
                    failed_login_count=failures,
                    locked_until=now + self._policy.lock_duration if lock_now else None,
                    updated_at=now,
                )
            )
            if lock_now:
                self._audit.record(
                    db,
                    principal=principal,
                    action="auth.account.locked",
                    outcome="failure",
                    target_type="user",
                    target_id=str(row.id),
                    request_id=request_id,
                    reason="too_many_failed_logins",
                )
            self._fail(db, principal, email, "wrong_password", request_id)

        values: dict[str, object] = {
            "failed_login_count": 0,
            "locked_until": None,
            "last_login_at": now,
            "updated_at": now,
        }
        if password_needs_rehash(row.password_hash):
            values["password_hash"] = hash_password(password)
        db.execute(update(users).where(users.c.id == row.id).values(**values))
        if replacing is not None:
            self._sessions.revoke(db, replacing.session_id)
        issued = self._sessions.create(db, row.id)
        self._audit.record(
            db,
            principal=principal,
            action="auth.login",
            target_type="session",
            target_id=str(issued.session_id),
            request_id=request_id,
        )
        db.commit()
        return LoginResult(row.id, row.email, row.display_name, issued)

    def logout(self, db: Session, active: ActiveSession, request_id: str | None) -> None:
        self._sessions.revoke(db, active.session_id)
        self._audit.record(
            db,
            principal=Principal.user(active.user_id),
            action="auth.logout",
            target_type="session",
            target_id=str(active.session_id),
            request_id=request_id,
        )
        db.commit()

    def _fail(
        self,
        db: Session,
        principal: Principal,
        email: str,
        reason: str,
        request_id: str | None,
    ) -> NoReturn:
        """Record the failed attempt (this IS the action being audited), commit, then raise."""
        self._audit.record(
            db,
            principal=principal,
            action="auth.login",
            outcome="failure",
            request_id=request_id,
            reason=reason,
            metadata={"email_fingerprint": _email_fingerprint(email)},
        )
        db.commit()
        raise invalid_credentials()
