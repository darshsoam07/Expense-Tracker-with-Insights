from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api import API_V1_PREFIX
from app.api.deps import AppClock, DbSession, request_id_of, require_permission
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession
from app.modules.finance import payments

router = APIRouter(prefix=f"{API_V1_PREFIX}/payments", tags=["payments"])
Creator = Annotated[ActiveSession, Depends(require_permission("payments.create"))]
Reader = Annotated[ActiveSession, Depends(require_permission("payments.read"))]
Submitter = Annotated[ActiveSession, Depends(require_permission("payments.submit"))]
Canceller = Annotated[ActiveSession, Depends(require_permission("payments.cancel"))]


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    beneficiary_name: Annotated[str, Field(min_length=1, max_length=128)]
    destination_reference: Annotated[str, Field(min_length=1, max_length=128)]
    customer_reference: Annotated[str, Field(min_length=1, max_length=128)]
    currency: Literal["INR"]
    amount: Annotated[str, Field(strict=True, pattern=r"^(0|[1-9][0-9]{0,15})(.[0-9]{1,2})?$")]


@router.post("", status_code=201)
def create(
    body: PaymentInput,
    request: Request,
    response: Response,
    active: Creator,
    db: DbSession,
    clock: AppClock,
    idempotency_key: Annotated[
        str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    ],
) -> dict[str, object]:
    result, created = payments.create(
        db,
        active.user_id,
        body.source_id,
        body.beneficiary_name.strip(),
        body.destination_reference.strip(),
        Decimal(body.amount),
        body.customer_reference.strip(),
        idempotency_key,
        AuditWriter(clock),
        request_id_of(request),
    )
    response.status_code = 201 if created else 200
    return result


@router.get("")
def listing(
    db: DbSession,
    active: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, object]]:
    return payments.page(db, active.user_id, limit, offset)


@router.get("/{payment}")
def detail(payment: UUID, db: DbSession, active: Reader) -> dict[str, object]:
    return payments.detail(db, active.user_id, payment)


@router.post("/{payment}/submit")
def submit(
    payment: UUID, request: Request, db: DbSession, active: Submitter, clock: AppClock
) -> dict[str, object]:
    return payments.submit(db, active.user_id, payment, AuditWriter(clock), request_id_of(request))


@router.post("/{payment}/cancel")
def cancel(
    payment: UUID, request: Request, db: DbSession, active: Canceller, clock: AppClock
) -> dict[str, object]:
    return payments.cancel(db, active.user_id, payment, AuditWriter(clock), request_id_of(request))
