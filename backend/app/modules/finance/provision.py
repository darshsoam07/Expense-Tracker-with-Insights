"""Explicit synthetic provisioning for an existing local operator. Never run on startup."""

import argparse
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import SystemClock
from app.core.principal import Principal
from app.db import make_engine, migration_url
from app.modules.audit import AuditWriter
from app.modules.finance.posting import Line, post


def provision(db: Session, user: UUID) -> None:
    customer = uuid5(NAMESPACE_URL, f"ledgerops:synthetic:{user}")
    actor = Principal.system("synthetic-provision")
    audit = AuditWriter(SystemClock())
    inserted = db.scalar(
        text("""
        INSERT INTO ledgerops.customers(id,name,kind)
        VALUES (:id,'Synthetic treasury','organization')
        ON CONFLICT(id) DO NOTHING RETURNING id
    """),
        {"id": customer},
    )
    if inserted is None:
        return
    db.execute(
        text("""
        INSERT INTO ledgerops.customer_members(customer_id,user_id,role)
        VALUES (:customer,:user,'owner')
    """),
        {"customer": customer, "user": user},
    )
    for action in ("customer.created", "membership.created"):
        audit.record(
            db,
            principal=actor,
            action=action,
            target_type="customer",
            target_id=str(customer),
            metadata={"member": str(user)},
        )
    ledgers = []
    for code in ("1000", "2000", "2000"):
        ledger = uuid4()
        ledgers.append(ledger)
        db.execute(
            text(
                "INSERT INTO ledgerops.ledger_accounts(id,code,currency) VALUES (:id,:code,'INR')"
            ),
            {"id": ledger, "code": code},
        )
        db.execute(
            text("INSERT INTO ledgerops.account_balances(ledger_id,currency) VALUES (:id,'INR')"),
            {"id": ledger},
        )
        if code == "2000":
            account = uuid4()
            db.execute(
                text("""
                INSERT INTO ledgerops.accounts(id,customer_id,ledger_id,currency)
                VALUES (:id,:customer,:ledger,'INR')
            """),
                {"id": account, "customer": customer, "ledger": ledger},
            )
            audit.record(
                db,
                principal=actor,
                action="account.opened",
                target_type="account",
                target_id=str(account),
            )
    initial = Decimal("1000.00")
    post(
        db,
        uuid4(),
        "Synthetic opening funding",
        (Line(ledgers[0], initial, Decimal(0)), Line(ledgers[1], Decimal(0), initial)),
        actor,
        audit,
        None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=UUID, required=True)
    args = parser.parse_args()
    with Session(make_engine(migration_url())) as db, db.begin():
        provision(db, args.user_id)


if __name__ == "__main__":
    main()
