"""Synchronous internal transfer with persistent actor-scoped replay."""

import hashlib
import json
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.modules.audit import AuditWriter
from app.modules.finance.posting import Line, post

HISTORY = """
SELECT t.id,t.source_id,t.destination_id,t.amount::text AS amount,t.currency,t.status,
       t.created_at,j.reference AS journal_reference
FROM ledgerops.transfers t JOIN ledgerops.journal_entries j ON j.id=t.journal_id
JOIN ledgerops.accounts s ON s.id=t.source_id JOIN ledgerops.accounts d ON d.id=t.destination_id
JOIN ledgerops.customer_members sm ON sm.customer_id=s.customer_id
JOIN ledgerops.customer_members dm ON dm.customer_id=d.customer_id
WHERE sm.active AND dm.active AND sm.user_id=:actor AND dm.user_id=:actor
"""


def history(db: Session, actor: UUID, limit: int, offset: int) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in db.execute(
            text(HISTORY + " ORDER BY t.created_at DESC,t.id LIMIT :limit OFFSET :offset"),
            {"actor": actor, "limit": limit, "offset": offset},
        ).mappings()
    ]


def transfer(
    db: Session,
    actor: UUID,
    source: UUID,
    destination: UUID,
    amount: Decimal,
    description: str,
    key: str,
    audit: AuditWriter,
    request_id: str | None,
) -> tuple[dict[str, object], bool]:
    if source == destination or amount <= 0 or amount != amount.quantize(Decimal(".01")):
        raise AppError(
            422, "invalid_transfer", "Choose different accounts and a positive INR amount."
        )
    payload = json.dumps([str(source), str(destination), format(amount, ".2f"), "INR", description])
    digest = hashlib.sha256(payload.encode()).hexdigest()
    journal = uuid4()
    params = {
        "actor": actor,
        "src": source,
        "dst": destination,
        "key": key,
        "hash": digest,
        "amount": amount,
        "id": uuid4(),
        "journal": journal,
    }
    try:
        # Lock in ledger UUID order even when two transfers have opposite directions.
        locks = db.execute(
            text("""
            SELECT k.ledger_id FROM ledgerops.account_balances k
            JOIN ledgerops.accounts a ON a.ledger_id=k.ledger_id
            JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
            WHERE a.id IN (:src,:dst) AND m.active AND m.user_id=:actor
              AND (a.id<>:src OR m.role<>'viewer')
            ORDER BY k.ledger_id FOR UPDATE OF k
        """),
            params,
        ).all()
        if len(locks) != 2:
            raise AppError(404, "account_not_found", "Account unavailable.")
        inserted = db.execute(
            text("""
            INSERT INTO ledgerops.transfers(id,actor_id,idempotency_key,payload_hash,source_id,
                destination_id,amount,currency,journal_id)
            VALUES (:id,:actor,:key,:hash,:src,:dst,:amount,'INR',:journal)
            ON CONFLICT(actor_id,operation,idempotency_key) DO NOTHING RETURNING id
        """),
            params,
        ).scalar_one_or_none()
        if inserted is None:
            previous = db.execute(
                text("""
                SELECT id,payload_hash FROM ledgerops.transfers WHERE actor_id=:actor
                AND operation='internal_transfer' AND idempotency_key=:key
            """),
                params,
            ).one()
            if previous.payload_hash != digest:
                raise AppError(
                    409, "idempotency_conflict", "This key belongs to a different request."
                )
            params["id"] = previous.id
        else:
            rows = db.execute(
                text("""
                SELECT a.id,a.ledger_id,a.status,a.currency,b.available_balance
                FROM ledgerops.accounts a JOIN ledgerops.account_balances b USING(ledger_id)
                WHERE a.id IN (:src,:dst)
            """),
                params,
            )
            accounts = {row.id: row for row in rows}
            if any(row.status != "active" or row.currency != "INR" for row in accounts.values()):
                raise AppError(
                    409, "account_unavailable", "Both accounts must be active INR accounts."
                )
            if accounts[source].available_balance < amount:
                raise AppError(409, "insufficient_funds", "Available balance is insufficient.")
            zero = Decimal(0)
            post(
                db,
                journal,
                description or "Internal transfer",
                (
                    Line(accounts[source].ledger_id, amount, zero),
                    Line(accounts[destination].ledger_id, zero, amount),
                ),
                Principal.user(actor),
                audit,
                request_id,
            )
            audit.record(
                db,
                principal=Principal.user(actor),
                action="transfer.posted",
                target_type="transfer",
                target_id=str(inserted),
                request_id=request_id,
            )
        result = dict(db.execute(text(HISTORY + " AND t.id=:id"), params).mappings().one())
        db.commit()
        return result, inserted is not None
    except OperationalError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) in {"40P01", "40001", "55P03", "57014"}:
            raise AppError(
                503, "transfer_busy", "Retry the same transfer with its original key."
            ) from exc
        raise
    except Exception:
        db.rollback()
        raise
