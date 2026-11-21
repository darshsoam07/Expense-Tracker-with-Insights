"""Explicit platform-owned simulated INR asset provisioning and legacy cash consolidation."""

import argparse
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import SystemClock
from app.core.principal import Principal
from app.db import make_engine, migration_url
from app.modules.audit import AuditWriter
from app.modules.finance.posting import Line, post

REFERENCE = "PLATFORM-INR-NOSTRO"
NOSTRO = uuid5(NAMESPACE_URL, "ledgerops:" + REFERENCE)


def provision_nostro(db: Session, audit: AuditWriter) -> UUID:
    inserted = db.scalar(
        text("""INSERT INTO ledgerops.ledger_accounts(id,code,currency)
        VALUES (:id,'1010','INR') ON CONFLICT DO NOTHING RETURNING id"""),
        {"id": NOSTRO},
    )
    if inserted:
        db.execute(
            text("""INSERT INTO ledgerops.account_balances(ledger_id,currency)
            VALUES (:id,'INR')"""),
            {"id": NOSTRO},
        )
        audit.record(
            db,
            principal=Principal.system("nostro-provision"),
            action="nostro.created",
            target_type="ledger_account",
            target_id=str(NOSTRO),
            request_id=None,
            metadata={"reference": REFERENCE},
        )
    if (
        db.scalar(
            text("""SELECT id FROM ledgerops.ledger_accounts WHERE code='1010'
        AND currency='INR' AND active""")
        )
        != NOSTRO
    ):
        raise ValueError("Platform nostro identity mismatch")
    return NOSTRO


def consolidate(db: Session, audit: AuditWriter) -> None:
    provision_nostro(db, audit)
    db.execute(
        text("SELECT ledger_id FROM ledgerops.account_balances WHERE ledger_id=:id FOR UPDATE"),
        {"id": NOSTRO},
    )
    rows = db.execute(
        text("""SELECT l.id,b.ledger_balance FROM ledgerops.ledger_accounts l
        JOIN ledgerops.account_balances b ON b.ledger_id=l.id WHERE l.code='1000'
        AND b.ledger_balance>0 ORDER BY l.id FOR UPDATE OF b""")
    ).all()
    for source, balance in rows:
        owners = (
            db.execute(
                text("""SELECT DISTINCT a.customer_id FROM ledgerops.journal_entries j
            JOIN ledgerops.journal_postings cash ON cash.journal_id=j.id
            JOIN ledgerops.journal_postings deposit ON deposit.journal_id=j.id
            JOIN ledgerops.accounts a ON a.ledger_id=deposit.ledger_id
            WHERE j.description='Synthetic opening funding' AND j.status='posted'
            AND j.actor_principal='system:synthetic-provision' AND cash.ledger_id=:source
            AND cash.debit>0 AND deposit.credit=cash.debit"""),
                {"source": source},
            )
            .scalars()
            .all()
        )
        if len(owners) != 1:
            raise ValueError(f"Review legacy cash attribution for {source}")
        journal = uuid5(NOSTRO, f"legacy-cash/{source}")
        actor = Principal.system("nostro-reclassification")
        post(
            db,
            journal,
            f"Legacy cash consolidation {source}",
            (Line(NOSTRO, balance, Decimal(0)), Line(source, Decimal(0), balance)),
            actor,
            audit,
            None,
        )
        audit.record(
            db,
            principal=actor,
            action="nostro.reclassified",
            target_type="journal",
            target_id=str(journal),
            request_id=None,
            metadata={"customer_id": str(owners[0]), "source": str(source)},
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consolidate", action="store_true")
    args = parser.parse_args()
    with Session(make_engine(migration_url())) as db, db.begin():
        audit = AuditWriter(SystemClock())
        if args.consolidate:
            consolidate(db, audit)
        else:
            provision_nostro(db, audit)


if __name__ == "__main__":
    main()
