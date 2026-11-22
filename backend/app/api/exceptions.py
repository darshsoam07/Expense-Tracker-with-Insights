"""Operational exception investigation endpoints."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api import API_V1_PREFIX
from app.api.deps import AppClock, DbSession, request_id_of, require_permission
from app.modules.audit import AuditWriter
from app.modules.auth.sessions import ActiveSession
from app.modules.finance import exceptions

router = APIRouter(prefix=f"{API_V1_PREFIX}/exceptions", tags=["exceptions"])
Reader = Annotated[ActiveSession, Depends(require_permission("exceptions.read"))]
Manager = Annotated[ActiveSession, Depends(require_permission("exceptions.manage"))]


def _day_start(day: date) -> datetime:
    """Midnight UTC, so the created_on filter does not depend on the database session timezone."""
    return datetime.combine(day, time.min, tzinfo=UTC)


class Assignment(BaseModel):
    assigned_user_id: UUID


class Transition(BaseModel):
    status: Annotated[str, Field(pattern="^(investigating|awaiting_information|resolved|closed)$")]
    reason: Annotated[str, Field(max_length=exceptions.REASON_MAX)] = ""


class Note(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=exceptions.NOTE_MAX)]


@router.get("")
def queue(
    db: DbSession,
    active: Reader,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: str | None = None,
    severity: str | None = None,
    exception_type: str | None = None,
    source_domain: str | None = None,
    assigned_user_id: UUID | None = None,
    customer_id: UUID | None = None,
    created_on: date | None = None,
) -> dict[str, Any]:
    return exceptions.page(
        db,
        active.user_id,
        limit,
        offset,
        {
            "status": status,
            "severity": severity,
            "exception_type": exception_type,
            "source_domain": source_domain,
            "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
            "customer_id": str(customer_id) if customer_id else None,
            "created_after": _day_start(created_on) if created_on else None,
            "created_before": _day_start(created_on + timedelta(days=1)) if created_on else None,
        },
    )


@router.get("/{exception}/assignees")
def assignees(exception: UUID, db: DbSession, active: Manager) -> list[dict[str, Any]]:
    return exceptions.assignees(db, active.user_id, exception)


@router.get("/{exception}")
def detail(exception: UUID, db: DbSession, active: Reader) -> dict[str, Any]:
    return exceptions.detail(db, active.user_id, exception)


@router.post("/{exception}/assign")
def assign(
    exception: UUID,
    body: Assignment,
    request: Request,
    db: DbSession,
    active: Manager,
    clock: AppClock,
) -> dict[str, Any]:
    return exceptions.assign(
        db,
        active.user_id,
        exception,
        body.assigned_user_id,
        AuditWriter(clock),
        request_id_of(request),
    )


@router.post("/{exception}/transition")
def transition(
    exception: UUID,
    body: Transition,
    request: Request,
    db: DbSession,
    active: Manager,
    clock: AppClock,
) -> dict[str, Any]:
    return exceptions.transition(
        db,
        active.user_id,
        exception,
        body.status,
        body.reason,
        AuditWriter(clock),
        request_id_of(request),
    )


@router.post("/{exception}/notes")
def note(
    exception: UUID, body: Note, request: Request, db: DbSession, active: Manager, clock: AppClock
) -> dict[str, Any]:
    return exceptions.note(
        db, active.user_id, exception, body.body, AuditWriter(clock), request_id_of(request)
    )


@router.post("/{exception}/resolve")
def resolve(
    exception: UUID, body: Note, request: Request, db: DbSession, active: Manager, clock: AppClock
) -> dict[str, Any]:
    return exceptions.transition(
        db,
        active.user_id,
        exception,
        "resolved",
        body.body,
        AuditWriter(clock),
        request_id_of(request),
    )


@router.post("/{exception}/close")
def close(
    exception: UUID,
    body: Transition,
    request: Request,
    db: DbSession,
    active: Manager,
    clock: AppClock,
) -> dict[str, Any]:
    return exceptions.transition(
        db,
        active.user_id,
        exception,
        "closed",
        body.reason,
        AuditWriter(clock),
        request_id_of(request),
    )
