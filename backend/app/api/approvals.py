from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api import API_V1_PREFIX
from app.api.deps import AppClock, DbSession, request_id_of, require_permission
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession
from app.modules.finance import approvals, holds

router = APIRouter(prefix=f"{API_V1_PREFIX}/approvals", tags=["approvals"])
Reader = Annotated[ActiveSession, Depends(require_permission("approvals.read"))]
Reviewer = Annotated[ActiveSession, Depends(require_permission("approvals.decide"))]


class Decision(BaseModel):
    reason: Annotated[str, Field(min_length=1, max_length=256)]


@router.get("")
def queue(
    db: DbSession,
    active: Reader,
    clock: AppClock,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, object]]:
    holds.refresh(db, active.user_id, None, AuditWriter(clock), request_id_of(request))
    rows = approvals.page(db, active.user_id, limit, offset)
    db.commit()
    return rows


@router.get("/{approval}")
def detail(approval: UUID, db: DbSession, active: Reader) -> dict[str, object]:
    return approvals.detail(db, active.user_id, approval)


@router.post("/{approval}/{decision}")
def decide(
    approval: UUID,
    decision: Literal["approve", "reject"],
    body: Decision,
    request: Request,
    db: DbSession,
    active: Reviewer,
    clock: AppClock,
) -> dict[str, object]:
    return approvals.decide(
        db,
        active.user_id,
        approval,
        decision,
        body.reason.strip(),
        AuditWriter(clock),
        request_id_of(request),
    )
