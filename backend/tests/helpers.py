"""Shared test helpers (plain functions, so tests can import them directly)."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.config import Settings

# Obviously fake, test-only values. Never use real secrets in tests.
TEST_SECRET = "test-only-secret-value-0123456789abcdef"
STRONG_SECRET = "q8Zr2mXv5Lk9Tw3Bn7Hd1Jf4Pc6Sg0Ay"  # 33 varied characters, no placeholder words


def make_settings(**overrides: Any) -> Settings:
    """Valid test settings; never reads a .env file or the real environment's .env."""
    values: dict[str, Any] = {
        "app_env": "test",
        "secret_key": TEST_SECRET,
        "cookie_secure": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def json_lines(text: str) -> list[dict[str, Any]]:
    """Parse captured stdout into log records; every non-empty line must be valid JSON."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class FakeClock:
    """A controllable Clock. Starts at a fixed instant and only moves when told to."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._now.date()

    def advance(self, delta: timedelta) -> None:
        self._now += delta
