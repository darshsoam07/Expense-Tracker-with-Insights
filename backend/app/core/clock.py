"""Time source. Services receive a Clock instead of reading the wall clock (ADR-0009, decision 11).

Production wires SystemClock; tests wire a fake one. Domain code must never call
datetime.now(), datetime.utcnow() or time.time() itself (a test enforces this).
"""

from datetime import UTC, date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current moment as a timezone-aware UTC datetime."""
        ...

    def today(self) -> date:
        """The current UTC calendar date."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return self.now().date()
