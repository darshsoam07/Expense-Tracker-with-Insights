from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance.transfers import transfer
from tests.helpers import FakeClock
from tests.integration.conftest import Workspace, login


def configure(db: Session, workspace: Workspace, clock: FakeClock) -> None:
    db.execute(
        text("""INSERT INTO ledgerops.approval_policies
        SELECT :policy,1,customer_id,'Review','INR',500,NULL,2,3600,true,:now,:actor
        FROM ledgerops.accounts WHERE id=:src"""),
        {"policy": uuid4(), "actor": workspace.actor, "now": clock.now(), "src": workspace.src},
    )
    db.commit()


def test_pending_api(api: TestClient, db: Session, workspace: Workspace, clock: FakeClock) -> None:
    configure(db, workspace, clock)
    headers = {
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
        "Idempotency-Key": "one",
    }
    data = {
        "source_id": str(workspace.src),
        "destination_id": str(workspace.dst),
        "currency": "INR",
        "amount": "600",
    }
    url = "/api/v1/transfers"
    counts = text("""SELECT (SELECT count(*) FROM ledgerops.journal_entries),
        (SELECT count(*) FROM ledgerops.journal_postings)""")
    before = db.execute(counts).one()
    response = api.post(url, json=data, headers=headers)
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["status"] == "pending_approval"
    assert result["reserved_amount"] == "600.00"
    assert result["required_count"] == 2
    assert result["id"] != result["approval_request_id"]
    assert api.post(url, json=data, headers=headers).json() == result
    assert api.post(url, json={**data, "amount": "601"}, headers=headers).status_code == 409
    assert db.execute(counts).one() == before
    account = api.get(f"/api/v1/accounts/{workspace.src}").json()
    assert (account["ledger_balance"], account["available_balance"]) == ("1000.00", "400.00")


@pytest.mark.parametrize("same_key", [True, False])
def test_pending_race(
    runtime_engine: Engine, db: Session, workspace: Workspace, clock: FakeClock, same_key: bool
) -> None:
    configure(db, workspace, clock)
    barrier = Barrier(2)

    def submit(key: str) -> str:
        with Session(runtime_engine) as session:
            barrier.wait(timeout=10)
            try:
                result, _ = transfer(
                    session,
                    workspace.actor,
                    workspace.src,
                    workspace.dst,
                    Decimal("700"),
                    "",
                    key,
                    AuditWriter(clock),
                    None,
                )
                return str(result["id"])
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(submit, ["one", "one" if same_key else "two"]))
    if same_key:
        assert outcomes[0] == outcomes[1]
    else:
        assert outcomes.count("insufficient_funds") == 1
    assert (
        db.scalar(
            text("SELECT count(*) FROM ledgerops.account_holds WHERE account_id=:src"),
            {"src": workspace.src},
        )
        == 1
    )


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO ledgerops.hold_events",
        "INSERT INTO ledgerops.approval_requests",
        "INSERT INTO ledgerops.approval_events",
        "approval_audit",
    ],
)
def test_submission_failure(
    db: Session, workspace: Workspace, clock: FakeClock, statement: str
) -> None:
    configure(db, workspace, clock)
    connection = db.connection()

    def fail(
        conn: object, cursor: object, sql: str, params: object, context: object, many: bool
    ) -> None:
        if statement in sql or (
            statement == "approval_audit"
            and "audit_events" in sql
            and "approval.requested" in str(params)
        ):
            raise RuntimeError("injected")

    event.listen(connection, "after_cursor_execute", fail)
    with pytest.raises(RuntimeError, match="injected"):
        transfer(
            db,
            workspace.actor,
            workspace.src,
            workspace.dst,
            Decimal("700"),
            "",
            "one",
            AuditWriter(clock),
            None,
        )
    for table, column in (
        ("account_holds", "account_id"),
        ("approval_requests", "source_id"),
        ("transfers", "source_id"),
    ):
        assert (
            db.scalar(
                text(f"SELECT count(*) FROM ledgerops.{table} WHERE {column}=:src"),  # noqa: S608 - fixed table/column pairs
                {"src": workspace.src},
            )
            == 0
        )
