"""Reserved payment instructions submitted to a deterministic simulated rail."""

import hashlib
import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.modules.audit import AuditWriter
from app.modules.finance import holds
from app.modules.finance.approval_policies import match_policy
from app.modules.finance.payment_rails import Rail, SimulatedRail

SELECT = """SELECT p.id,p.customer_id,p.source_id,p.actor_id,p.customer_reference,
 p.beneficiary_name,p.destination_reference,p.amount::text,p.currency,p.rail,p.status,
 p.hold_id,p.approval_id,r.status AS approval_status,p.provider_reference,p.created_at,p.updated_at
 FROM ledgerops.payment_instructions p LEFT JOIN ledgerops.approval_requests r
 ON r.id=p.approval_id"""


def payload_hash(
    source: UUID, beneficiary: str, destination: str, amount: Decimal, customer_reference: str
) -> str:
    payload = [
        str(source),
        beneficiary,
        destination,
        format(amount, ".2f"),
        "INR",
        "SIMULATED_INR",
        customer_reference,
    ]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def _scoped(db: Session, actor: UUID, payment: UUID, lock: bool = False) -> Any:
    if lock:
        # Approval decisions and expiry also lock the balance before the instruction.
        db.execute(
            text("""SELECT b.ledger_id FROM ledgerops.payment_instructions p
                JOIN ledgerops.accounts a ON a.id=p.source_id
                JOIN ledgerops.account_balances b ON b.ledger_id=a.ledger_id
                JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
                WHERE p.id=:id AND m.user_id=:actor AND m.active AND m.role<>'viewer'
                FOR UPDATE OF b"""),
            {"id": payment, "actor": actor},
        )
    suffix = " AND m.role<>'viewer' FOR UPDATE OF p" if lock else ""
    row = (
        db.execute(
            text(
                SELECT
                + """ JOIN ledgerops.accounts a ON a.id=p.source_id
        JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
        WHERE p.id=:id AND m.user_id=:actor AND m.active"""
                + suffix
            ),
            {"id": payment, "actor": actor},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AppError(404, "payment_not_found", "Payment unavailable.")
    return row


def detail(db: Session, actor: UUID, payment: UUID) -> dict[str, Any]:
    row = dict(_scoped(db, actor, payment))
    row["events"] = [
        dict(e)
        for e in db.execute(
            text("""SELECT id,kind,actor,occurred_at,
        provider_reference,detail,correlation_id FROM ledgerops.payment_events
        WHERE payment_id=:id ORDER BY occurred_at,id"""),
            {"id": payment},
        ).mappings()
    ]
    return row


def page(db: Session, actor: UUID, limit: int, offset: int) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in db.execute(
            text(
                SELECT
                + """ JOIN ledgerops.accounts a
      ON a.id=p.source_id JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
      WHERE m.user_id=:actor AND m.active ORDER BY p.created_at DESC,p.id
      LIMIT :limit OFFSET :offset"""
            ),
            {"actor": actor, "limit": limit, "offset": offset},
        ).mappings()
    ]


def _event(
    db: Session,
    payment: UUID,
    kind: str,
    actor: UUID | None,
    now: Any,
    request_id: str | None,
    provider: str,
    detail_text: str,
) -> None:
    db.execute(
        text("""INSERT INTO ledgerops.payment_events
        VALUES(:id,:payment,:kind,:actor,:now,:provider,:detail,:request)"""),
        {
            "id": uuid4(),
            "payment": payment,
            "kind": kind,
            "actor": actor,
            "now": now,
            "provider": provider,
            "detail": detail_text,
            "request": request_id,
        },
    )


def create(
    db: Session,
    actor: UUID,
    source: UUID,
    beneficiary: str,
    destination: str,
    amount: Decimal,
    customer_reference: str,
    key: str,
    audit: AuditWriter,
    request_id: str | None,
) -> tuple[dict[str, Any], bool]:
    if (
        amount <= 0
        or amount >= Decimal("1e16")
        or not amount.is_finite()
        or amount != amount.quantize(Decimal(".01"))
    ):
        raise AppError(
            422, "invalid_amount", "Use a positive INR amount with at most two decimals."
        )
    digest = payload_hash(source, beneficiary, destination, amount, customer_reference)
    try:
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": f"payment:{actor}:{key}"},
        )
        existing = db.execute(
            text("""SELECT id,payload_hash FROM ledgerops.payment_instructions
            WHERE actor_id=:actor AND idempotency_key=:key"""),
            {"actor": actor, "key": key},
        ).one_or_none()
        if existing:
            if existing.payload_hash != digest:
                raise AppError(409, "idempotency_conflict", "This key belongs to another payment.")
            return detail(db, actor, existing.id), False
        account = db.execute(
            text("""SELECT a.id,a.customer_id,a.status,a.currency,m.role,
            b.available_balance FROM ledgerops.accounts a JOIN ledgerops.account_balances b
            USING(ledger_id) JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
            WHERE a.id=:source AND m.user_id=:actor AND m.active FOR UPDATE OF b"""),
            {"source": source, "actor": actor},
        ).one_or_none()
        if account is None or account.role == "viewer":
            raise AppError(404, "account_not_found", "Account unavailable.")
        if account.status != "active" or account.currency != "INR":
            raise AppError(409, "account_unavailable", "Source must be an active INR account.")
        now = audit.clock.now()
        expired = holds.expire_locked(db, source, now, audit, request_id)
        available = account.available_balance
        if expired:
            available = db.execute(
                text("""SELECT available_balance FROM ledgerops.accounts
                JOIN ledgerops.account_balances USING(ledger_id) WHERE id=:id"""),
                {"id": source},
            ).scalar_one()
        if available < amount:
            raise AppError(409, "insufficient_funds", "Available balance is insufficient.")
        payment, hold = uuid4(), uuid4()
        provider = "sim_" + hashlib.sha256(str(payment).encode()).hexdigest()[:24]
        policy = match_policy(db, account.customer_id, amount, "INR", now)
        status = "pending_approval" if policy else "ready_for_submission"
        holds.append_event(
            db,
            audit,
            request_id,
            hold=hold,
            account=source,
            kind="created",
            amount=amount,
            remaining=amount,
            now=now,
            actor=actor,
            command="create",
            key=f"payment/{payment}",
            digest=digest,
            reason="External payment instruction",
            reference=customer_reference,
        )
        db.execute(
            text("""INSERT INTO ledgerops.payment_instructions
          (id,customer_id,source_id,actor_id,customer_reference,beneficiary_name,
           destination_reference,amount,currency,rail,status,hold_id,idempotency_key,
           payload_hash,provider_reference,created_at,updated_at)
          VALUES(:id,:customer,:source,:actor,:reference,:beneficiary,:destination,:amount,
           'INR','SIMULATED_INR',:status,:hold,:key,:digest,:provider,:now,:now)"""),
            {
                "id": payment,
                "customer": account.customer_id,
                "source": source,
                "actor": actor,
                "reference": customer_reference,
                "beneficiary": beneficiary,
                "destination": destination,
                "amount": amount,
                "status": status,
                "hold": hold,
                "key": key,
                "digest": digest,
                "provider": provider,
                "now": now,
            },
        )
        _event(
            db,
            payment,
            "created",
            actor,
            now,
            request_id,
            provider,
            "Payment instruction created on the simulated INR rail.",
        )
        if policy:
            approval = uuid4()
            db.execute(
                text("""INSERT INTO ledgerops.approval_requests
              (id,subject_type,subject_id,maker,customer_id,policy_id,policy_version,source_id,
               destination_id,amount,currency,description,payload_hash,idempotency_key,hold_id,
               created_at,expires_at,status)
              VALUES(:approval,'payment',:payment,:actor,:customer,:policy,:version,:source,
               NULL,:amount,'INR',:description,:digest,:approval_key,:hold,:now,
               CASE WHEN :ttl IS NULL THEN NULL ELSE :now+make_interval(secs=>:ttl) END,
               'pending_approval')"""),
                {
                    "approval": approval,
                    "payment": payment,
                    "actor": actor,
                    "customer": account.customer_id,
                    "policy": policy.id,
                    "version": policy.version,
                    "source": source,
                    "amount": amount,
                    "description": customer_reference,
                    "digest": digest,
                    "approval_key": f"payment/{key}",
                    "hold": hold,
                    "now": now,
                    "ttl": policy.ttl_seconds,
                },
            )
            db.execute(
                text("""UPDATE ledgerops.payment_instructions SET approval_id=:approval
                WHERE id=:payment"""),
                {"approval": approval, "payment": payment},
            )
            db.execute(
                text("""INSERT INTO ledgerops.approval_events
                VALUES(:event,:approval,'requested',:actor,:now,:request)"""),
                {
                    "event": uuid4(),
                    "approval": approval,
                    "actor": actor,
                    "now": now,
                    "request": request_id,
                },
            )
        audit.record(
            db,
            principal=Principal.user(actor),
            action="payment.created",
            target_type="payment",
            target_id=str(payment),
            request_id=request_id,
        )
        db.commit()
        return detail(db, actor, payment), True
    except Exception:
        db.rollback()
        raise


