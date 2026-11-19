"""Financial operations exercised through HTTP and independent PostgreSQL sessions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.clock import SystemClock
from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance.provision import provision
from app.modules.finance.queries import accounts
from app.modules.finance.transfers import transfer
from tests.integration.conftest import UserFactory, login


@dataclass
class Workspace:
    actor: UUID
    email: str
    src: UUID
    dst: UUID


@pytest.fixture
def workspace(make_user: UserFactory, migrator_engine: Engine) -> Workspace:
    user = make_user(("operator",))
    with Session(migrator_engine) as db, db.begin():
        provision(db, user.id)
        provision(db, user.id)
        rows = sorted(
            accounts(db, user.id), key=lambda a: Decimal(str(a["ledger_balance"])), reverse=True
        )
        assert [r["available_balance"] for r in rows] == ["1000.00", "0.00"]
        return Workspace(user.id, user.email, UUID(str(rows[0]["id"])), UUID(str(rows[1]["id"])))


def test_internal_transfer(api: TestClient, workspace: Workspace, make_user: UserFactory) -> None:
    state = login(api, workspace.email)
    payload = {
        "source_id": str(workspace.src),
        "destination_id": str(workspace.dst),
        "amount": "12.05",
        "currency": "INR",
    }
    headers = {"Idempotency-Key": "first", "X-CSRF-Token": str(state["csrf_token"])}
    path = "/api/v1/transfers"
    assert api.post(path, json=payload).status_code == 403
    assert (
        api.post(path, json=payload, headers={"X-CSRF-Token": headers["X-CSRF-Token"]}).status_code
        == 422
    )
    result = api.post(path, json=payload, headers=headers)
    assert result.status_code == 201, result.text
    replay = api.post(path, json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json() == result.json()
    assert api.post(path, json={**payload, "amount": "1"}, headers=headers).status_code == 409
    for amount in (0.5, "1.001", "0", "-1"):
        assert (
            api.post(path, json={**payload, "amount": amount}, headers=headers).status_code == 422
        )
    assert api.post(path, json={**payload, "currency": "USD"}, headers=headers).status_code == 422
    assert (
        api.post(
            path, json={**payload, "destination_id": str(workspace.src)}, headers=headers
        ).status_code
        == 422
    )
    assert len(api.get(path).json()) == 1
    for account_id, balance in ((workspace.src, "987.95"), (workspace.dst, "12.05")):
        url = f"/api/v1/accounts/{account_id}"
        assert api.get(url).json()["available_balance"] == balance
        entries = api.get(url + "/ledger").json()
        assert entries[0]["reference"] == result.json()["journal_reference"]
    outsider = make_user(("operator",))
    api.cookies.clear()
    state = login(api, outsider.email)
    headers["X-CSRF-Token"] = str(state["csrf_token"])
    assert api.get(f"/api/v1/accounts/{workspace.src}").status_code == 404
    assert api.post(path, json=payload, headers=headers).status_code == 404
    api.cookies.clear()
    state = login(api, make_user(("auditor",)).email)
    headers["X-CSRF-Token"] = str(state["csrf_token"])
    assert api.post(path, json=payload, headers=headers).status_code == 403


@pytest.mark.parametrize("duplicate", [True, False])
def test_concurrent_posting(workspace: Workspace, runtime_engine: Engine, duplicate: bool) -> None:
    barrier = Barrier(2)

    def worker(key: str) -> str:
        with Session(runtime_engine) as db:
            barrier.wait(timeout=10)
            try:
                _, created = transfer(
                    db,
                    workspace.actor,
                    workspace.src,
                    workspace.dst,
                    Decimal("700.00"),
                    "Concurrent",
                    key,
                    AuditWriter(SystemClock()),
                    None,
                )
                return "created" if created else "replay"
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ["first", "first" if duplicate else "second"]))
    assert sorted(results) == sorted(["created", "replay" if duplicate else "insufficient_funds"])
    with Session(runtime_engine) as db:
        assert sorted(str(a["ledger_balance"]) for a in accounts(db, workspace.actor)) == [
            "300.00",
            "700.00",
        ]
        assert (
            db.scalar(
                text("SELECT count(*) FROM ledgerops.transfers WHERE actor_id=:id"),
                {"id": workspace.actor},
            )
            == 1
        )


@pytest.mark.parametrize(
    "point",
    [
        "INSERT INTO ledgerops.transfers",
        "INSERT INTO ledgerops.journal_entries",
        "INSERT INTO ledgerops.journal_postings",
        "UPDATE ledgerops.journal_entries",
        "INSERT INTO ledgerops.audit_events",
    ],
)
def test_rollback_after_statement(workspace: Workspace, runtime_engine: Engine, point: str) -> None:
    from typing import Any

    from sqlalchemy import event
    from sqlalchemy.engine import Connection, ExecutionContext

    def fail(
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        if point in statement:
            raise RuntimeError("injected failure")

    with runtime_engine.connect() as conn, Session(conn) as db:
        event.listen(conn, "after_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="injected failure"):
            transfer(
                db,
                workspace.actor,
                workspace.src,
                workspace.dst,
                Decimal("2.50"),
                "Rollback",
                "rollback",
                AuditWriter(SystemClock()),
                None,
            )
    with Session(runtime_engine) as db:
        for query in (
            "SELECT count(*) FROM ledgerops.transfers WHERE actor_id=:id",
            "SELECT count(*) FROM ledgerops.journal_entries WHERE actor_id=:id",
        ):
            assert (
                db.scalar(
                    text(query),
                    {"id": workspace.actor},
                )
                == 0
            )
        assert (
            db.scalar(
                text("SELECT count(*) FROM ledgerops.audit_events WHERE actor_user_id=:id"),
                {"id": workspace.actor},
            )
            == 0
        )
        assert sorted(str(a["available_balance"]) for a in accounts(db, workspace.actor)) == [
            "0.00",
            "1000.00",
        ]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledgerops.journal_entries SET description='changed' WHERE id=:j",
        "DELETE FROM ledgerops.journal_entries WHERE id=:j",
        "UPDATE ledgerops.journal_postings SET debit=10 WHERE journal_id=:j",
        "DELETE FROM ledgerops.journal_postings WHERE journal_id=:j",
        """INSERT INTO ledgerops.journal_postings(journal_id,ledger_id,currency,debit,credit)
       SELECT journal_id,ledger_id,currency,debit,credit FROM ledgerops.journal_postings
       WHERE journal_id=:j LIMIT 1""",
    ],
)
def test_finalized_journal_is_immutable(
    workspace: Workspace, migrator_engine: Engine, statement: str
) -> None:
    from sqlalchemy.exc import DBAPIError

    with Session(migrator_engine) as db:
        journal = db.scalar(
            text("""
            SELECT p.journal_id FROM ledgerops.accounts a
            JOIN ledgerops.journal_postings p USING(ledger_id) WHERE a.id=:src
        """),
            {"src": workspace.src},
        )
        assert journal
        with pytest.raises(DBAPIError, match="Invalid journal"):
            db.execute(text(statement), {"j": journal})


def test_runtime_cannot_truncate_or_change_projection(runtime_engine: Engine) -> None:
    with Session(runtime_engine) as db:
        assert not db.scalar(
            text("""
            SELECT has_table_privilege(current_user,'ledgerops.journal_entries','TRUNCATE')
                OR has_table_privilege(current_user,'ledgerops.journal_postings','TRUNCATE')
                OR has_table_privilege(current_user,'ledgerops.account_balances','UPDATE')
        """)
        )


@pytest.mark.parametrize(
    "scenario",
    ["draft", "empty", "one", "unbalanced", "both_sides", "currency", "inactive", "negative"],
)
def test_invalid_journal_rolls_back(
    workspace: Workspace, migrator_engine: Engine, scenario: str
) -> None:
    from sqlalchemy.exc import DBAPIError

    with Session(migrator_engine) as db:
        source = db.scalar(
            text("SELECT ledger_id FROM ledgerops.accounts WHERE id=:id"), {"id": workspace.src}
        )
        dest = db.scalar(
            text("SELECT ledger_id FROM ledgerops.accounts WHERE id=:id"), {"id": workspace.dst}
        )
        if scenario == "inactive":
            db.execute(
                text("UPDATE ledgerops.ledger_accounts SET active=false WHERE id=:id"), {"id": dest}
            )
        journal = db.scalar(
            text("""
            INSERT INTO ledgerops.journal_entries(description,currency,actor_principal)
            VALUES ('Invariant check','INR','system:test') RETURNING id
        """)
        )

        def attempt() -> None:
            if scenario not in {"empty", "draft"}:
                amount = Decimal("1001.00" if scenario == "negative" else "1.01")
                rows = [(source, amount, Decimal(1) if scenario == "both_sides" else Decimal(0))]
                if scenario != "one":
                    rows.append(
                        (dest, Decimal(0), Decimal(1) if scenario == "unbalanced" else amount)
                    )
                for ledger, debit, credit in rows:
                    db.execute(
                        text("""
                        INSERT INTO ledgerops.journal_postings
                            (journal_id,ledger_id,currency,debit,credit)
                        VALUES (:j,:l,:c,:d,:cr)
                    """),
                        {
                            "j": journal,
                            "l": ledger,
                            "c": "USD" if scenario == "currency" else "INR",
                            "d": debit,
                            "cr": credit,
                        },
                    )
            if scenario != "draft":
                db.execute(
                    text("UPDATE ledgerops.journal_entries SET status='posted' WHERE id=:j"),
                    {"j": journal},
                )
            db.commit()

        with pytest.raises(DBAPIError):
            attempt()
        db.rollback()
        assert not db.scalar(
            text("SELECT EXISTS(SELECT FROM ledgerops.journal_entries WHERE id=:j)"), {"j": journal}
        )
        assert sorted(str(a["ledger_balance"]) for a in accounts(db, workspace.actor)) == [
            "0.00",
            "1000.00",
        ]


def test_projection_matches_posted_activity(workspace: Workspace, runtime_engine: Engine) -> None:
    with Session(runtime_engine) as db:
        transfer(
            db,
            workspace.actor,
            workspace.src,
            workspace.dst,
            Decimal("21.99"),
            "Projection",
            "projection",
            AuditWriter(SystemClock()),
            None,
        )
        mismatch = db.scalar(
            text("""
            SELECT count(*) FROM ledgerops.account_balances b
            JOIN ledgerops.accounts a USING(ledger_id)
            JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
            WHERE m.user_id=:actor AND b.ledger_balance<>(SELECT coalesce(sum(p.credit-p.debit),0)
                FROM ledgerops.journal_postings p
                JOIN ledgerops.journal_entries j ON j.id=p.journal_id
                WHERE p.ledger_id=b.ledger_id AND j.status='posted')
        """),
            {"actor": workspace.actor},
        )
        assert mismatch == 0
        assert (
            db.scalar(
                text("""
            SELECT count(*) FROM ledgerops.audit_events WHERE actor_user_id=:actor
            AND action IN ('transfer.posted','ledger.journal.posted') AND outcome='success'
        """),
                {"actor": workspace.actor},
            )
            == 2
        )


def test_frozen_and_read_only_source(
    workspace: Workspace, api: TestClient, migrator_engine: Engine
) -> None:
    token = login(api, workspace.email)["csrf_token"]
    body = {
        "source_id": str(workspace.src),
        "destination_id": str(workspace.dst),
        "currency": "INR",
        "amount": "3.00",
    }
    headers = {"X-CSRF-Token": str(token), "Idempotency-Key": "retry-rejected"}
    with migrator_engine.begin() as conn:
        conn.execute(
            text("UPDATE ledgerops.accounts SET status='frozen' WHERE id=:id"),
            {"id": workspace.src},
        )
    assert api.post("/api/v1/transfers", json=body, headers=headers).status_code == 409
    with migrator_engine.begin() as conn:
        conn.execute(
            text("UPDATE ledgerops.accounts SET status='active' WHERE id=:id"),
            {"id": workspace.src},
        )
        conn.execute(
            text("UPDATE ledgerops.customer_members SET role='viewer' WHERE user_id=:id"),
            {"id": workspace.actor},
        )
    assert api.post("/api/v1/transfers", json=body, headers=headers).status_code == 404
    assert len(api.get("/api/v1/accounts").json()) == 2
    with migrator_engine.begin() as conn:
        conn.execute(
            text("UPDATE ledgerops.customer_members SET role='member' WHERE user_id=:id"),
            {"id": workspace.actor},
        )
    assert api.post("/api/v1/transfers", json=body, headers=headers).status_code == 201


def test_multi_customer_membership_scopes_accounts_independently(
    workspace: Workspace, api: TestClient, migrator_engine: Engine, make_user: UserFactory
) -> None:
    other = make_user(("operator",))
    with Session(migrator_engine) as db, db.begin():
        provision(db, other.id)
        other_accounts = accounts(db, other.id)
        customer = other_accounts[0]["customer_id"]
        db.execute(
            text("""INSERT INTO ledgerops.customer_members(customer_id,user_id,role)
                    VALUES (:customer,:user,'viewer')"""),
            {"customer": customer, "user": workspace.actor},
        )

    login(api, workspace.email)
    own_ids = {str(workspace.src), str(workspace.dst)}
    other_ids = {str(row["id"]) for row in other_accounts}
    listed = api.get("/api/v1/accounts")
    assert listed.status_code == 200
    assert sorted(row["id"] for row in listed.json()) == sorted(own_ids | other_ids)
    with migrator_engine.begin() as conn:
        conn.execute(
            text("""UPDATE ledgerops.customer_members SET active=false
                    WHERE customer_id=:customer AND user_id=:user"""),
            {"customer": customer, "user": workspace.actor},
        )
    assert sorted(row["id"] for row in api.get("/api/v1/accounts").json()) == sorted(own_ids)
    for account_id in other_ids:
        assert api.get(f"/api/v1/accounts/{account_id}").status_code == 404

    api.cookies.clear()
    login(api, other.email)
    assert sorted(row["id"] for row in api.get("/api/v1/accounts").json()) == sorted(other_ids)
    assert api.get(f"/api/v1/accounts/{workspace.src}/ledger").status_code == 404


@pytest.mark.parametrize("closed_side", ["source", "destination"])
def test_closed_account_rejects_transfer_without_financial_changes(
    workspace: Workspace, api: TestClient, migrator_engine: Engine, closed_side: str
) -> None:
    closed_id = workspace.src if closed_side == "source" else workspace.dst
    with migrator_engine.begin() as conn:
        conn.execute(
            text("UPDATE ledgerops.accounts SET status='closed' WHERE id=:id"), {"id": closed_id}
        )

    def snapshot() -> tuple[object, ...]:
        with Session(migrator_engine) as db:
            return (
                db.scalar(
                    text("SELECT count(*) FROM ledgerops.transfers WHERE actor_id=:actor"),
                    {"actor": workspace.actor},
                ),
                db.scalar(
                    text("SELECT count(*) FROM ledgerops.journal_entries WHERE actor_id=:actor"),
                    {"actor": workspace.actor},
                ),
                sorted(
                    (str(a["id"]), str(a["ledger_balance"]), str(a["available_balance"]))
                    for a in accounts(db, workspace.actor)
                ),
            )

    before = snapshot()
    token = login(api, workspace.email)["csrf_token"]
    response = api.post(
        "/api/v1/transfers",
        json={
            "source_id": str(workspace.src),
            "destination_id": str(workspace.dst),
            "amount": "1.00",
            "currency": "INR",
        },
        headers={"X-CSRF-Token": str(token), "Idempotency-Key": "closed-account"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_unavailable"
    assert snapshot() == before
