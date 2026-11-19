"""Real PostgreSQL reservation, transfer and expiry invariants."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance import holds
from app.modules.finance.transfers import transfer
from tests.helpers import FakeClock
from tests.integration.conftest import UserFactory, Workspace, login


def test_hold_lifecycle(api: TestClient, workspace: Workspace) -> None:
    url = f"/api/v1/accounts/{workspace.src}"
    headers = {
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
        "Idempotency-Key": "create",
    }
    body = {"amount": "700.00", "reason": "Inventory", "currency": "INR"}
    assert api.post(url + "/holds", json=body).status_code == 403
    created = api.post(url + "/holds", headers=headers, json=body)
    assert created.status_code == 201, created.text
    assert api.post(url + "/holds", headers=headers, json=body).json() == created.json()
    assert (
        api.post(url + "/holds", headers=headers, json={**body, "amount": "1"}).status_code == 409
    )
    hold = "/api/v1/holds/" + created.json()["hold_id"]
    balance = api.get(url).json()
    assert (balance["ledger_balance"], balance["held_amount"], balance["available_balance"]) == (
        "1000.00",
        "700.00",
        "300.00",
    )
    assert (
        api.post(
            url + "/holds", headers={**headers, "Idempotency-Key": "second"}, json=body
        ).status_code
        == 409
    )
    tx = {
        "source_id": str(workspace.src),
        "destination_id": str(workspace.dst),
        "amount": "350.00",
        "currency": "INR",
    }
    assert api.post("/api/v1/transfers", headers=headers, json=tx).status_code == 409
    headers["Idempotency-Key"] = "partial"
    release = {"amount": "125.00", "currency": "INR"}
    result = api.post(hold + "/release", headers=headers, json=release)
    assert result.status_code == 200, result.text
    assert result.json()["remaining"] == "575.00"
    assert api.post(hold + "/release", headers=headers, json=release).json() == result.json()
    assert (
        api.post(hold + "/release", headers=headers, json={**release, "amount": "2"}).status_code
        == 409
    )
    headers["Idempotency-Key"] = "release"
    assert (
        api.post(hold + "/release", headers=headers, json={"currency": "INR"}).json()["remaining"]
        == "0.00"
    )
    headers["Idempotency-Key"] = "terminal"
    assert api.post(hold + "/release", headers=headers, json=release).status_code == 409
    record = api.get(hold).json()
    assert record["status"] == "released"
    assert {e["kind"] for e in record["events"]} == {"created", "partially_released", "released"}
    assert api.get(url + "/holds?offset=1").json() == []
    balance = api.get(url).json()
    assert balance["ledger_balance"] == balance["available_balance"] == "1000.00"


@pytest.mark.parametrize("access", ["account", "accounts", "holds", "hold", "transfer"])
def test_due_hold_expires_once(
    api: TestClient, workspace: Workspace, clock: FakeClock, runtime_engine: Engine, access: str
) -> None:
    url = f"/api/v1/accounts/{workspace.src}"
    headers = {
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
        "Idempotency-Key": "exp",
    }
    due = clock.now() + timedelta(minutes=2)
    result = api.post(
        url + "/holds",
        headers=headers,
        json={
            "currency": "INR",
            "amount": "800",
            "reason": "Expiry",
            "expires_at": due.isoformat(),
        },
    )
    hold = result.json()["hold_id"]
    clock.advance(timedelta(minutes=2))
    if access == "transfer":
        request = api.post(
            "/api/v1/transfers",
            headers=headers,
            json={
                "source_id": str(workspace.src),
                "destination_id": str(workspace.dst),
                "amount": "800",
                "currency": "INR",
            },
        )
        assert request.status_code == 201, request.text
    else:
        path = {
            "account": url,
            "accounts": "/api/v1/accounts",
            "holds": url + "/holds",
            "hold": "/api/v1/holds/" + hold,
        }[access]
        assert api.get(path).status_code == 200
    with runtime_engine.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT status FROM ledgerops.account_holds WHERE id=:id"), {"id": hold}
            )
            == "expired"
        )
    assert api.get(url).json()["held_amount"] == "0.00"
    record = api.get("/api/v1/holds/" + hold).json()
    assert sorted(e["kind"] for e in record["events"]) == ["created", "expired"]
    with runtime_engine.connect() as conn:
        assert (
            conn.scalar(
                text("""SELECT count(*) FROM ledgerops.audit_events
            WHERE action='account_hold.expired' AND target_id=:id"""),
                {"id": hold},
            )
            == 1
        )


def test_capture_requires_posted_transfer(workspace: Workspace, api: TestClient) -> None:
    url = f"/api/v1/accounts/{workspace.src}"
    headers = {
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
        "Idempotency-Key": "hold",
    }
    hold = api.post(
        url + "/holds",
        headers=headers,
        json={"amount": "600", "currency": "INR", "reason": "Order"},
    ).json()["hold_id"]
    tx = {
        "source_id": str(workspace.src),
        "destination_id": str(workspace.dst),
        "currency": "INR",
        "amount": "599.99",
        "hold_id": hold,
    }
    assert api.post("/api/v1/transfers", headers=headers, json=tx).status_code == 409
    tx["amount"] = "600.00"
    result = api.post("/api/v1/transfers", headers=headers, json=tx)
    assert result.status_code == 201, result.text
    assert api.post("/api/v1/transfers", headers=headers, json=tx).json() == result.json()
    record = api.get("/api/v1/holds/" + hold).json()
    assert record["status"] == "captured"
    assert next(e for e in record["events"] if e["kind"] == "captured")["journal_id"]
    balance = api.get(url).json()
    assert balance["ledger_balance"] == balance["available_balance"] == "400.00"


@pytest.mark.parametrize("other", ["hold", "transfer", "duplicate"])
def test_competing_reservations(
    workspace: Workspace, runtime_engine: Engine, clock: FakeClock, other: str
) -> None:
    barrier = Barrier(2)

    def submit(index: int) -> str:
        with Session(runtime_engine) as db:
            barrier.wait(timeout=10)
            try:
                if index and other == "transfer":
                    transfer(
                        db,
                        workspace.actor,
                        workspace.src,
                        workspace.dst,
                        Decimal("700"),
                        "Concurrent",
                        "tx",
                        AuditWriter(clock),
                        None,
                    )
                    return "posted"
                _, created = holds.change(
                    db,
                    workspace.actor,
                    workspace.src,
                    None,
                    Decimal("700"),
                    str(index) if other != "duplicate" else "same",
                    AuditWriter(clock),
                    None,
                    reason="Concurrent",
                )
                db.commit()
                return "posted" if created else "replayed"
            except AppError as exc:
                db.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, [0, 1]))
    assert sorted(outcomes) == sorted(
        ["posted", "replayed" if other == "duplicate" else "insufficient_funds"]
    )
    with runtime_engine.connect() as conn:
        row = conn.execute(
            text("""SELECT ledger_balance,held_amount,available_balance,
            (SELECT coalesce(sum(remaining),0) FROM ledgerops.account_holds WHERE account_id=a.id)
            FROM ledgerops.accounts a JOIN ledgerops.account_balances b USING(ledger_id)
            WHERE a.id=:id"""),
            {"id": workspace.src},
        ).one()
        assert row[2] == Decimal("300")
        assert row[1] == row[3]
        assert row[0] - row[1] == row[2]


@pytest.mark.parametrize(
    "point", ["INSERT INTO ledgerops.hold_events", "INSERT INTO ledgerops.audit_events"]
)
def test_hold_command_rolls_back(
    workspace: Workspace, runtime_engine: Engine, clock: FakeClock, point: str
) -> None:
    def inject(
        _conn: object, _cursor: object, statement: str, _params: object, _ctx: object, _many: bool
    ) -> None:
        if point in statement:
            raise RuntimeError("injected")

    with runtime_engine.connect() as conn, Session(conn) as db:
        event.listen(conn, "after_cursor_execute", inject)
        with pytest.raises(RuntimeError, match="injected"):
            holds.change(
                db,
                workspace.actor,
                workspace.src,
                None,
                Decimal("100"),
                "fail",
                AuditWriter(clock),
                None,
                reason="Rollback",
            )
        db.rollback()
    with runtime_engine.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT count(*) FROM ledgerops.hold_events WHERE account_id=:id"),
                {"id": workspace.src},
            )
            == 0
        )
        assert (
            conn.scalar(
                text("""SELECT held_amount FROM ledgerops.accounts
            JOIN ledgerops.account_balances USING(ledger_id) WHERE id=:id"""),
                {"id": workspace.src},
            )
            == 0
        )
        assert not conn.scalar(
            text("""SELECT has_column_privilege(current_user,
            'ledgerops.account_balances','held_amount','UPDATE')
            OR has_table_privilege(current_user,
            'ledgerops.account_holds','UPDATE') OR has_table_privilege(current_user,
            'ledgerops.hold_events','DELETE')""")
        )


@pytest.mark.parametrize("status", ["frozen", "closed"])
def test_unusable_accounts_allow_history_only(
    api: TestClient, workspace: Workspace, migrator_engine: Engine, status: str
) -> None:
    url = f"/api/v1/accounts/{workspace.src}/holds"
    headers = {
        "Idempotency-Key": "original",
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
    }
    body = {"currency": "INR", "amount": "5.00", "reason": "Order"}
    hold = api.post(url, json=body, headers=headers).json()["hold_id"]
    with migrator_engine.begin() as conn:
        conn.execute(
            text("UPDATE ledgerops.accounts SET status=:status WHERE id=:id"),
            {"status": status, "id": workspace.src},
        )
    headers["Idempotency-Key"] = "another"
    assert api.post(url, json=body, headers=headers).status_code == 409
    assert (
        api.post(
            f"/api/v1/holds/{hold}/release", json={"currency": "INR"}, headers=headers
        ).status_code
        == 409
    )
    assert api.get(url).json()[0]["remaining"] == "5.00"


@pytest.mark.parametrize(
    ("platform", "membership", "expected"),
    [
        ("operator", "member", 403),
        ("operator", "administrator", 200),
        ("operator", "owner", 200),
        ("operator", "viewer", 403),
        ("admin", None, 404),
        ("auditor", "owner", 403),
        ("viewer", "owner", 403),
        ("approver", "owner", 403),
    ],
)
def test_release_authority(
    api: TestClient,
    workspace: Workspace,
    make_user: UserFactory,
    migrator_engine: Engine,
    platform: str,
    membership: str | None,
    expected: int,
) -> None:
    url = f"/api/v1/accounts/{workspace.src}/holds"
    headers = {
        "Idempotency-Key": "owner",
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
    }
    hold = api.post(
        url, json={"amount": "10", "reason": "Order", "currency": "INR"}, headers=headers
    ).json()["hold_id"]
    other = make_user((platform,))
    if membership:
        with migrator_engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO ledgerops.customer_members(customer_id,user_id,role)
                SELECT customer_id,:user,:role FROM ledgerops.accounts WHERE id=:account
            """),
                {"role": membership, "user": other.id, "account": workspace.src},
            )
    api.cookies.clear()
    headers["X-CSRF-Token"] = str(login(api, other.email)["csrf_token"])
    if platform == "auditor":
        assert api.get(url).status_code == 200
    if membership is None:
        assert api.get("/api/v1/holds/" + hold).status_code == 404
    response = api.post(
        "/api/v1/holds/" + hold + "/release", json={"currency": "INR"}, headers=headers
    )
    assert response.status_code == expected, response.text


