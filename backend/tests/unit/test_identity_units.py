"""Pure unit tests: clock, security helpers, principals, policy, and the no-wall-clock rule."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.clock import SystemClock
from app.core.principal import ANONYMOUS, Principal
from app.core.security import (
    ANONYMOUS_CSRF_MAX_AGE_SECONDS,
    cookie_name,
    hash_password,
    hash_session_token,
    issue_anonymous_csrf,
    new_session_token,
    password_needs_rehash,
    verify_anonymous_csrf,
    verify_password,
)
from app.modules.auth.policy import ROLE_PERMISSIONS, Permission, Role, as_permission
from tests.helpers import FakeClock

SECRET = "x" * 40


def test_fake_clock_only_moves_when_advanced() -> None:
    clock = FakeClock()
    first = clock.now()
    assert clock.now() == first
    clock.advance(timedelta(hours=1))
    assert clock.now() - first == timedelta(hours=1)
    assert clock.today() == first.date()


def test_system_clock_returns_aware_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_password_hashing_is_argon2id_and_verifies() -> None:
    hashed = hash_password("a long enough password")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "a long enough password")
    assert not verify_password(hashed, "another password")
    assert not verify_password("not-a-hash", "a long enough password")
    assert not password_needs_rehash(hashed)


def test_session_tokens_are_unique_and_hashes_are_32_bytes() -> None:
    assert new_session_token() != new_session_token()
    assert len(hash_session_token("abc")) == 32


def test_cookie_name_prefix_depends_on_secure_flag() -> None:
    assert cookie_name("s", secure=True) == "__Host-s"
    assert cookie_name("s", secure=False) == "s"


def test_anonymous_csrf_accepts_matching_pair_and_rejects_tampering() -> None:
    now = datetime(2026, 11, 18, 12, tzinfo=UTC)
    cookie, token = issue_anonymous_csrf(SECRET, now)
    assert verify_anonymous_csrf(SECRET, cookie, token, now)
    assert not verify_anonymous_csrf(SECRET, cookie, token + "0", now)
    assert not verify_anonymous_csrf(SECRET, cookie + "x", token, now)
    assert not verify_anonymous_csrf("y" * 40, cookie, token, now)
    assert not verify_anonymous_csrf(SECRET, None, token, now)
    assert not verify_anonymous_csrf(SECRET, cookie, None, now)
    assert not verify_anonymous_csrf(SECRET, "garbage", token, now)


def test_anonymous_csrf_expires_and_rejects_future_issue_times() -> None:
    now = datetime(2026, 11, 18, 12, tzinfo=UTC)
    cookie, token = issue_anonymous_csrf(SECRET, now)
    late = now + timedelta(seconds=ANONYMOUS_CSRF_MAX_AGE_SECONDS + 1)
    assert not verify_anonymous_csrf(SECRET, cookie, token, late)
    assert not verify_anonymous_csrf(SECRET, cookie, token, now - timedelta(minutes=5))


def test_principals() -> None:
    assert ANONYMOUS.value == "anonymous"
    assert ANONYMOUS.user_id is None
    assert Principal.system("outbox-worker").value == "system:outbox-worker"
    with pytest.raises(ValueError, match="system principal"):
        Principal.system("Bad Name")


def test_policy_is_consistent() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)
    assert as_permission("audit.read") is Permission.AUDIT_READ
    with pytest.raises(ValueError, match="unknown permission"):
        as_permission("nope.nope")


def test_application_code_never_reads_the_wall_clock_directly() -> None:
    """Only app/core/clock.py may call the system time (ADR-0009, decision 11)."""
    pattern = re.compile(r"datetime\.(now|utcnow)\(|date\.today\(|time\.time\(|time\.monotonic\(")
    root = Path(__file__).resolve().parents[2] / "app"
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path.name != "clock.py" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
