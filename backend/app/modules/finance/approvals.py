"""Scoped review of reserved internal transfers."""

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.modules.audit import AuditWriter
from app.modules.auth.rbac import effective_permissions
from app.modules.finance import exceptions, holds, payments
from app.modules.finance.transfers import payload_hash, post_transfer

SCOPED = """
 SELECT r.id,r.subject_id,r.maker,u.display_name AS maker_name,r.customer_id,r.source_id,
 r.destination_id,r.amount::text,r.currency,r.description,r.status,r.created_at,r.expires_at,
 r.policy_id,r.policy_version,p.required_count,r.hold_id,h.status AS hold_status
 FROM ledgerops.approval_requests r
 JOIN ledgerops.approval_policies p ON (p.id,p.version)=(r.policy_id,r.policy_version)
 JOIN ledgerops.users u ON u.id=r.maker JOIN ledgerops.account_holds h ON h.id=r.hold_id
 JOIN ledgerops.accounts s ON s.id=r.source_id AND s.customer_id=r.customer_id
 LEFT JOIN ledgerops.accounts d ON d.id=r.destination_id
 JOIN ledgerops.customer_members sm ON sm.customer_id=s.customer_id AND sm.active
 LEFT JOIN ledgerops.customer_members dm ON dm.customer_id=d.customer_id AND dm.active
   AND dm.user_id=:actor
 WHERE sm.user_id=:actor AND (r.subject_type='payment' OR dm.user_id IS NOT NULL)
"""


def detail(db: Session, actor: UUID, approval: UUID) -> dict[str, Any]:
    params = {"actor": actor, "id": approval}
    row = db.execute(text(SCOPED + " AND r.id=:id"), params).mappings().one_or_none()
    if row is None:
        raise AppError(404, "approval_not_found", "Approval unavailable.")
    decisions = db.execute(
        text("""SELECT actor,decision,reason,decided_at
        FROM ledgerops.approval_decisions WHERE request_id=:id ORDER BY decided_at,actor"""),
        params,
    ).mappings()
    return {**row, "decisions": [dict(d) for d in decisions]}


def page(db: Session, actor: UUID, limit: int, offset: int) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in db.execute(
            text(
                SCOPED
                + """ AND r.status='pending_approval'
        ORDER BY r.created_at,r.id LIMIT :limit OFFSET :offset"""
            ),
            {"actor": actor, "limit": limit, "offset": offset},
        ).mappings()
    ]