def submit(
    db: Session,
    actor: UUID,
    payment: UUID,
    audit: AuditWriter,
    request_id: str | None,
    rail: Rail | None = None,
) -> dict[str, Any]:
    try:
        row = _scoped(db, actor, payment, True)
        if row.status in {"accepted", "failed"}:
            return detail(db, actor, payment)
        if row.status not in {"ready_for_submission", "outcome_unknown"}:
            raise AppError(409, "invalid_payment_state", "Payment cannot be submitted.")
        now = audit.clock.now()
        if row.status == "ready_for_submission":
            _event(
                db,
                payment,
                "submitted",
                actor,
                now,
                request_id,
                row.provider_reference,
                "Submitted to the simulated INR rail.",
            )
        result = (rail or SimulatedRail()).submit(row.provider_reference)
        if result.outcome == "temporary_unavailable":
            if row.status == "outcome_unknown":
                db.rollback()
                raise AppError(503, "rail_unavailable", result.detail)
            _event(
                db,
                payment,
                "retry_ready",
                actor,
                now,
                request_id,
                row.provider_reference,
                result.detail,
            )
            audit.record(
                db,
                principal=Principal.user(actor),
                action="payment.retry_deferred",
                target_type="payment",
                target_id=str(payment),
                request_id=request_id,
            )
            db.commit()
            raise AppError(503, "rail_unavailable", result.detail)
        kind = {"accepted": "accepted", "rejected": "failed", "timeout": "outcome_unknown"}[
            result.outcome
        ]
        if kind == row.status == "outcome_unknown":
            db.commit()
            return detail(db, actor, payment)
        _event(db, payment, kind, actor, now, request_id, row.provider_reference, result.detail)
        if kind == "failed":
            holds.append_event(
                db,
                audit,
                request_id,
                hold=row.hold_id,
                account=row.source_id,
                kind="released",
                amount=Decimal(row.amount),
                remaining=Decimal(0),
                now=now,
                actor=actor,
                command="release",
                key=f"payment/{payment}/failed",
                digest=hashlib.sha256(row.provider_reference.encode()).hexdigest(),
                reason="Simulated rail rejection",
            )
        audit.record(
            db,
            principal=Principal.user(actor),
            action=f"payment.{kind}",
            target_type="payment",
            target_id=str(payment),
            request_id=request_id,
        )
        db.commit()
        return detail(db, actor, payment)
    except AppError as exc:
        if exc.code != "rail_unavailable":
            db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def approve(
    db: Session, payment: UUID, expected_hash: str, actor: UUID, now: Any, request_id: str | None
) -> None:
    row = db.execute(
        text("SELECT * FROM ledgerops.payment_instructions WHERE id=:id FOR UPDATE"),
        {"id": payment},
    ).one()
    actual = payload_hash(
        row.source_id,
        row.beneficiary_name,
        row.destination_reference,
        row.amount,
        row.customer_reference,
    )
    if (
        row.status != "pending_approval"
        or actual != expected_hash
        or row.payload_hash != expected_hash
    ):
        raise AppError(409, "intent_changed", "Payment instruction cannot be approved.")
    _event(
        db,
        payment,
        "approved",
        actor,
        now,
        request_id,
        row.provider_reference,
        "Independent approval completed; ready for simulated submission.",
    )


