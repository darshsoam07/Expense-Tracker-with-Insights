"""Pure security helpers: password hashing, opaque tokens and CSRF tokens. No database access.

Design (ADR-0001, ADR-0005):
  * Passwords use Argon2id. Verification of an unknown user runs against a dummy hash so the
    response time does not reveal whether an account exists.
  * Session tokens are random and opaque. Only their SHA-256 hash is stored.
  * Before login, CSRF uses a signed double-submit pair: a cookie value `r` and a header
    token HMAC(csrf_key, r). After login the per-session csrf_token is compared instead.
"""

import hashlib
import hmac
import secrets
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

SESSION_COOKIE = "ledgerops_session"
ANONYMOUS_CSRF_COOKIE = "ledgerops_csrf"
CSRF_HEADER = "X-CSRF-Token"
ANONYMOUS_CSRF_MAX_AGE_SECONDS = 3600
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256

_hasher = PasswordHasher()  # argon2-cffi defaults: Argon2id, RFC 9106 low-memory profile
_dummy_hash: str | None = None


def cookie_name(base: str, *, secure: bool) -> str:
    """`__Host-` forces Secure, Path=/ and no Domain. Browsers reject it over plain HTTP."""
    return f"__Host-{base}" if secure else base


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def burn_password_verification(password: str) -> None:
    """Spend the same time as a real verification (used when the account does not exist)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hasher.hash(secrets.token_urlsafe(16))
    verify_password(_dummy_hash, password)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


def new_csrf_value() -> str:
    return secrets.token_urlsafe(32)


def equal_constant_time(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _csrf_key(secret_key: str) -> bytes:
    return hmac.new(secret_key.encode("utf-8"), b"ledgerops-csrf-v1", hashlib.sha256).digest()


def issue_anonymous_csrf(secret_key: str, now: datetime) -> tuple[str, str]:
    """Return (cookie_value, header_token) for a visitor who has no session yet."""
    cookie_value = f"{int(now.timestamp())}.{secrets.token_urlsafe(32)}"
    return cookie_value, _anonymous_token(secret_key, cookie_value)


def _anonymous_token(secret_key: str, cookie_value: str) -> str:
    return hmac.new(_csrf_key(secret_key), cookie_value.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_anonymous_csrf(
    secret_key: str, cookie_value: str | None, header_token: str | None, now: datetime
) -> bool:
    if not cookie_value or not header_token:
        return False
    issued_text, _, _ = cookie_value.partition(".")
    if not issued_text.isdigit():
        return False
    age = now.timestamp() - int(issued_text)
    if age < 0 or age > ANONYMOUS_CSRF_MAX_AGE_SECONDS:
        return False
    return equal_constant_time(_anonymous_token(secret_key, cookie_value), header_token)
