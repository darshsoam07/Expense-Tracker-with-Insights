"""Resolve the effective internal-transfer policy for a source customer."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError


@dataclass(frozen=True)
class PolicyRevision:
    id: UUID
    version: int
    required_count: int
    ttl_seconds: int | None


def match_policy(
    db: Session, customer: UUID, amount: Decimal, currency: str, now: datetime
) -> PolicyRevision | None:
    rows = db.execute(
        text("""
            WITH effective AS (
                SELECT DISTINCT ON (id) *
                FROM ledgerops.approval_policies
                WHERE customer_id=:customer AND recorded_at<=:now
                ORDER BY id,version DESC
            )
            SELECT id,version,required_count,ttl_seconds FROM effective
            WHERE active AND currency=:currency AND minimum<=:amount
              AND (maximum IS NULL OR maximum>=:amount)
            LIMIT 2
        """),
        {"customer": customer, "amount": amount, "currency": currency, "now": now},
    ).all()
    if len(rows) > 1:
        raise AppError(409, "approval_policy_overlap", "Multiple transfer policies match.")
    if not rows:
        return None
    row = rows[0]
    return PolicyRevision(row.id, row.version, row.required_count, row.ttl_seconds)
