"""Authenticated internal transfers."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api import API_V1_PREFIX
from app.api.deps import AppClock, DbSession, request_id_of, require_permission
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession
from app.modules.finance import transfers

router = APIRouter(prefix=f"{API_V1_PREFIX}/transfers", tags=["transfers"])
Creator = Annotated[ActiveSession, Depends(require_permission("transfers.create"))]
Reader = Annotated[ActiveSession, Depends(require_permission("accounts.read"))]


class TransferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    destination_id: UUID
    currency: Literal["INR"]
    amount: Annotated[str, Field(strict=True, pattern=r"^(0|[1-9][0-9]{0,15})(\.[0-9]{1,2})?$")]
    description: Annotated[str, Field(max_length=256)] = ""


@router.post("", status_code=201)
def create_transfer(
    body: TransferInput,
    request: Request,
    response: Response,
    active: Creator,
    db: DbSession,
    clock: AppClock,
    idempotency_key: Annotated[
        str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    ],
) -> dict[str, object]:
    result, created = transfers.transfer(
        db,
        active.user_id,
        body.source_id,
        body.destination_id,
        Decimal(body.amount),
        body.description.strip(),
        idempotency_key,
        AuditWriter(clock),
        request_id_of(request),
    )
    response.status_code = 201 if created else 200
    return result


@router.get("")
def list_transfers(
    db: DbSession,
    active: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, object]]:
    return transfers.history(db, active.user_id, limit, offset)
