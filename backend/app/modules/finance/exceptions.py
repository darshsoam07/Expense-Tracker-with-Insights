"""Customer-scoped, append-only operational exception investigations."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.modules.audit import AuditWriter

# Transition and close reasons are short operational statements. Notes and resolution
# summaries are the free-text record, so they may be longer. The API and the UI use these.
REASON_MAX = 500
NOTE_MAX = 2000

RULES = {
    "payment_failed": (
        "high",
        "Payment rejected",
        "The simulated rail confirmed payment rejection.",
    ),
    "payment_outcome_unknown": (
        "high",
        "Payment outcome unknown",
        "The simulated rail outcome remains unresolved.",
    ),
    "approval_expired": (
        "medium",
        "Approval expired",
        "The approval request expired before completion.",
    ),
    "settlement_failed": (
        "high",
        "Settlement failed",
        "The payment could not be settled in its batch.",
    ),
    "amount_mismatch": (
        "high",
        "Reconciliation amount mismatch",
        "The statement amount differs from the internal settlement.",
    ),
    "currency_mismatch": (
        "high",
        "Reconciliation currency mismatch",
        "The statement currency differs from the internal settlement.",
    ),
    "missing_internal_record": (
        "high",
        "Missing internal settlement",
        "The statement line has no matching internal settlement.",
    ),
    "missing_statement_record": (
        "medium",
        "Missing statement record",
        "The internal settlement has no matching statement line.",
    ),
    "duplicate_external_reference": (
        "high",
        "Duplicate provider reference",
        "The statement includes a duplicate external reference.",
    ),
    "direction_mismatch": (
        "high",
        "Reconciliation direction mismatch",
        "The statement direction differs from the expected outbound settlement.",
    ),
    "status_mismatch": (
        "medium",
        "Reconciliation status mismatch",
        "The statement status is not settled for an internally settled payment.",
    ),
    "timing_difference": (
        "low",
        "Settlement timing difference",
        "Statement and internal settlement dates differ beyond tolerance.",
    ),
}

# Every reconcile() classification except exact_match must raise an exception. A test keeps this
# list and the classifications emitted by reconcile() from drifting apart.
RECONCILIATION_TYPES = (
    "amount_mismatch",
    "currency_mismatch",
    "missing_internal_record",
    "missing_statement_record",
    "duplicate_external_reference",
    "direction_mismatch",
    "status_mismatch",
    "timing_difference",
)


def _event(
    db: Session,
    ident: UUID,
    kind: str,
    actor: UUID | None,
    now: datetime,
    *,
    previous: str | None = None,
    next_status: str | None = None,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one history row. Ordering is the identity `sequence`, never the timestamp."""
    db.execute(
        text(
            """INSERT INTO ledgerops.exception_events(
            exception_id, kind, actor_id, occurred_at, previous_status, next_status, note, metadata
            ) VALUES(:id,:kind,:actor,:now,:previous,:next,:note,CAST(:metadata AS jsonb))"""
        ),
        {
            "id": ident,
            "kind": kind,
            "actor": actor,
            "now": now,
            "previous": previous,
            "next": next_status,
            "note": note,
            "metadata": json.dumps(metadata or {}),
        },
    )


def generate(
    db: Session,
    customer: UUID,
    domain: str,
    source: UUID,
    kind: str,
    actor: UUID | None,
    now: datetime,
) -> UUID:
    severity, title, description = RULES[kind]
    ident = db.scalar(
        text("""INSERT INTO ledgerops.exceptions(customer_id,source_domain,source_reference,
        exception_type,severity,status,title,description,created_at,updated_at)
        VALUES(:customer,:domain,:source,:kind,:severity,'open',:title,:description,:now,:now)
        ON CONFLICT(source_domain,source_reference,exception_type) DO NOTHING RETURNING id"""),
        {
            "customer": customer,
            "domain": domain,
            "source": source,
            "kind": kind,
            "severity": severity,
            "title": title,
            "description": description,
            "now": now,
        },
    )
    if ident is not None:
        _event(db, ident, "created", actor, now, next_status="open")
    return (
        UUID(str(ident))
        if ident
        else UUID(
            str(
                db.scalar(
                    text("""SELECT id FROM ledgerops.exceptions
        WHERE source_domain=:domain AND source_reference=:source AND exception_type=:kind"""),
                    {"domain": domain, "source": source, "kind": kind},
                )
            )
        )
    )


_SCOPED = """SELECT e.*,u.display_name AS assigned_name FROM ledgerops.exceptions e
    JOIN ledgerops.customer_members m ON m.customer_id=e.customer_id
    LEFT JOIN ledgerops.users u ON u.id=e.assigned_user_id
    WHERE e.id=:id AND m.user_id=:actor AND m.active AND (NOT :manage OR m.role<>'viewer')"""
# Locks only the exception row (the nullable side of the outer join cannot be locked).
_SCOPED_LOCKED = _SCOPED + " FOR UPDATE OF e"


