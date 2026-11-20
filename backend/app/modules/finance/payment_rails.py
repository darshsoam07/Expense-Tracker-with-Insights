"""A deterministic, network-free payment rail."""

from dataclasses import dataclass
from typing import Literal, Protocol

RailOutcome = Literal["accepted", "rejected", "temporary_unavailable", "timeout"]


@dataclass(frozen=True)
class RailResult:
    outcome: RailOutcome
    detail: str


class Rail(Protocol):
    def submit(self, provider_reference: str) -> RailResult: ...


class SimulatedRail:
    """Stable default outcome with an injectable result for automated tests."""

    def __init__(self, outcome: RailOutcome = "accepted") -> None:
        self._outcome = outcome

    def submit(self, provider_reference: str) -> RailResult:
        messages = {
            "accepted": "Accepted by the simulated INR rail; settlement is pending.",
            "rejected": "Rejected by the simulated INR rail.",
            "temporary_unavailable": "The simulated INR rail is temporarily unavailable.",
            "timeout": "The simulated rail outcome is unknown after a timeout.",
        }
        return RailResult(self._outcome, messages[self._outcome])
