"""Post and audit a journal inside the caller's transaction."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.principal import Principal
from app.modules.audit import AuditWriter


@dataclass(frozen=True)
class Line:
    ledger: UUID
    debit: Decimal
    credit: Decimal


def post(
    db: Session,
    journal: UUID,
    description: str,
    lines: tuple[Line, ...],
    actor: Principal,
    audit: AuditWriter,
    request_id: str | None,
) -> None:
    if len(lines) < 2 or sum(line.debit for line in lines) != sum(line.credit for line in lines):
        raise ValueError("Journal must balance")
    for line in lines:
        for value in (line.debit, line.credit):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("Invalid posting amount")
            if value != value.quantize(Decimal(".01")):
                raise ValueError("Invalid posting precision")
        if bool(line.credit) == bool(line.debit):
            raise ValueError("Posting requires one positive side")
    db.execute(
        text("""
        INSERT INTO ledgerops.journal_entries(id,description,currency,actor_id,actor_principal)
        VALUES (:id,:description,'INR',:actor,:principal)
    """),
        {
            "id": journal,
            "description": description,
            "actor": actor.user_id,
            "principal": actor.value,
        },
    )
    for line in lines:
        db.execute(
            text("""
            INSERT INTO ledgerops.journal_postings(journal_id,ledger_id,currency,debit,credit)
            VALUES (:id,:ledger,'INR',:debit,:credit)
        """),
            {"id": journal, "ledger": line.ledger, "debit": line.debit, "credit": line.credit},
        )
    db.execute(
        text("UPDATE ledgerops.journal_entries SET status='posted' WHERE id=:id"), {"id": journal}
    )
    audit.record(
        db,
        principal=actor,
        action="ledger.journal.posted",
        target_type="journal",
        target_id=str(journal),
        request_id=request_id,
    )
