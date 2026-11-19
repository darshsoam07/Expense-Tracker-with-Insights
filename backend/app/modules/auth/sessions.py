"""Server-side sessions stored in PostgreSQL (ADR-0001, ADR-0005).

The browser holds a random token. The database stores only its SHA-256 hash. Idle timeout and
absolute lifetime are both evaluated against the injected Clock.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.security import hash_session_token, new_csrf_value, new_session_token
from app.db.tables import sessions, users

# Do not write on every request: refresh last_seen_at at most this often.
TOUCH_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_id: UUID
    token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ActiveSession:
    session_id: UUID
    user_id: UUID
    email: str
    display_name: str
    csrf_token: str
    expires_at: datetime
    last_seen_at: datetime


class SessionService:
    def __init__(self, clock: Clock, idle_timeout: timedelta, absolute_lifetime: timedelta) -> None:
        self._clock = clock
        self._idle = idle_timeout
        self._absolute = absolute_lifetime

    def create(self, db: Session, user_id: UUID) -> IssuedSession:
        """Always a brand-new token and CSRF value, which prevents session fixation."""
        now = self._clock.now()
        token = new_session_token()
        csrf_token = new_csrf_value()
        expires_at = now + self._absolute
        session_id = db.execute(
            insert(sessions)
            .values(
                user_id=user_id,
                token_hash=hash_session_token(token),
                csrf_token=csrf_token,
                created_at=now,
                last_seen_at=now,
                expires_at=expires_at,
            )
            .returning(sessions.c.id)
        ).scalar_one()
        return IssuedSession(session_id, token, csrf_token, expires_at)

    def resolve(self, db: Session, token: str) -> ActiveSession | None:
        """Return the live session for a cookie value, or None for any kind of invalid one."""
        row = db.execute(
            select(
                sessions.c.id,
                sessions.c.user_id,
                sessions.c.csrf_token,
                sessions.c.expires_at,
                sessions.c.last_seen_at,
                sessions.c.revoked_at,
                users.c.email,
                users.c.display_name,
                users.c.status,
            )
            .join(users, users.c.id == sessions.c.user_id)
            .where(sessions.c.token_hash == hash_session_token(token))
        ).one_or_none()
        if row is None:
            return None
        now = self._clock.now()
        if row.revoked_at is not None or row.status != "active":
            return None
        if now >= row.expires_at or now - row.last_seen_at > self._idle:
            return None
        return ActiveSession(
            session_id=row.id,
            user_id=row.user_id,
            email=row.email,
            display_name=row.display_name,
            csrf_token=row.csrf_token,
            expires_at=row.expires_at,
            last_seen_at=row.last_seen_at,
        )

    def touch(self, db: Session, active: ActiveSession) -> bool:
        """Refresh last_seen_at when stale. The caller commits. Returns True if it wrote."""
        now = self._clock.now()
        if now - active.last_seen_at < TOUCH_INTERVAL:
            return False
        db.execute(
            update(sessions).where(sessions.c.id == active.session_id).values(last_seen_at=now)
        )
        return True

    def revoke(self, db: Session, session_id: UUID) -> None:
        db.execute(
            update(sessions)
            .where(sessions.c.id == session_id, sessions.c.revoked_at.is_(None))
            .values(revoked_at=self._clock.now())
        )
