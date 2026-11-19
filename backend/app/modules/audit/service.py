"""Transactional audit writer (ADR-0009, decision 10).

`record()` only INSERTs on the caller's Session and never commits. The audit row therefore
commits or rolls back together with the business change it describes: if the audit insert
fails, the exception propagates and the caller's whole transaction is rolled back.
"""

import re
from typing import Any, Literal

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.principal import Principal
from app.db.tables import audit_events

AuditOutcome = Literal["success", "failure", "denied"]

_ACTION = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")


class AuditWriter:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def record(
        self,
        db: Session,
        *,
        principal: Principal,
        action: str,
        outcome: AuditOutcome = "success",
        target_type: str | None = None,
        target_id: str | None = None,
        request_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not _ACTION.fullmatch(action):
            raise ValueError("audit action must look like 'domain.verb' in lower case")
        db.execute(
            insert(audit_events).values(
                occurred_at=self._clock.now(),
                actor_principal=principal.value,
                actor_user_id=principal.user_id,
                action=action,
                outcome=outcome,
                target_type=target_type,
                target_id=target_id,
                request_id=request_id,
                reason=reason,
                metadata=metadata or {},
            )
        )
