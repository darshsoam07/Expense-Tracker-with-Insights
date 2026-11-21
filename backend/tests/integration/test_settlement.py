"""Platform settlement accounting uses the original hold and a single journal."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance import payments
from app.modules.finance.nostro import NOSTRO, provision_nostro
from app.modules.finance.settlement import settle
from tests.helpers import FakeClock
from tests.integration.conftest import Workspace
from tests.integration.test_payments import make_payment


def test_nostro_and_settlement(
    db: Session,
    migrator_engine: Engine,
    runtime_engine: Engine,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    audit = AuditWriter(clock)
    with Session(migrator_engine) as admin, admin.begin():
        assert provision_nostro(admin, audit) == provision_nostro(admin, audit) == NOSTRO
    balance = text("SELECT ledger_balance FROM ledgerops.account_balances WHERE ledger_id=:id")
    before = db.scalar(balance, {"id": NOSTRO})
    p = make_payment(db, workspace, clock)
    payment = UUID(str(p["id"]))
    with pytest.raises(AppError, match="accepted"):
        settle(db, payment, workspace.actor, audit, None)
    payments.submit(db, workspace.actor, payment, audit, None)

    def fail(
        conn: object, cursor: object, statement: str, params: object, context: object, many: bool
    ) -> None:
        if "audit_events" in statement and "payment.settled" in str(params):
            raise RuntimeError("audit failure")

    event.listen(db.connection(), "after_cursor_execute", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        settle(db, payment, workspace.actor, audit, None)
    db.rollback()
    assert db.scalar(balance, {"id": NOSTRO}) == before
    assert db.scalar(
        text("SELECT remaining FROM ledgerops.account_holds WHERE id=:id"), {"id": p["hold_id"]}
    ) == Decimal("600")
    barrier = Barrier(2)

    def process() -> UUID:
        with Session(runtime_engine) as session, session.begin():
            barrier.wait(timeout=10)
            return settle(session, payment, workspace.actor, audit, None)

    with ThreadPoolExecutor(2) as pool:
        first, second = list(pool.map(lambda _: process(), range(2)))
    assert first == second
    assert db.scalar(balance, {"id": NOSTRO}) == before - Decimal("600")
    assert (
        db.scalar(
            text("SELECT remaining FROM ledgerops.account_holds WHERE id=:id"), {"id": p["hold_id"]}
        )
        == 0
    )
    assert (
        db.scalar(
            text("SELECT customer_id FROM ledgerops.settlement_items WHERE journal_id=:id"),
            {"id": first},
        )
        == p["customer_id"]
    )
    assert db.execute(
        text("SELECT sum(debit),sum(credit) FROM ledgerops.journal_postings WHERE journal_id=:id"),
        {"id": first},
    ).one() == (Decimal("600"), Decimal("600"))


def test_distinct_payments_compete_for_nostro(
    db: Session,
    migrator_engine: Engine,
    runtime_engine: Engine,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    from uuid import uuid4

    from app.core.principal import Principal
    from app.modules.finance.posting import Line, post

    audit = AuditWriter(clock)
    ids = []
    for key in ("first", "second"):
        p = make_payment(db, workspace, clock, key, Decimal("400"))
        payment = UUID(str(p["id"]))
        payments.submit(db, workspace.actor, payment, audit, None)
        ids.append(payment)
    with Session(migrator_engine) as admin, admin.begin():
        cash = uuid4()
        admin.execute(
            text(
                "INSERT INTO ledgerops.ledger_accounts(id,code,currency) VALUES (:id,'1000','INR')"
            ),
            {"id": cash},
        )
        admin.execute(
            text("INSERT INTO ledgerops.account_balances(ledger_id,currency) VALUES (:id,'INR')"),
            {"id": cash},
        )
        total = admin.scalar(
            text(
                "SELECT ledger_balance FROM ledgerops.account_balances "
                "WHERE ledger_id=:id FOR UPDATE"
            ),
            {"id": NOSTRO},
        )
        reserve = total - Decimal("400")
        post(
            admin,
            uuid4(),
            "Synthetic liquidity test",
            (Line(cash, reserve, Decimal(0)), Line(NOSTRO, Decimal(0), reserve)),
            Principal.system("liquidity-test"),
            audit,
            None,
        )
    barrier = Barrier(2)

    def process(payment: UUID) -> str:
        try:
            with Session(runtime_engine) as session, session.begin():
                barrier.wait(timeout=10)
                settle(session, payment, workspace.actor, audit, None)
            return "settled"
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(process, ids)) == ["insufficient_nostro", "settled"]
    assert (
        db.scalar(
            text("SELECT ledger_balance FROM ledgerops.account_balances WHERE ledger_id=:id"),
            {"id": NOSTRO},
        )
        == 0
    )
    assert db.scalar(
        text("""SELECT sum(h.remaining) FROM ledgerops.account_holds h JOIN
        ledgerops.payment_instructions p ON p.hold_id=h.id WHERE p.source_id=:source"""),
        {"source": workspace.src},
    ) == Decimal("400")

    # Return synthetic liquidity to the shared asset for other integration cases.
    with Session(migrator_engine) as admin, admin.begin():
        post(
            admin,
            uuid4(),
            "Restore synthetic liquidity",
            (Line(NOSTRO, reserve, Decimal(0)), Line(cash, Decimal(0), reserve)),
            Principal.system("liquidity-test"),
            audit,
            None,
        )


def test_legacy_cash_consolidated_once(
    migrator_engine: Engine, workspace: Workspace, clock: FakeClock
) -> None:
    from uuid import uuid4

    from app.core.principal import Principal
    from app.modules.finance.nostro import consolidate
    from app.modules.finance.posting import Line, post

    audit = AuditWriter(clock)
    with Session(migrator_engine) as db, db.begin():
        legacy = uuid4()
        db.execute(
            text(
                "INSERT INTO ledgerops.ledger_accounts(id,code,currency) VALUES (:id,'1000','INR')"
            ),
            {"id": legacy},
        )
        db.execute(
            text("INSERT INTO ledgerops.account_balances(ledger_id,currency) VALUES (:id,'INR')"),
            {"id": legacy},
        )
        deposit = db.scalar(
            text("SELECT ledger_id FROM ledgerops.accounts WHERE id=:id"), {"id": workspace.src}
        )
        amount = Decimal("125.50")
        post(
            db,
            uuid4(),
            "Synthetic opening funding",
            (Line(legacy, amount, Decimal(0)), Line(deposit, Decimal(0), amount)),
            Principal.system("synthetic-provision"),
            audit,
            None,
        )

        def balance(ledger: UUID) -> Decimal:
            return Decimal(
                db.execute(
                    text(
                        "SELECT ledger_balance FROM ledgerops.account_balances WHERE ledger_id=:id"
                    ),
                    {"id": ledger},
                ).scalar_one()
            )

        before = balance(NOSTRO)
        liability = balance(deposit)
        consolidate(db, audit)
        count = db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries"))
        consolidate(db, audit)
        assert db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries")) == count
        assert balance(legacy) == 0
        assert balance(NOSTRO) == before + amount
        assert balance(deposit) == liability
