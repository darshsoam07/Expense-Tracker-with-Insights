"""Readiness: "can this instance safely receive traffic right now?"

Today (PR 2) there is exactly one check, "app_started": true after startup completes and
false as soon as shutdown begins (so a load balancer can stop sending traffic before the
process exits).

There is NO database check yet. PostgreSQL arrives in PR 3, which will register a database
check here with `register()`. Until then readiness says nothing about any database.
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
