"""Payment reservations and deterministic simulated-rail lifecycle."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance import approvals, payments
from app.modules.finance.holds import require_unassigned
from app.modules.finance.payment_rails import SimulatedRail
from tests.helpers import FakeClock
from tests.integration.conftest import UserFactory, Workspace, login
from tests.integration.test_pending_submission import configure


def make_payment(
    db: Session,
    workspace: Workspace,
    clock: FakeClock,
    key: str = "payment",
    amount: Decimal = Decimal("600"),
) -> dict[str, object]:
    result, created = payments.create(
        db,
        workspace.actor,
        workspace.src,
        "Synthetic Supplier",
        "SIM-DEST-001",
        amount,
        "INV-001",
        key,
        AuditWriter(clock),
        None,
    )
    assert created
    return result


@pytest.mark.parametrize(
    ("outcome", "status", "remaining"),
    [
        ("accepted", "accepted", "600.00"),
        ("rejected", "failed", "0.00"),
        ("timeout", "outcome_unknown", "600.00"),
    ],
)
def test_simulated_outcomes_preserve_accounting_boundary(
    db: Session,
    workspace: Workspace,
    clock: FakeClock,
    outcome: str,
    status: str,
    remaining: str,
) -> None:
    before = db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries"))
    payment = make_payment(db, workspace, clock, outcome)
    assert payment["status"] == "ready_for_submission"
    assert payment["rail"] == "SIMULATED_INR"
    result = payments.submit(
        db,
        workspace.actor,
        UUID(str(payment["id"])),
        AuditWriter(clock),
        None,
        SimulatedRail(outcome),  # type: ignore[arg-type]
    )
    assert result["status"] == status
    if status in {"accepted", "outcome_unknown"}:
        with pytest.raises(AppError, match="Reservation belongs"):
            require_unassigned(db, UUID(str(payment["hold_id"])))
    if status == "outcome_unknown":
        repeated = payments.submit(
            db,
            workspace.actor,
            UUID(str(payment["id"])),
            AuditWriter(clock),
            None,
            SimulatedRail("timeout"),
        )
        assert repeated["events"] == result["events"]
        resolved = payments.submit(
            db,
            workspace.actor,
            UUID(str(payment["id"])),
            AuditWriter(clock),
            None,
            SimulatedRail("accepted"),
        )
        assert resolved["provider_reference"] == payment["provider_reference"]
        assert resolved["status"] == "accepted"
    hold = db.execute(
        text("SELECT remaining::text FROM ledgerops.account_holds WHERE id=:id"),
        {"id": payment["hold_id"]},
    ).scalar_one()
    assert hold == remaining
    assert db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries")) == before
    balance = db.execute(
        text("""SELECT ledger_balance::text,available_balance::text
          FROM ledgerops.accounts JOIN ledgerops.account_balances USING(ledger_id)
          WHERE accounts.id=:id"""),
        {"id": workspace.src},
    ).one()
    assert balance.ledger_balance == "1000.00"
    assert balance.available_balance == ("1000.00" if status == "failed" else "400.00")


def test_retry_idempotency_cancel_and_temporary_failure(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    payment = make_payment(db, workspace, clock)
    replay, created = payments.create(
        db,
        workspace.actor,
        workspace.src,
        "Synthetic Supplier",
        "SIM-DEST-001",
        Decimal("600"),
        "INV-001",
        "payment",
        AuditWriter(clock),
        None,
    )
    assert not created
    assert replay["id"] == payment["id"]
    with pytest.raises(AppError, match="another payment"):
        payments.create(
            db,
            workspace.actor,
            workspace.src,
            "Changed",
            "SIM-DEST-001",
            Decimal("600"),
            "INV-001",
            "payment",
            AuditWriter(clock),
            None,
        )
    with pytest.raises(AppError, match="temporarily unavailable"):
        payments.submit(
            db,
            workspace.actor,
            UUID(str(payment["id"])),
            AuditWriter(clock),
            None,
            SimulatedRail("temporary_unavailable"),
        )
    assert payments.detail(db, workspace.actor, UUID(str(payment["id"])))["status"] == (
        "ready_for_submission"
    )
    cancelled = payments.cancel(
        db, workspace.actor, UUID(str(payment["id"])), AuditWriter(clock), None
    )
    assert cancelled["status"] == "cancelled"
    with pytest.raises(AppError, match="no longer"):
        payments.cancel(db, workspace.actor, UUID(str(payment["id"])), AuditWriter(clock), None)


def test_approval_then_submission(
    db: Session,
    migrator_engine: Engine,
    workspace: Workspace,
    make_user: UserFactory,
    clock: FakeClock,
) -> None:
    configure(db, workspace, clock)
    checker = make_user(("approver",))
    with migrator_engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO ledgerops.customer_members(customer_id,user_id,role)
              SELECT customer_id,:actor,'member' FROM ledgerops.accounts WHERE id=:source"""),
            {"actor": checker.id, "source": workspace.src},
        )
    payment = make_payment(db, workspace, clock)
    assert payment["status"] == "pending_approval"
    with pytest.raises(AppError, match="cannot be submitted"):
        payments.submit(db, workspace.actor, UUID(str(payment["id"])), AuditWriter(clock), None)
    approval = UUID(str(payment["approval_id"]))
    approvals.decide(db, checker.id, approval, "approve", "Reviewed", AuditWriter(clock), None)
    ready = payments.detail(db, workspace.actor, UUID(str(payment["id"])))
    assert ready["status"] == "pending_approval"
    second = make_user(("approver",))
    with migrator_engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO ledgerops.customer_members(customer_id,user_id,role)
              SELECT customer_id,:actor,'member' FROM ledgerops.accounts WHERE id=:source"""),
            {"actor": second.id, "source": workspace.src},
        )
    approvals.decide(db, second.id, approval, "approve", "Final", AuditWriter(clock), None)
    ready = payments.detail(db, workspace.actor, UUID(str(payment["id"])))
    assert ready["status"] == "ready_for_submission"
    assert (
        payments.submit(db, workspace.actor, UUID(str(payment["id"])), AuditWriter(clock), None)[
            "status"
        ]
        == "accepted"
    )


def test_concurrent_submission_and_audit_rollback(
    db: Session, runtime_engine: Engine, workspace: Workspace, clock: FakeClock
) -> None:
    payment = make_payment(db, workspace, clock)
    payment_id = UUID(str(payment["id"]))
    barrier = Barrier(2)

    def submit() -> str:
        with Session(runtime_engine) as session:
            barrier.wait(timeout=10)
            return str(
                payments.submit(session, workspace.actor, payment_id, AuditWriter(clock), None)[
                    "status"
                ]
            )

    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _: submit(), range(2))) == ["accepted", "accepted"]
    assert (
        db.scalar(
            text("""SELECT count(*) FROM ledgerops.payment_events
          WHERE payment_id=:id AND kind='accepted'"""),
            {"id": payment_id},
        )
        == 1
    )

    other = make_payment(db, workspace, clock, "rollback", Decimal("300"))

    def fail_audit(
        conn: object, cursor: object, statement: str, params: object, context: object, many: bool
    ) -> None:
        if "audit_events" in statement and "payment.accepted" in str(params):
            raise RuntimeError("injected")

    event.listen(db.connection(), "after_cursor_execute", fail_audit)
    with pytest.raises(RuntimeError, match="injected"):
        payments.submit(db, workspace.actor, UUID(str(other["id"])), AuditWriter(clock), None)
    assert payments.detail(db, workspace.actor, UUID(str(other["id"])))["status"] == (
        "ready_for_submission"
    )


def test_live_payment_api(api: TestClient, workspace: Workspace) -> None:
    headers = {
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
        "Idempotency-Key": "api-payment",
    }
    body = {
        "source_id": str(workspace.src),
        "beneficiary_name": "Synthetic Supplier",
        "destination_reference": "SIM-DEST-API",
        "customer_reference": "INV-API",
        "amount": "100",
        "currency": "INR",
    }
    created = api.post("/api/v1/payments", headers=headers, json=body)
    assert created.status_code == 201, created.text
    payment = created.json()
    assert (
        api.post("/api/v1/payments", headers=headers, json={**body, "amount": "101"}).status_code
        == 409
    )
    insufficient = api.post(
        "/api/v1/payments",
        headers={**headers, "Idempotency-Key": "insufficient"},
        json={**body, "amount": "1001"},
    )
    assert insufficient.status_code == 409
    assert api.post("/api/v1/payments", headers=headers, json=body).json()["id"] == payment["id"]
    assert api.get("/api/v1/payments").status_code == 200
    submitted = api.post(
        f"/api/v1/payments/{payment['id']}/submit",
        headers={"X-CSRF-Token": headers["X-CSRF-Token"]},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "accepted"
    assert api.post(f"/api/v1/payments/{payment['id']}/cancel", headers=headers).status_code == 409


def test_unrelated_customer_cannot_read_or_submit(
    db: Session, workspace: Workspace, clock: FakeClock, make_user: UserFactory
) -> None:
    payment = make_payment(db, workspace, clock)
    outsider = make_user(("approver",))
    payment_id = UUID(str(payment["id"]))
    with pytest.raises(AppError, match="Payment unavailable"):
        payments.detail(db, outsider.id, payment_id)
    with pytest.raises(AppError, match="Payment unavailable"):
        payments.submit(db, outsider.id, payment_id, AuditWriter(clock), None)
    assert payments.detail(db, workspace.actor, payment_id)["status"] == "ready_for_submission"
