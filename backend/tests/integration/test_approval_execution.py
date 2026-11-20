from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from typing import Literal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance.approvals import decide
from app.modules.finance.transfers import transfer
from tests.helpers import FakeClock
from tests.integration.conftest import UserFactory, Workspace, login
from tests.integration.test_pending_submission import configure


@pytest.mark.parametrize(
    "scenario", ["approve", "reject", "expiry", "race", "mixed", "audit", "posting"]
)
def test_decision_outcome(
    scenario: str,
    api: TestClient,
    db: Session,
    runtime_engine: Engine,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    users = [make_user(("approver",)) for _ in range(3)]
    reviewers = [user.id for user in users]
    with migrator_engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO ledgerops.user_roles(user_id,role_id,granted_at,granted_by)
            SELECT :maker,id,now(),'system:test' FROM ledgerops.roles WHERE code='approver'"""),
            {"maker": workspace.actor},
        )
        for reviewer in reviewers:
            conn.execute(
                text("""INSERT INTO ledgerops.customer_members(customer_id,user_id,role)
                SELECT customer_id,:actor,'member' FROM ledgerops.accounts WHERE id=:src"""),
                {"actor": reviewer, "src": workspace.src},
            )
    configure(db, workspace, clock)
    audit = AuditWriter(clock)
    receipt, _ = transfer(
        db,
        workspace.actor,
        workspace.src,
        workspace.dst,
        Decimal("600"),
        "review",
        "one",
        audit,
        None,
    )
    approval = UUID(str(receipt["approval_request_id"]))
    with pytest.raises(AppError, match="different reviewer"):
        decide(db, workspace.actor, approval, "approve", "self", audit, None)
    token = login(api, users[0].email)["csrf_token"]
    url = f"/api/v1/approvals/{approval}"
    assert any(row["id"] == str(approval) for row in api.get("/api/v1/approvals").json())
    assert api.get(url).json()["hold_status"] == "active"
    assert api.post(url + "/approve", json={"reason": "first"}).status_code == 403
    first = api.post(
        url + "/approve", json={"reason": "first"}, headers={"X-CSRF-Token": str(token)}
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending_approval"
    with pytest.raises(AppError, match="already decided"):
        decide(db, reviewers[0], approval, "approve", "again", audit, None)
    if scenario == "expiry":
        clock.advance(timedelta(hours=2))
        with pytest.raises(AppError, match="expired"):
            decide(db, reviewers[1], approval, "approve", "late", audit, None)
    elif scenario in {"race", "mixed"}:
        barrier = Barrier(2)

        def vote(index: int) -> str:
            with Session(runtime_engine) as session:
                barrier.wait(timeout=10)
                choice: Literal["approve", "reject"] = (
                    "reject" if scenario == "mixed" and index == 2 else "approve"
                )
                try:
                    return str(
                        decide(session, reviewers[index], approval, choice, "race", audit, None)[
                            "status"
                        ]
                    )
                except AppError as exc:
                    return exc.code

        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(vote, [1, 2]))
        assert outcomes.count("approval_terminal") == 1
    elif scenario in {"posting", "audit"}:

        def fail(
            conn: object, cursor: object, sql: str, params: object, context: object, many: bool
        ) -> None:
            if (scenario == "posting" and "INSERT INTO ledgerops.journal_postings" in sql) or (
                scenario == "audit" and "approval.approved" in str(params)
            ):
                raise RuntimeError("injected")

        event.listen(db.connection(), "after_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="injected"):
            decide(db, reviewers[1], approval, "approve", "final", audit, None)
    else:
        decide(
            db,
            reviewers[1],
            approval,
            "approve" if scenario == "approve" else "reject",
            "final",
            audit,
            None,
        )
    state = db.execute(
        text("""SELECT r.status,h.remaining,b.ledger_balance,
        (SELECT count(*) FROM ledgerops.transfers t JOIN ledgerops.journal_entries j
         ON j.id=t.journal_id WHERE t.id=r.subject_id AND j.status='posted') AS journals,
        (SELECT count(*) FROM ledgerops.approval_decisions WHERE request_id=r.id) AS decisions
        FROM ledgerops.approval_requests r JOIN ledgerops.account_holds h ON h.id=r.hold_id
        JOIN ledgerops.accounts a ON a.id=r.source_id
        JOIN ledgerops.account_balances b USING(ledger_id)
        WHERE r.id=:id"""),
        {"id": approval},
    ).one()
    if scenario in {"audit", "posting"}:
        assert tuple(state) == ("pending_approval", 600, 1000, 0, 1)
    elif scenario in {"approve", "race"} or (scenario == "mixed" and state.status == "approved"):
        assert tuple(state) == ("approved", 0, 400, 1, 2)
        replay, created = transfer(
            db,
            workspace.actor,
            workspace.src,
            workspace.dst,
            Decimal("600"),
            "review",
            "one",
            audit,
            None,
        )
        assert not created
        assert replay["status"] == "posted"
        assert replay["id"] == receipt["id"]
    else:
        assert tuple(state) == (
            ("expired", 0, 1000, 0, 1) if scenario == "expiry" else ("rejected", 0, 1000, 0, 2)
        )