def decide(
    db: Session,
    actor: UUID,
    approval: UUID,
    decision: Literal["approve", "reject"],
    reason: str,
    audit: AuditWriter,
    request_id: str | None,
) -> dict[str, Any]:
    if "approvals.decide" not in effective_permissions(db, actor):
        raise AppError(403, "forbidden", "Approval permission required.")
    try:
        request = detail(db, actor, approval)
        accounts = {
            a.id: a
            for a in db.execute(
                text("""SELECT a.id,a.ledger_id,a.status,a.currency,
            m.active,m.role FROM ledgerops.accounts a
            JOIN ledgerops.account_balances b USING(ledger_id)
            LEFT JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
                AND m.user_id=:maker
            WHERE a.id IN (:source_id,:destination_id) ORDER BY a.id FOR UPDATE OF b"""),
                request,
            )
        }
        r = db.execute(
            text("SELECT * FROM ledgerops.approval_requests WHERE id=:id FOR UPDATE"),
            {"id": approval},
        ).one()
        if r.status != "pending_approval":
            raise AppError(409, "approval_terminal", "Approval has already finished.")
        now = audit.clock.now()
        params = {
            "id": approval,
            "actor": actor,
            "maker": r.maker,
            "reason": reason,
            "decision": decision,
            "now": now,
            "correlation": request_id,
        }
        expired = r.expires_at is not None and r.expires_at <= now
        status = "pending_approval"
        if expired:
            status = "expired"
        else:
            if actor == r.maker:
                raise AppError(403, "self_decision", "A different reviewer must decide.")
            if not reason.strip():
                raise AppError(422, "reason_required", "Enter a decision reason.")
            added = db.scalar(
                text("""INSERT INTO ledgerops.approval_decisions
                VALUES(:id,:maker,:actor,:decision,:reason,:now) ON CONFLICT DO NOTHING
                RETURNING actor"""),
                params,
            )
            if added is None:
                raise AppError(409, "duplicate_decision", "You already decided this request.")
            count = db.scalar(
                text("""SELECT count(*) FROM ledgerops.approval_decisions
                WHERE request_id=:id AND decision='approve'"""),
                params,
            )
            if decision == "reject":
                status = "rejected"
            elif count == request["required_count"]:
                status = "approved"
        if status != "pending_approval":
            hold = holds.detail(db, r.hold_id)
            if hold["account_id"] != r.source_id or Decimal(hold["remaining"]) != r.amount:
                raise AppError(409, "reservation_changed", "Reservation no longer matches.")
            if status == "approved" and r.subject_type == "payment":
                payments.approve(db, r.subject_id, r.payload_hash, actor, now, request_id)
            elif status == "approved":
                if (
                    r.currency != "INR"
                    or payload_hash(
                        r.source_id, r.destination_id, r.amount, r.description, r.original_hold_id
                    )
                    != r.payload_hash
                    or any(
                        a.status != "active" or a.currency != r.currency or not a.active
                        for a in accounts.values()
                    )
                    or accounts[r.source_id].role == "viewer"
                ):
                    raise AppError(409, "intent_changed", "Transfer cannot be posted.")
                post_transfer(
                    db,
                    r.maker,
                    r.source_id,
                    accounts[r.source_id].ledger_id,
                    accounts[r.destination_id].ledger_id,
                    r.amount,
                    r.description,
                    r.idempotency_key,
                    r.payload_hash,
                    r.destination_id,
                    r.subject_id,
                    r.hold_id,
                    now,
                    audit,
                    request_id,
                )
            else:
                if not holds.append_event(
                    db,
                    audit,
                    request_id,
                    hold=r.hold_id,
                    account=r.source_id,
                    kind="released",
                    amount=r.amount,
                    remaining=Decimal(0),
                    actor=r.maker if expired else actor,
                    now=now,
                    command="release",
                    key=f"approval/{approval}",
                    digest=r.payload_hash,
                    reason="Approval expired" if expired else reason,
                ):
                    raise AppError(409, "release_conflict", "Reservation release conflicted.")
                if r.subject_type == "payment":
                    db.execute(
                        text("""INSERT INTO ledgerops.payment_events
                        SELECT gen_random_uuid(),id,'cancelled',:actor,:now,provider_reference,
                        :reason,:correlation FROM ledgerops.payment_instructions WHERE id=:payment
                        """),
                        {
                            **params,
                            "payment": r.subject_id,
                            "actor": None if expired else actor,
                            "reason": "Approval expired" if expired else reason,
                        },
                    )
            db.execute(
                text("""UPDATE ledgerops.approval_requests SET status=:status,
                completed_at=:now WHERE id=:id"""),
                {**params, "status": status},
            )
        kind = "decision" if status == "pending_approval" else status
        db.execute(
            text("""INSERT INTO ledgerops.approval_events
            VALUES(:event,:id,:kind,:actor,:now,:correlation)"""),
            {**params, "event": uuid4(), "kind": kind, "actor": None if expired else actor},
        )
        audit.record(
            db,
            principal=Principal.system("approval-expiry") if expired else Principal.user(actor),
            action=f"approval.{kind}",
            target_type="approval_request",
            target_id=str(approval),
            request_id=request_id,
            reason="Approval expired" if expired else reason,
        )
        if expired:
            exceptions.generate(
                db, r.customer_id, "approval", approval, "approval_expired", None, now
            )
    except Exception:
        db.rollback()
        raise
    result = detail(db, actor, approval)
    db.commit()
    if expired:
        raise AppError(
            409, "approval_expired", "Approval expired and the reservation was released."
        )
    return result
