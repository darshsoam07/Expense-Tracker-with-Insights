"""Scoped financial reads. Money is returned using PostgreSQL's exact decimal text."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError

ACCOUNT_QUERY = """
SELECT a.id, a.reference, a.account_type, a.customer_id, c.name AS customer_name,
       a.currency, a.status, a.created_at, b.updated_at, b.ledger_balance::text AS ledger_balance,
       b.available_balance::text AS available_balance
FROM ledgerops.accounts a JOIN ledgerops.customers c ON c.id=a.customer_id
JOIN ledgerops.customer_members m ON m.customer_id=c.id
JOIN ledgerops.account_balances b ON b.ledger_id=a.ledger_id
WHERE m.user_id=:actor AND m.active
"""


def accounts(db: Session, actor: UUID) -> list[dict[str, object]]:
    rows = db.execute(text(ACCOUNT_QUERY + " ORDER BY a.created_at,a.id"), {"actor": actor})
    return [dict(row) for row in rows.mappings()]


def account(db: Session, actor: UUID, account_id: UUID) -> dict[str, object]:
    row = (
        db.execute(text(ACCOUNT_QUERY + " AND a.id=:id"), {"actor": actor, "id": account_id})
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AppError(404, "account_not_found", "Account unavailable.")
    return dict(row)


def activity(
    db: Session, actor: UUID, account_id: UUID, limit: int, offset: int
) -> list[dict[str, object]]:
    account(db, actor, account_id)
    rows = db.execute(
        text("""
        SELECT p.id,j.reference,j.description,j.posted_at,p.currency,
               CASE WHEN debit>0 THEN 'debit' ELSE 'credit' END AS direction,
               greatest(debit,credit)::text AS amount
        FROM ledgerops.journal_postings p JOIN ledgerops.journal_entries j ON j.id=p.journal_id
        JOIN ledgerops.accounts a ON a.ledger_id=p.ledger_id
        JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
        WHERE a.id=:id AND m.active AND m.user_id=:actor AND j.status='posted'
        ORDER BY j.posted_at DESC,p.id LIMIT :limit OFFSET :offset
    """),
        {"id": account_id, "actor": actor, "limit": limit, "offset": offset},
    )
    return [dict(row) for row in rows.mappings()]
