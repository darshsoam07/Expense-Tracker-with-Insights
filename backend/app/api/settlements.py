"""Scoped simulation operations; upload bodies are bounded while streaming."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api import API_V1_PREFIX
from app.api.deps import AppClock, DbSession, request_id_of, require_permission
from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession
from app.modules.finance import operations as ops
from app.modules.finance.statements import MAX_BYTES

router = APIRouter(prefix=f"{API_V1_PREFIX}/settlements", tags=["settlements"])
Read = Annotated[ActiveSession, Depends(require_permission("ledger.read"))]
Write = Annotated[ActiveSession, Depends(require_permission("payments.submit"))]
Kind = Literal["batches", "statements", "reconciliation-runs"]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


class Workspace(BaseModel):
    customer_id: UUID


class Run(BaseModel):
    import_id: UUID


@router.post("/batches", status_code=201)
def create_batch(
    body: Workspace, actor: Write, db: DbSession, clock: AppClock, request: Request
) -> dict[str, Any]:
    return ops.batch(
        db, body.customer_id, actor.user_id, AuditWriter(clock), request_id_of(request)
    )


@router.post("/batches/{ident}/process")
def process(
    ident: UUID, actor: Write, db: DbSession, clock: AppClock, request: Request
) -> dict[str, Any]:
    return ops.process(db, ident, actor.user_id, AuditWriter(clock), request_id_of(request))


@router.post("/statements/import")
async def ingest(
    customer_id: UUID, filename: str, actor: Write, db: DbSession, clock: AppClock, request: Request
) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";")[0] != "text/csv":
        raise AppError(415, "invalid_media_type", "Upload UTF-8 text/csv.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_BYTES:
            raise AppError(413, "statement_too_large", "Statement exceeds 256 KiB.")
        content.extend(chunk)
    return ops.ingest(
        db,
        customer_id,
        actor.user_id,
        filename,
        bytes(content),
        AuditWriter(clock),
        request_id_of(request),
    )


@router.post("/reconciliation-runs", status_code=201)
def reconcile(
    body: Run, actor: Write, db: DbSession, clock: AppClock, request: Request
) -> dict[str, Any]:
    return ops.reconcile(
        db, body.import_id, actor.user_id, AuditWriter(clock), request_id_of(request)
    )


@router.get("/{kind}")
def listing(
    kind: Kind, actor: Read, db: DbSession, limit: Limit = 25, offset: Offset = 0
) -> list[dict[str, Any]]:
    return ops.records(db, kind, actor.user_id, limit=limit, offset=offset)


@router.get("/{kind}/{ident}")
def detail(kind: Kind, ident: UUID, actor: Read, db: DbSession) -> dict[str, Any]:
    return ops.detail(db, kind, actor.user_id, ident)


@router.get("/{kind}/{ident}/items")
def items(
    kind: Kind, ident: UUID, actor: Read, db: DbSession, limit: Limit = 25, offset: Offset = 0
) -> list[dict[str, Any]]:
    return ops.children(db, kind, actor.user_id, ident, limit, offset)