def test_initiating_member_can_release(
    api: TestClient, workspace: Workspace, migrator_engine: Engine
) -> None:
    with migrator_engine.begin() as conn:
        conn.execute(
            text("UPDATE ledgerops.customer_members SET role='member' WHERE user_id=:id"),
            {"id": workspace.actor},
        )
    headers = {
        "Idempotency-Key": "initial",
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
    }
    result = api.post(
        f"/api/v1/accounts/{workspace.src}/holds",
        headers=headers,
        json={"amount": "5", "reason": "Order", "currency": "INR"},
    )
    hold = result.json()["hold_id"]
    assert (
        api.post(
            "/api/v1/holds/" + hold + "/release", headers=headers, json={"currency": "INR"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("due", [True, False])
def test_concurrent_release_and_expiry(
    workspace: Workspace, clock: FakeClock, runtime_engine: Engine, due: bool
) -> None:
    audit = AuditWriter(clock)
    with Session(runtime_engine) as db:
        result, _ = holds.change(
            db,
            workspace.actor,
            workspace.src,
            None,
            Decimal("70"),
            "create",
            audit,
            None,
            reason="Expiry",
            expires=clock.now() + timedelta(seconds=1),
        )
        db.commit()
    if due:
        clock.advance(timedelta(seconds=1))
    barrier = Barrier(2)

    def submit(index: int) -> str:
        with Session(runtime_engine) as db:
            barrier.wait(timeout=10)
            try:
                if due and index:
                    holds.refresh(db, workspace.actor, workspace.src, audit, None)
                    db.commit()
                    return "read"
                response, _ = holds.change(
                    db,
                    workspace.actor,
                    workspace.src,
                    result["hold_id"],
                    None,
                    str(index),
                    audit,
                    None,
                )
                db.commit()
                return str(response["kind"])
            except AppError as err:
                return err.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, [0, 1]))
    assert sorted(outcomes) == sorted(["invalid_release", "read" if due else "released"])
    with runtime_engine.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT count(*) FROM ledgerops.hold_events WHERE hold_id=:id"),
                {"id": result["hold_id"]},
            )
            == 2
        )
        assert conn.scalar(
            text("""SELECT b.available_balance FROM ledgerops.account_balances b
            JOIN ledgerops.accounts a USING(ledger_id) WHERE a.id=:id"""),
            {"id": workspace.src},
        ) == Decimal("1000")