def _scoped(
    db: Session, actor: UUID, ident: UUID, manage: bool = False, lock: bool = False
) -> dict[str, Any]:
    """Read one exception the actor may see. `lock=True` takes the row lock for the unit of work.

    Concurrent lifecycle or assignment requests then queue on this row. The second request
    re-reads the committed row once it is released, so it validates against current state.
    """
    row = (
        db.execute(
            text(_SCOPED_LOCKED if lock else _SCOPED),
            {"id": ident, "actor": actor, "manage": manage},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AppError(404, "exception_not_found", "Exception unavailable.")
    return dict(row)


# One statement returns the page and the total, so both come from the same snapshot.
# When the offset is past the end the join still yields one row carrying the total.
_QUEUE = """
WITH queue AS (
  SELECT e.id,e.reference,e.customer_id,e.exception_type,e.severity,e.status,e.source_domain,
    e.source_reference,e.assigned_user_id,u.display_name AS assigned_name,e.created_at,
    e.updated_at,e.title
  FROM ledgerops.exceptions e
  JOIN ledgerops.customer_members m ON m.customer_id=e.customer_id
  LEFT JOIN ledgerops.users u ON u.id=e.assigned_user_id
  WHERE m.user_id=:actor AND m.active
    AND (CAST(:status AS text) IS NULL OR e.status=CAST(:status AS text))
    AND (CAST(:severity AS text) IS NULL OR e.severity=CAST(:severity AS text))
    AND (CAST(:exception_type AS text) IS NULL OR e.exception_type=CAST(:exception_type AS text))
    AND (CAST(:source_domain AS text) IS NULL OR e.source_domain=CAST(:source_domain AS text))
    AND (CAST(:assigned_user_id AS uuid) IS NULL
         OR e.assigned_user_id=CAST(:assigned_user_id AS uuid))
    AND (CAST(:customer_id AS uuid) IS NULL OR e.customer_id=CAST(:customer_id AS uuid))
    AND (CAST(:created_after AS timestamptz) IS NULL
         OR e.created_at >= CAST(:created_after AS timestamptz))
    AND (CAST(:created_before AS timestamptz) IS NULL
         OR e.created_at < CAST(:created_before AS timestamptz))
)
SELECT (SELECT count(*) FROM queue) AS total, p.*
FROM (SELECT 1) AS anchor
LEFT JOIN (SELECT * FROM queue ORDER BY created_at DESC,id LIMIT :limit OFFSET :offset) p ON true
ORDER BY p.created_at DESC NULLS LAST,p.id
"""

_FILTERS = (
    "status",
    "severity",
    "exception_type",
    "source_domain",
    "assigned_user_id",
    "customer_id",
    "created_after",
    "created_before",
)


def page(
    db: Session, actor: UUID, limit: int, offset: int, filters: dict[str, Any]
) -> dict[str, Any]:
    params: dict[str, Any] = {"actor": actor, "limit": limit, "offset": offset}
    params.update({name: filters.get(name) for name in _FILTERS})
    rows = db.execute(text(_QUEUE), params).mappings().all()
    items = [
        {key: value for key, value in row.items() if key != "total"}
        for row in rows
        if row["id"] is not None
    ]
    return {"items": items, "total": int(rows[0]["total"]), "limit": limit, "offset": offset}


def assignees(db: Session, actor: UUID, ident: UUID) -> list[dict[str, Any]]:
    """Members who could take this exception. Never reaches outside the exception's customer."""
    row = _scoped(db, actor, ident, manage=True)
    return [
        dict(item)
        for item in db.execute(
            text("""SELECT u.id,u.display_name FROM ledgerops.customer_members m
            JOIN ledgerops.users u ON u.id=m.user_id
            WHERE m.customer_id=:customer AND m.active AND m.role<>'viewer'
            ORDER BY u.display_name,u.id"""),
            {"customer": row["customer_id"]},
        ).mappings()
    ]


def detail(db: Session, actor: UUID, ident: UUID) -> dict[str, Any]:
    row = _scoped(db, actor, ident)
    row["events"] = [
        dict(event)
        for event in db.execute(
            text("""SELECT x.id,x.kind,x.actor_id,x.occurred_at,x.previous_status,x.next_status,
            x.note,x.metadata,u.display_name AS actor_name
            FROM ledgerops.exception_events x LEFT JOIN ledgerops.users u ON u.id=x.actor_id
            WHERE x.exception_id=:id ORDER BY x.sequence"""),
            {"id": ident},
        ).mappings()
    ]
    return row


def _audit(
    db: Session, audit: AuditWriter, actor: UUID, action: str, ident: UUID, request: str | None
) -> None:
    audit.record(
        db,
        principal=Principal.user(actor),
        action=action,
        target_type="exception",
        target_id=str(ident),
        request_id=request,
    )


def assign(
    db: Session, actor: UUID, ident: UUID, assigned: UUID, audit: AuditWriter, request: str | None
) -> dict[str, Any]:
    """Assign or reassign. Serialised per exception; the status change, history row and audit
    record commit together or not at all."""
    row = _scoped(db, actor, ident, manage=True, lock=True)
    if row["status"] == "closed":
        raise AppError(409, "exception_closed", "A closed exception cannot be reassigned.")
    candidate = db.execute(
        text(
            """SELECT u.display_name FROM ledgerops.customer_members m
            JOIN ledgerops.users u ON u.id=m.user_id
            WHERE m.customer_id=:customer AND m.user_id=:assigned AND m.active
            AND m.role<>'viewer'"""
        ),
        {"customer": row["customer_id"], "assigned": assigned},
    ).first()
    if candidate is None:
        raise AppError(422, "invalid_assignee", "Assignee must have active workspace membership.")
    if row["assigned_user_id"] == assigned:
        db.commit()  # nothing to change: release the lock without a history row or audit noise
        return detail(db, actor, ident)
    now = audit.clock.now()
    # The runtime role cannot lock membership rows, so the same statement re-checks membership.
    # A membership revoked mid-request is then refused instead of silently assigned.
    changed = db.scalar(
        text("""UPDATE ledgerops.exceptions SET assigned_user_id=:assigned, updated_at=:now
        WHERE id=:id AND EXISTS(SELECT 1 FROM ledgerops.customer_members
          WHERE customer_id=:customer AND user_id=:assigned AND active AND role<>'viewer')
        RETURNING id"""),
        {"assigned": assigned, "now": now, "id": ident, "customer": row["customer_id"]},
    )
    if changed is None:
        raise AppError(422, "invalid_assignee", "Assignee must have active workspace membership.")
    _event(
        db,
        ident,
        "assigned" if row["assigned_user_id"] is None else "reassigned",
        actor,
        now,
        metadata={
            "assigned_user_id": str(assigned),
            "assigned_name": candidate[0],  # a snapshot: history must not change if the name does
            "previous_assigned_user_id": str(row["assigned_user_id"])
            if row["assigned_user_id"]
            else None,
        },
    )
    _audit(db, audit, actor, "exception.assigned", ident, request)
    db.commit()
    return detail(db, actor, ident)


TRANSITIONS = {
    "open": {"investigating", "awaiting_information"},
    "investigating": {"awaiting_information", "resolved"},
    "awaiting_information": {"investigating"},
    "resolved": {"closed"},
    "closed": set(),
}


def transition(
    db: Session,
    actor: UUID,
    ident: UUID,
    status: str,
    reason: str,
    audit: AuditWriter,
    request: str | None,
) -> dict[str, Any]:
    """Apply one lifecycle transition against the status read under the row lock."""
    reason = reason.strip()
    limit = NOTE_MAX if status == "resolved" else REASON_MAX
    if len(reason) > limit:
        raise AppError(422, "reason_too_long", f"Keep the reason within {limit} characters.")
    row = _scoped(db, actor, ident, manage=True, lock=True)
    if status not in TRANSITIONS.get(row["status"], set()):
        raise AppError(
            409, "invalid_exception_transition", "Exception transition is not permitted."
        )
    if status in {"awaiting_information", "resolved", "closed"} and not reason:
        raise AppError(422, "reason_required", "Enter an operational reason.")
    now = audit.clock.now()
    changed = db.scalar(
        text("""UPDATE ledgerops.exceptions SET status=:status,updated_at=:now,
        resolution_summary=CASE WHEN :status='resolved' THEN :reason ELSE resolution_summary END,
        resolved_at=CASE WHEN :status='resolved' THEN :now ELSE resolved_at END,
        closed_at=CASE WHEN :status='closed' THEN :now ELSE closed_at END
        WHERE id=:id AND status=:previous RETURNING id"""),
        {"status": status, "now": now, "reason": reason, "id": ident, "previous": row["status"]},
    )
    if changed is None:  # unreachable while the row lock is held; guards against a missed lock
        raise AppError(409, "exception_changed", "The exception changed. Refresh and retry.")
    _event(
        db,
        ident,
        "status_changed" if status != "resolved" else "resolved",
        actor,
        now,
        previous=row["status"],
        next_status=status,
        note=reason or None,
    )
    _audit(db, audit, actor, "exception." + status, ident, request)
    db.commit()
    return detail(db, actor, ident)


def note(
    db: Session, actor: UUID, ident: UUID, body: str, audit: AuditWriter, request: str | None
) -> dict[str, Any]:
    _scoped(db, actor, ident, manage=True)
    body = body.strip()
    if not body:
        raise AppError(422, "note_required", "Enter a note.")
    if len(body) > NOTE_MAX:
        raise AppError(422, "note_too_long", f"Keep the note within {NOTE_MAX} characters.")
    now = audit.clock.now()
    _event(db, ident, "note_added", actor, now, note=body)
    _audit(db, audit, actor, "exception.note_added", ident, request)
    db.commit()
    return detail(db, actor, ident)
