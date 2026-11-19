"""Customer-scoped INR reservations."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.api import API_V1_PREFIX
from app.api.deps import AppClock, DbSession, request_id_of, require_permission
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession
from app.modules.finance import holds

router = APIRouter(prefix=API_V1_PREFIX, tags=["holds"])
Reader = Annotated[ActiveSession, Depends(require_permission("holds.read"))]
Creator = Annotated[ActiveSession, Depends(require_permission("holds.create"))]
Releaser = Annotated[ActiveSession, Depends(require_permission("holds.release"))]
Key = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
]
Money = Annotated[str, Field(strict=True, pattern=r"^(0|[1-9][0-9]{0,15})(\.[0-9]{1,2})?$")]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


class CreateHold(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    amount: Money
    currency: Literal["INR"]
    reason: Annotated[str, Field(min_length=1, max_length=256)]
    business_reference: Annotated[str, Field(max_length=128)] | None = None
    expires_at: AwareDatetime | None = None


class ReleaseHold(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: Literal["INR"]
    amount: Money | None = None


@router.post("/accounts/{account_id}/holds", status_code=201)
def create(
    account_id: UUID,
    body: CreateHold,
    active: Creator,
    db: DbSession,
    clock: AppClock,
    request: Request,
    response: Response,
    key: Key,
) -> dict[str, object]:
    result, created = holds.change(
        db,
        active.user_id,
        account_id,
        None,
        Decimal(body.amount),
        key,
        AuditWriter(clock),
        request_id_of(request),
        reason=body.reason,
        reference=body.business_reference,
        expires=body.expires_at,
    )
    db.commit()
    response.status_code = 201 if created else 200
    return result


@router.get("/accounts/{account_id}/holds")
def listing(
    account_id: UUID,
    active: Reader,
    db: DbSession,
    clock: AppClock,
    request: Request,
    limit: Limit = 25,
    offset: Offset = 0,
) -> list[dict[str, object]]:
    holds.refresh(db, active.user_id, account_id, AuditWriter(clock), request_id_of(request))
    result = holds.page(db, account_id, limit, offset)
    db.commit()
    return result


@router.get("/holds/{hold_id}")
def get(
    hold_id: UUID,
    active: Reader,
    db: DbSession,
    clock: AppClock,
    request: Request,
    limit: Limit = 25,
    offset: Offset = 0,
) -> dict[str, object]:
    account = holds.locate(db, active.user_id, hold_id)
    holds.refresh(db, active.user_id, account, AuditWriter(clock), request_id_of(request))
    result = holds.detail(db, hold_id)
    result["events"] = [
        dict(row)
        for row in db.execute(
            text("""
        SELECT id,kind,amount::text,remaining::text,currency,occurred_at,journal_id
        FROM ledgerops.hold_events WHERE hold_id=:id ORDER BY remaining ASC
        LIMIT :limit OFFSET :offset
    """),
            {"id": hold_id, "limit": limit, "offset": offset},
        ).mappings()
    ]
    db.commit()
    return result


@router.post("/holds/{hold_id}/release")
def release(
    hold_id: UUID,
    body: ReleaseHold,
    active: Releaser,
    db: DbSession,
    clock: AppClock,
    request: Request,
    key: Key,
) -> dict[str, object]:
    account = holds.locate(db, active.user_id, hold_id)
    result, _ = holds.change(
        db,
        active.user_id,
        account,
        hold_id,
        Decimal(body.amount) if body.amount is not None else None,
        key,
        AuditWriter(clock),
        request_id_of(request),
    )
    db.commit()
    return result
