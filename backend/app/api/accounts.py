"""Customer-scoped account and posted activity endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api import API_V1_PREFIX
from app.api.deps import AppClock, DbSession, request_id_of, require_permission
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession
from app.modules.finance import holds, queries

router = APIRouter(prefix=f"{API_V1_PREFIX}/accounts", tags=["accounts"])
AccountReader = Annotated[ActiveSession, Depends(require_permission("accounts.read"))]
LedgerReader = Annotated[ActiveSession, Depends(require_permission("ledger.read"))]


@router.get("")
def list_accounts(
    db: DbSession, active: AccountReader, clock: AppClock, request: Request
) -> list[dict[str, object]]:
    holds.refresh(db, active.user_id, None, AuditWriter(clock), request_id_of(request))
    result = queries.accounts(db, active.user_id)
    db.commit()
    return result


@router.get("/{account_id}")
def get_account(
    account_id: UUID, db: DbSession, active: AccountReader, clock: AppClock, request: Request
) -> dict[str, object]:
    holds.refresh(db, active.user_id, account_id, AuditWriter(clock), request_id_of(request))
    result = queries.account(db, active.user_id, account_id)
    db.commit()
    return result


@router.get("/{account_id}/ledger")
def ledger(
    account_id: UUID,
    db: DbSession,
    active: LedgerReader,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, object]]:
    return queries.activity(db, active.user_id, account_id, limit, offset)
