from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance import operations as ops
from app.modules.finance import payments
from app.modules.finance.statements import COLUMNS, MAX_BYTES, MAX_ROWS, parse_statement
from tests.helpers import FakeClock
from tests.integration.conftest import Workspace
from tests.integration.test_payments import make_payment

HEADER = ",".join(COLUMNS) + "\n"
ROW = (Path(__file__).parents[1] / "fixtures" / "simulated_statement.csv").read_text().splitlines()[
    1
] + "\n"


@pytest.mark.parametrize(
    "content",
    [
        b"bad",
        bytes(MAX_BYTES + 1),
        (HEADER + ROW * (MAX_ROWS + 1)).encode(),
        (HEADER + ROW.replace("10.00", "0.001")).encode(),
        (HEADER + ROW.replace("INR", "INVALID")).encode(),
        (HEADER + ROW.replace("01-01", "02-31")).encode(),
        b"\xff",
    ],
)
def test_invalid_statements(content: bytes) -> None:
    with pytest.raises(AppError):
        parse_statement(content)


def test_batch_statement_workflow(db: Session, workspace: Workspace, clock: FakeClock) -> None:
    audit = AuditWriter(clock)
    actor = workspace.actor
    customer = db.execute(
        text("SELECT customer_id FROM ledgerops.accounts WHERE id=:id"), {"id": workspace.src}
    ).scalar_one()
    with pytest.raises(AppError, match="No eligible"):
        ops.batch(db, customer, actor, audit, None)
    p = make_payment(db, workspace, clock, amount=Decimal("10"))
    payments.submit(db, actor, UUID(str(p["id"])), audit, None)
    b = ops.batch(db, customer, actor, audit, None)
    assert ops.process(db, b["id"], actor, audit, None)["status"] == "settled"
    assert ops.process(db, b["id"], actor, audit, None)["settled_count"] == 1
    entry = ops.children(db, "batches", actor, b["id"], 25, 0)[0]
    assert entry["journal_id"]
    assert entry["hold_status"] == "captured"
    journals = db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries"))
    day = clock.now().date().isoformat()
    for i, (amount, currency, direction, date, expected) in enumerate(
        [
            ("10.00", "INR", "outbound", day, "exact_match"),
            ("11", "INR", "outbound", day, "amount_mismatch"),
            ("10", "USD", "outbound", day, "currency_mismatch"),
            ("10", "INR", "inbound", day, "direction_mismatch"),
            ("10", "INR", "outbound", "2099-01-01", "timing_difference"),
        ]
    ):
        body = (
            HEADER + f"{p['provider_reference']},ext{i},{amount},{currency},"
            f"{day},{date},{direction},settled\n"
        ).encode()
        imp = ops.ingest(db, customer, actor, "rail.csv", body, audit, None)
        replay = ops.ingest(db, customer, actor, "rail.csv", body, audit, None)
        assert imp["id"] == replay["id"]
        assert replay["replayed"]
        run = ops.reconcile(db, imp["id"], actor, audit, None)
        assert (
            ops.children(db, "reconciliation-runs", actor, run["id"], 25, 0)[0]["classification"]
            == expected
        )
    for repeat, expected in [(1, "missing_internal_record"), (2, "duplicate_external_reference")]:
        body = (HEADER + ROW.replace("2026-01-01", day) * repeat).encode()
        imp = ops.ingest(db, customer, actor, "rail.csv", body, audit, None)
        run = ops.reconcile(db, imp["id"], actor, audit, None)
        assert {
            r["classification"]
            for r in ops.children(db, "reconciliation-runs", actor, run["id"], 25, 0)
        } == {expected, "missing_statement_record"}
    assert db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries")) == journals


def test_batch_competition_partial_failure_and_retry(
    db: Session,
    runtime_engine: Engine,
    workspace: Workspace,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = workspace.actor
    audit = AuditWriter(clock)
    customer = db.execute(
        text("SELECT customer_id FROM ledgerops.accounts WHERE id=:id"), {"id": workspace.src}
    ).scalar_one()
    ids = []
    for key in ("batch-a", "batch-b"):
        payment = make_payment(db, workspace, clock, key, Decimal("25"))
        ids.append(UUID(str(payment["id"])))
        payments.submit(db, actor, ids[-1], audit, None)
    barrier = Barrier(2)

    def reserve() -> UUID | None:
        with Session(runtime_engine) as session:
            barrier.wait(timeout=10)
            try:
                return UUID(str(ops.batch(session, customer, actor, audit, None)["id"]))
            except AppError as exc:
                if exc.code != "empty_batch":
                    raise
                return None

    with ThreadPoolExecutor(2) as pool:
        batches = [b for b in pool.map(lambda _: reserve(), range(2)) if b]
    assert len(batches) == 1
    from app.modules.finance.settlement import settle as original

    def unavailable(
        session: Session, payment: UUID, user: UUID, writer: AuditWriter, request: str | None
    ) -> UUID:
        if payment == ids[0]:
            raise AppError(409, "insufficient_nostro", "Test liquidity limit")
        return original(session, payment, user, writer, request)

    with monkeypatch.context() as patch:
        patch.setattr(ops, "settle", unavailable)
        partial = ops.process(db, batches[0], actor, audit, None)
        assert partial["status"] == "partially_settled"
        assert partial["failed_count"] == partial["settled_count"] == 1

    def retry() -> str:
        with Session(runtime_engine) as session:
            barrier.wait(timeout=10)
            return str(ops.process(session, batches[0], actor, audit, None)["status"])

    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _: retry(), range(2))) == ["settled", "settled"]
    items = ops.children(db, "batches", actor, batches[0], 25, 0)
    assert len({r["journal_id"] for r in items}) == 2
    assert all(r["hold_status"] == "captured" and r["failure"] is None for r in items)


def test_failed_import_audit_rolls_back(
    db: Session, workspace: Workspace, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    customer = db.execute(
        text("SELECT customer_id FROM ledgerops.accounts WHERE id=:id"), {"id": workspace.src}
    ).scalar_one()

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(ops, "log", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        ops.ingest(
            db,
            customer,
            workspace.actor,
            "rollback.csv",
            (HEADER + ROW).encode(),
            AuditWriter(clock),
            None,
        )
    db.rollback()
    assert (
        db.scalar(
            text("SELECT count(*) FROM ledgerops.statement_imports WHERE customer_id=:id"),
            {"id": customer},
        )
        == 0
    )