def cancel(
    db: Session, actor: UUID, payment: UUID, audit: AuditWriter, request_id: str | None
) -> dict[str, Any]:
    try:
        row = _scoped(db, actor, payment, True)
        if row.status not in {"pending_approval", "ready_for_submission"}:
            raise AppError(409, "invalid_payment_state", "Payment can no longer be cancelled.")
        now = audit.clock.now()
        _event(
            db,
            payment,
            "cancelled",
            actor,
            now,
            request_id,
            row.provider_reference,
            "Cancelled before simulated rail acceptance.",
        )
        holds.append_event(
            db,
            audit,
            request_id,
            hold=row.hold_id,
            account=row.source_id,
            kind="released",
            amount=Decimal(row.amount),
            remaining=Decimal(0),
            now=now,
            actor=actor,
            command="release",
            key=f"payment/{payment}/cancel",
            digest=hashlib.sha256(row.provider_reference.encode()).hexdigest(),
            reason="Payment cancelled",
        )
        if row.approval_id:
            db.execute(
                text("""UPDATE ledgerops.approval_requests SET status='rejected',
                completed_at=:now WHERE id=:id AND status='pending_approval'"""),
                {"id": row.approval_id, "now": now},
            )
        audit.record(
            db,
            principal=Principal.user(actor),
            action="payment.cancelled",
            target_type="payment",
            target_id=str(payment),
            request_id=request_id,
        )
        db.commit()
        return detail(db, actor, payment)
    except Exception:
        db.rollback()
        raise