def test_capture_audit_failure_restores_reservation(
    workspace: Workspace, runtime_engine: Engine, clock: FakeClock
) -> None:
    audit = AuditWriter(clock)
    with Session(runtime_engine) as db:
        result, _ = holds.change(
            db,
            workspace.actor,
            workspace.src,
            None,
            Decimal("60"),
            "create",
            audit,
            None,
            reason="Capture",
        )
        db.commit()

    def fail(
        _conn: object, _cursor: object, stmt: str, _params: object, _context: object, _many: bool
    ) -> None:
        if "UPDATE ledgerops.journal_entries" in stmt:
            raise RuntimeError("injected posting failure")

    with runtime_engine.connect() as conn, Session(conn) as db:
        event.listen(conn, "after_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="injected posting"):
            transfer(
                db,
                workspace.actor,
                workspace.src,
                workspace.dst,
                Decimal("60"),
                "Capture",
                "tx",
                audit,
                None,
                result["hold_id"],
            )
    with Session(runtime_engine) as db:
        assert holds.detail(db, result["hold_id"])["remaining"] == "60.00"
        assert (
            db.scalar(
                text("SELECT count(*) FROM ledgerops.transfers WHERE actor_id=:id"),
                {"id": workspace.actor},
            )
            == 0
        )
        assert (
            db.scalar(
                text("SELECT count(*) FROM ledgerops.hold_events WHERE hold_id=:id"),
                {"id": result["hold_id"]},
            )
            == 1
        )


@pytest.mark.parametrize("operation", ["release", "transfer"])
def test_rejected_command_commits_only_due_expiry(
    api: TestClient, workspace: Workspace, runtime_engine: Engine, clock: FakeClock, operation: str
) -> None:
    headers = {
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
        "Idempotency-Key": "create",
    }
    result = api.post(
        f"/api/v1/accounts/{workspace.src}/holds",
        headers=headers,
        json={
            "amount": "800.00",
            "currency": "INR",
            "reason": "Temporary",
            "expires_at": (clock.now() + timedelta(seconds=1)).isoformat(),
        },
    )
    hold = result.json()["hold_id"]
    clock.advance(timedelta(seconds=1))
    if operation == "release":
        res = api.post(f"/api/v1/holds/{hold}/release", headers=headers, json={"currency": "INR"})
    else:
        res = api.post(
            "/api/v1/transfers",
            headers=headers,
            json={
                "amount": "1000.01",
                "currency": "INR",
                "source_id": str(workspace.src),
                "destination_id": str(workspace.dst),
            },
        )
    assert res.status_code == 409
    with runtime_engine.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT status FROM ledgerops.account_holds WHERE id=:id"), {"id": hold}
            )
            == "expired"
        )
        assert (
            conn.scalar(
                text("SELECT count(*) FROM ledgerops.transfers WHERE actor_id=:id"),
                {"id": workspace.actor},
            )
            == 0
        )


def test_invalid_hold_money_and_past_expiry(
    api: TestClient, workspace: Workspace, clock: FakeClock
) -> None:
    headers = {
        "X-CSRF-Token": str(login(api, workspace.email)["csrf_token"]),
        "Idempotency-Key": "invalid",
    }
    base = {"amount": "0.01", "currency": "INR", "reason": "Order"}
    url = f"/api/v1/accounts/{workspace.src}/holds"
    for changes in (
        {"amount": 1.01},
        {"amount": "1.001"},
        {"amount": "0"},
        {"currency": "USD"},
        {"expires_at": clock.now().isoformat()},
        {"expires_at": "2026-11-20T00:00:00"},
    ):
        assert api.post(url, json={**base, **changes}, headers=headers).status_code == 422
    assert api.get(url).json() == []
