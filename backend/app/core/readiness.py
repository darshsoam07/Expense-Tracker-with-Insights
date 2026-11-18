"""Readiness: "can this instance safely receive traffic right now?"

The application factory registers database and schema compatibility alongside process startup.
"""

import logging
from collections.abc import Callable

logger = logging.getLogger("app.readiness")


class ReadinessRegistry:
    def __init__(self) -> None:
        self._started = False
        self._stopping = False
        self._checks: dict[str, Callable[[], bool]] = {"app_started": self._app_is_serving}

    def _app_is_serving(self) -> bool:
        return self._started and not self._stopping

    def mark_started(self) -> None:
        self._started = True
        self._stopping = False

    def mark_stopping(self) -> None:
        self._stopping = True

    def register(self, name: str, check: Callable[[], bool]) -> None:
        if name in self._checks:
            raise ValueError(f"readiness check {name!r} is already registered")
        self._checks[name] = check

    def run(self) -> dict[str, bool]:
        """Run every check. A check that raises counts as failed; its error stays in the logs."""
        results: dict[str, bool] = {}
        for name, check in self._checks.items():
            try:
                results[name] = bool(check())
            except Exception:
                logger.warning("readiness.check_error", extra={"check": name}, exc_info=True)
                results[name] = False
        return results
