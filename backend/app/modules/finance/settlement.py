"""Capture an accepted outbound instruction inside its settlement item's transaction."""

from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.modules.audit import AuditWriter
from app.modules.finance import holds
from app.modules.finance.nostro import NOSTRO
from app.modules.finance.posting import Line, post


def settle(
    db: Session, payment: UUID, actor: UUID, audit: AuditWriter, request_id: str | None
) -> UUID:
    row = db.execute(
        text("""SELECT p.customer_id,p.source_id,p.amount,p.hold_id,p.status,a.ledger_id
        FROM ledgerops.payment_instructions p JOIN ledgerops.accounts a ON a.id=p.source_id
        JOIN ledgerops.customer_members m ON m.customer_id=p.customer_id
        WHERE p.id=:payment AND m.user_id=:actor AND m.active AND m.role<>'viewer'
        """),
        {"payment": payment, "actor": actor},
    ).one_or_none()
    if row is None:
        raise AppError(404, "payment_not_found", "Payment unavailable.")
    if row.status != "accepted":
        raise AppError(409, "not_accepted", "Only accepted payments can settle.")
    cash = db.scalar(
        text("""SELECT b.ledger_balance FROM ledgerops.account_balances b
        JOIN ledgerops.ledger_accounts l ON l.id=b.ledger_id WHERE l.id=:id AND l.code='1010'
        AND l.active FOR UPDATE OF b"""),
        {"id": NOSTRO},
    )
    existing = db.scalar(
        text("SELECT journal_id FROM ledgerops.settlement_items WHERE payment_id=:id"),
        {"id": payment},
    )
    if existing is not None:
        return UUID(str(existing))
    if cash is None or cash < row.amount:
        raise AppError(409, "insufficient_nostro", "Insufficient platform settlement funds.")
    db.execute(
        text("SELECT ledger_id FROM ledgerops.account_balances WHERE ledger_id=:id FOR UPDATE"),
        {"id": row.ledger_id},
    )
    remaining = db.scalar(
        text("""SELECT remaining FROM ledgerops.account_holds
        WHERE id=:hold AND account_id=:source"""),
        {"hold": row.hold_id, "source": row.source_id},
    )
    if remaining != row.amount:
        raise AppError(
            409, "reservation_mismatch", "Payment reservation must match the settlement."
        )
    journal = uuid5(payment, "outbound-settlement")
    now = audit.clock.now()
    db.execute(
        text("""INSERT INTO ledgerops.settlement_items
        (payment_id,customer_id,journal_id,settled_at,actor_id)
        VALUES (:payment,:customer,:journal,:now,:actor)"""),
        {
            "payment": payment,
            "customer": row.customer_id,
            "journal": journal,
            "now": now,
            "actor": actor,
        },
    )
    holds.append_event(
        db,
        audit,
        request_id,
        hold=row.hold_id,
        account=row.source_id,
        kind="captured",
        amount=row.amount,
        remaining=Decimal(0),
        now=now,
        actor=actor,
        command="capture",
        journal=journal,
    )
    principal = Principal.user(actor)
    post(
        db,
        journal,
        f"Outbound settlement {payment}",
        (Line(row.ledger_id, row.amount, Decimal(0)), Line(NOSTRO, Decimal(0), row.amount)),
        principal,
        audit,
        request_id,
    )
    audit.record(
        db,
        principal=principal,
        action="payment.settled",
        target_type="payment",
        target_id=str(payment),
        request_id=request_id,
        metadata={"journal_id": str(journal), "customer_id": str(row.customer_id)},
    )
    return journal
