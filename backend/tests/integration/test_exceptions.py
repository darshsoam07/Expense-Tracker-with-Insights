"""PostgreSQL coverage for operational exception investigations."""

import inspect
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance import exceptions, payments
from app.modules.finance import operations as ops
from app.modules.finance.approvals import decide
from app.modules.finance.payment_rails import SimulatedRail
from app.modules.finance.transfers import transfer
from tests.helpers import FakeClock
from tests.integration.conftest import UserFactory, Workspace, login
from tests.integration.test_operations import HEADER
from tests.integration.test_payments import make_payment
from tests.integration.test_pending_submission import configure


def customer_of(db: Session, workspace: Workspace) -> UUID:
    return UUID(
        str(
            db.scalar(
                text("SELECT customer_id FROM ledgerops.accounts WHERE id=:id"),
                {"id": workspace.src},
            )
        )
    )


def add_member(
    engine: Engine, customer: UUID, user: UUID, role: str = "member", active: bool = True
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledgerops.customer_members(customer_id,user_id,role,active) "
                "VALUES(:customer,:user,:role,:active)"
            ),
            {"customer": customer, "user": user, "role": role, "active": active},
        )


def new_exception(
    db: Session, workspace: Workspace, clock: FakeClock, kind: str = "payment_failed"
) -> UUID:
    ident = exceptions.generate(
        db, customer_of(db, workspace), "payment", uuid4(), kind, workspace.actor, clock.now()
    )
    db.commit()
    return ident


def count_exceptions(db: Session, source: object, kind: str) -> int:
    return int(
        db.scalar(
            text(
                "SELECT count(*) FROM ledgerops.exceptions "
                "WHERE source_reference=:source AND exception_type=:kind"
            ),
            {"source": source, "kind": kind},
        )
        or 0
    )


def race(engine: Engine, jobs: list[Callable[[Session], object]]) -> list[object]:
    """Run each job in its own session and transaction, released together by a barrier."""
    barrier = Barrier(len(jobs))

    def run(job: Callable[[Session], object]) -> object:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                job(session)
            except AppError as exc:
                return exc.code
            return "ok"

    with ThreadPoolExecutor(len(jobs)) as pool:
        return list(pool.map(run, jobs))


# ------------------------------------------------------------------ generation


def test_failed_and_unknown_payments_create_one_exception(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    audit = AuditWriter(clock)
    cases: tuple[
        tuple[Literal["rejected", "timeout"], Literal["payment_failed", "payment_outcome_unknown"]],
        ...,
    ] = (("rejected", "payment_failed"), ("timeout", "payment_outcome_unknown"))
    for outcome, expected in cases:
        payment = make_payment(db, workspace, clock, key=outcome, amount=Decimal("100"))
        payments.submit(
            db, workspace.actor, UUID(str(payment["id"])), audit, None, SimulatedRail(outcome)
        )
        assert count_exceptions(db, payment["id"], expected) == 1


def test_expired_approval_creates_one_exception(
    db: Session,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    reviewers = [make_user(("approver",)).id for _ in range(2)]
    with migrator_engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO ledgerops.user_roles(user_id,role_id,granted_at,granted_by)
            SELECT :maker,id,now(),'system:test' FROM ledgerops.roles WHERE code='approver'"""),
            {"maker": workspace.actor},
        )
    for reviewer in reviewers:
        add_member(migrator_engine, customer_of(db, workspace), reviewer)
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
    clock.advance(timedelta(hours=2))
    with pytest.raises(AppError, match="expired"):
        decide(db, reviewers[0], approval, "approve", "late", audit, None)
    assert count_exceptions(db, approval, "approval_expired") == 1
    row = db.execute(
        text(
            "SELECT source_domain,severity,status FROM ledgerops.exceptions "
            "WHERE source_reference=:s"
        ),
        {"s": approval},
    ).one()
    assert tuple(row) == ("approval", "medium", "open")


def test_settlement_failure_creates_one_exception_and_retry_is_idempotent(
    db: Session, workspace: Workspace, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = AuditWriter(clock)
    payment = make_payment(db, workspace, clock, key="settle-fail", amount=Decimal("10"))
    pid = UUID(str(payment["id"]))
    payments.submit(db, workspace.actor, pid, audit, None)
    batch = ops.batch(db, customer_of(db, workspace), workspace.actor, audit, None)

    def unavailable(
        session: Session, payment: UUID, user: UUID, writer: AuditWriter, request: str | None
    ) -> UUID:
        raise AppError(409, "insufficient_nostro", "Test liquidity limit")

    monkeypatch.setattr(ops, "settle", unavailable)
    ops.process(db, batch["id"], workspace.actor, audit, None)
    assert count_exceptions(db, pid, "settlement_failed") == 1
    ops.process(db, batch["id"], workspace.actor, audit, None)  # retry fails again
    assert count_exceptions(db, pid, "settlement_failed") == 1


def statement_for(payment: dict[str, object], clock: FakeClock, **overrides: str) -> bytes:
    day = clock.now().date().isoformat()
    fields = {"amount": "10.00", "direction": "outbound", "status": "settled", **overrides}
    return (
        HEADER + f"{payment['provider_reference']},ext-{uuid4().hex[:8]},{fields['amount']},INR,"
        f"{day},{day},{fields['direction']},{fields['status']}\n"
    ).encode()


@pytest.mark.parametrize(
    ("overrides", "expected", "severity"),
    [
        ({"direction": "inbound"}, "direction_mismatch", "high"),
        ({"status": "failed"}, "status_mismatch", "medium"),
        ({"amount": "11.00"}, "amount_mismatch", "high"),
    ],
)
def test_reconciliation_discrepancies_create_exactly_one_exception(
    db: Session,
    workspace: Workspace,
    clock: FakeClock,
    overrides: dict[str, str],
    expected: str,
    severity: str,
) -> None:
    audit, actor = AuditWriter(clock), workspace.actor
    customer = customer_of(db, workspace)
    payment = make_payment(db, workspace, clock, key=expected, amount=Decimal("10"))
    payments.submit(db, actor, UUID(str(payment["id"])), audit, None)
    batch = ops.batch(db, customer, actor, audit, None)
    ops.process(db, batch["id"], actor, audit, None)
    imported = ops.ingest(
        db, customer, actor, "rail.csv", statement_for(payment, clock, **overrides), audit, None
    )
    run = ops.reconcile(db, imported["id"], actor, audit, None)
    rows = ops.children(db, "reconciliation-runs", actor, run["id"], 25, 0)
    assert [row["classification"] for row in rows] == [expected]
    source = rows[0]["line_id"]

    def stored() -> list[tuple[str, str]]:
        return [
            (str(r[0]), str(r[1]))
            for r in db.execute(
                text(
                    "SELECT exception_type,severity FROM ledgerops.exceptions "
                    "WHERE source_domain='reconciliation' AND source_reference=:source"
                ),
                {"source": source},
            )
        ]

    assert stored() == [(expected, severity)]
    ops.reconcile(db, imported["id"], actor, audit, None)  # reconciling again must not duplicate
    assert stored() == [(expected, severity)]


def test_exact_match_creates_no_exception(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    audit, actor = AuditWriter(clock), workspace.actor
    customer = customer_of(db, workspace)
    payment = make_payment(db, workspace, clock, key="exact", amount=Decimal("10"))
    payments.submit(db, actor, UUID(str(payment["id"])), audit, None)
    ops.process(db, ops.batch(db, customer, actor, audit, None)["id"], actor, audit, None)
    imported = ops.ingest(
        db, customer, actor, "rail.csv", statement_for(payment, clock), audit, None
    )
    run = ops.reconcile(db, imported["id"], actor, audit, None)
    assert ops.children(db, "reconciliation-runs", actor, run["id"], 25, 0)[0][
        "classification"
    ] == ("exact_match")
    assert (
        db.scalar(
            text("SELECT count(*) FROM ledgerops.exceptions WHERE source_reference=:s"),
            {"s": ops.children(db, "reconciliation-runs", actor, run["id"], 25, 0)[0]["line_id"]},
        )
        == 0
    )


def test_every_reconciliation_classification_has_an_exception_rule() -> None:
    """Fails if reconcile() gains a classification that would silently raise no exception."""
    emitted = set(re.findall(r"THEN\s+'(\w+)'", inspect.getsource(ops.reconcile)))
    emitted |= set(re.findall(r"ELSE\s+'(\w+)'", inspect.getsource(ops.reconcile)))
    assert emitted - {"exact_match"} == set(exceptions.RECONCILIATION_TYPES)
    assert set(exceptions.RECONCILIATION_TYPES) <= set(exceptions.RULES)


# ------------------------------------------------------------------ lifecycle


def test_exception_lifecycle_is_scoped_audited_and_non_financial(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    audit = AuditWriter(clock)
    before = db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries"))
    ident = new_exception(db, workspace, clock)
    queue = exceptions.page(db, workspace.actor, 25, 0, {})
    assert [item["id"] for item in queue["items"]] == [ident]
    assert queue["total"] == 1
    exceptions.assign(db, workspace.actor, ident, workspace.actor, audit, "request-1")
    exceptions.transition(db, workspace.actor, ident, "investigating", "", audit, "request-1")
    exceptions.note(db, workspace.actor, ident, "Rail evidence attached.", audit, "request-1")
    resolved = exceptions.transition(
        db, workspace.actor, ident, "resolved", "Confirmed simulation failure.", audit, "request-1"
    )
    closed = exceptions.transition(
        db, workspace.actor, ident, "closed", "Investigation complete.", audit, "request-1"
    )
    assert resolved["resolution_summary"] == "Confirmed simulation failure."
    assert closed["status"] == "closed"
    assert [item["kind"] for item in closed["events"]] == [
        "created",
        "assigned",
        "status_changed",
        "note_added",
        "resolved",
        "status_changed",
    ]
    # The clock never moved: order comes from the event sequence, not from timestamps.
    assert len({item["occurred_at"] for item in closed["events"]}) == 1
    assert db.scalar(text("SELECT count(*) FROM ledgerops.journal_entries")) == before
    assert (
        db.scalar(
            text(
                "SELECT count(*) FROM ledgerops.audit_events WHERE target_type='exception' AND "
                "target_id=:id"
            ),
            {"id": str(ident)},
        )
        == 5
    )


def test_events_keep_order_when_the_clock_advances(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    audit = AuditWriter(clock)
    ident = new_exception(db, workspace, clock)
    for status, reason in (("investigating", ""), ("awaiting_information", "Need rail evidence")):
        clock.advance(timedelta(minutes=5))
        exceptions.transition(db, workspace.actor, ident, status, reason, audit, None)
    events = exceptions.detail(db, workspace.actor, ident)["events"]
    assert [e["kind"] for e in events] == ["created", "status_changed", "status_changed"]
    assert [e["occurred_at"] for e in events] == sorted(e["occurred_at"] for e in events)


@pytest.mark.parametrize(
    ("status", "reason", "code"),
    [
        ("awaiting_information", "", "reason_required"),
        ("awaiting_information", "x" * (exceptions.REASON_MAX + 1), "reason_too_long"),
        ("investigating", "x" * (exceptions.REASON_MAX + 1), "reason_too_long"),
    ],
)
def test_transition_reason_rules(
    db: Session, workspace: Workspace, clock: FakeClock, status: str, reason: str, code: str
) -> None:
    ident = new_exception(db, workspace, clock)
    with pytest.raises(AppError) as caught:
        exceptions.transition(db, workspace.actor, ident, status, reason, AuditWriter(clock), None)
    assert caught.value.code == code


def test_text_limits_match_the_documented_contract(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    audit = AuditWriter(clock)
    ident = new_exception(db, workspace, clock)
    exceptions.transition(db, workspace.actor, ident, "investigating", "", audit, None)
    exceptions.note(db, workspace.actor, ident, "n" * exceptions.NOTE_MAX, audit, None)
    with pytest.raises(AppError, match="within 2000"):
        exceptions.note(db, workspace.actor, ident, "n" * (exceptions.NOTE_MAX + 1), audit, None)
    summary = "s" * exceptions.NOTE_MAX  # resolution summaries use the longer limit
    resolved = exceptions.transition(db, workspace.actor, ident, "resolved", summary, audit, None)
    assert resolved["resolution_summary"] == summary


def test_exception_source_dedupe_and_event_history_are_immutable(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    customer = customer_of(db, workspace)
    source = uuid4()
    first = exceptions.generate(
        db, customer, "reconciliation", source, "amount_mismatch", None, clock.now()
    )
    second = exceptions.generate(
        db, customer, "reconciliation", source, "amount_mismatch", None, clock.now()
    )
    db.commit()
    assert first == second
    with pytest.raises(Exception, match="append-only"):
        db.execute(
            text("DELETE FROM ledgerops.exception_events WHERE exception_id=:id"), {"id": first}
        )
    db.rollback()


def test_failed_exception_audit_rolls_back_mutation(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    ident = new_exception(db, workspace, clock)

    def fail_audit(
        conn: object, cursor: object, statement: str, params: object, context: object, many: bool
    ) -> None:
        if "audit_events" in statement and "exception.investigating" in str(params):
            raise RuntimeError("audit unavailable")

    event.listen(db.connection(), "after_cursor_execute", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        exceptions.transition(
            db, workspace.actor, ident, "investigating", "", AuditWriter(clock), "request-1"
        )
    db.rollback()
    assert exceptions.detail(db, workspace.actor, ident)["status"] == "open"
    assert len(exceptions.detail(db, workspace.actor, ident)["events"]) == 1


def test_failed_assignment_audit_rolls_back_assignment_and_event(
    db: Session, workspace: Workspace, clock: FakeClock
) -> None:
    ident = new_exception(db, workspace, clock)

    def fail_audit(
        conn: object, cursor: object, statement: str, params: object, context: object, many: bool
    ) -> None:
        if "audit_events" in statement and "exception.assigned" in str(params):
            raise RuntimeError("audit unavailable")

    event.listen(db.connection(), "after_cursor_execute", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        exceptions.assign(db, workspace.actor, ident, workspace.actor, AuditWriter(clock), None)
    db.rollback()
    record = exceptions.detail(db, workspace.actor, ident)
    assert record["assigned_user_id"] is None
    assert [e["kind"] for e in record["events"]] == ["created"]


def test_exception_isolated_from_non_member(
    db: Session, workspace: Workspace, clock: FakeClock, make_user: UserFactory
) -> None:
    ident = new_exception(db, workspace, clock)
    outsider = make_user(("operator",))
    with pytest.raises(AppError, match="Exception unavailable"):
        exceptions.detail(db, outsider.id, ident)
    assert exceptions.page(db, outsider.id, 25, 0, {}) == {
        "items": [],
        "total": 0,
        "limit": 25,
        "offset": 0,
    }


# ------------------------------------------------------------------ assignment


def test_assignee_discovery_never_leaves_the_customer_or_lists_unqualified_members(
    db: Session,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    customer = customer_of(db, workspace)
    ident = new_exception(db, workspace, clock)
    colleague = make_user(("operator",))
    viewer = make_user(("operator",))
    departed = make_user(("operator",))
    stranger = make_user(("operator",))  # a member of a different customer only
    add_member(migrator_engine, customer, colleague.id)
    add_member(migrator_engine, customer, viewer.id, role="viewer")
    add_member(migrator_engine, customer, departed.id, active=False)
    other = new_exception_for_other_customer(db, migrator_engine, stranger, clock)
    assert other != ident
    listed = {UUID(str(a["id"])) for a in exceptions.assignees(db, workspace.actor, ident)}
    assert listed == {workspace.actor, colleague.id}
    with pytest.raises(AppError, match="Exception unavailable"):
        exceptions.assignees(db, viewer.id, ident)  # viewer membership cannot manage
    with pytest.raises(AppError, match="Exception unavailable"):
        exceptions.assignees(db, stranger.id, ident)


def new_exception_for_other_customer(
    db: Session, migrator_engine: Engine, user: Any, clock: FakeClock
) -> UUID:
    from app.modules.finance.provision import provision

    with Session(migrator_engine) as session, session.begin():
        provision(session, user.id)
        customer = session.scalar(
            text("SELECT customer_id FROM ledgerops.customer_members WHERE user_id=:u"),
            {"u": user.id},
        )
    ident = exceptions.generate(
        db, customer, "payment", uuid4(), "payment_failed", None, clock.now()
    )
    db.commit()
    return ident


def test_assignment_and_reassignment_are_recorded_and_validated(
    db: Session,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    customer = customer_of(db, workspace)
    audit = AuditWriter(clock)
    ident = new_exception(db, workspace, clock)
    colleague, viewer, departed, stranger = (make_user(("operator",)) for _ in range(4))
    add_member(migrator_engine, customer, colleague.id)
    add_member(migrator_engine, customer, viewer.id, role="viewer")
    add_member(migrator_engine, customer, departed.id, active=False)

    first = exceptions.assign(db, workspace.actor, ident, colleague.id, audit, "r1")
    assert first["assigned_user_id"] == colleague.id
    second = exceptions.assign(db, workspace.actor, ident, workspace.actor, audit, "r2")
    assert second["assigned_user_id"] == workspace.actor
    kinds = [e["kind"] for e in second["events"]]
    assert kinds == ["created", "assigned", "reassigned"]
    assert second["events"][2]["metadata"]["previous_assigned_user_id"] == str(colleague.id)
    assert second["events"][1]["metadata"]["assigned_name"] == "Test User"

    again = exceptions.assign(db, workspace.actor, ident, workspace.actor, audit, "r3")
    assert [e["kind"] for e in again["events"]] == kinds  # same assignee: no new history

    for bad in (viewer.id, departed.id, stranger.id, uuid4()):
        with pytest.raises(AppError) as caught:
            exceptions.assign(db, workspace.actor, ident, bad, audit, None)
        assert caught.value.code == "invalid_assignee"

    for status, reason in (("investigating", ""), ("resolved", "Done"), ("closed", "Closed out")):
        exceptions.transition(db, workspace.actor, ident, status, reason, audit, None)
    with pytest.raises(AppError) as closed:
        exceptions.assign(db, workspace.actor, ident, colleague.id, audit, None)
    assert closed.value.code == "exception_closed"


# ------------------------------------------------------------------ queue


def test_queue_filters_total_and_pagination_boundaries(
    db: Session,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    customer = customer_of(db, workspace)
    audit = AuditWriter(clock)
    plan = [
        ("payment", "payment_failed"),
        ("approval", "approval_expired"),
        ("settlement", "settlement_failed"),
        ("reconciliation", "direction_mismatch"),
        ("reconciliation", "timing_difference"),
    ]
    made: list[UUID] = []
    for domain, kind in plan:
        made.append(
            exceptions.generate(db, customer, domain, uuid4(), kind, workspace.actor, clock.now())
        )
        db.commit()
        clock.advance(timedelta(days=1))
    exceptions.transition(db, workspace.actor, made[0], "investigating", "", audit, None)
    exceptions.assign(db, workspace.actor, made[1], workspace.actor, audit, None)
    # Another customer's exception must not leak into this user's queue or total.
    stranger = make_user(("operator",))
    new_exception_for_other_customer(db, migrator_engine, stranger, clock)

    def total(**filters: object) -> int:
        return int(exceptions.page(db, workspace.actor, 25, 0, filters)["total"])

    assert total() == 5
    assert total(status="open") == 4
    assert total(status="investigating") == 1
    assert total(status="closed") == 0
    assert total(severity="high") == 3
    assert total(severity="low") == 1
    assert total(exception_type="direction_mismatch") == 1
    assert total(source_domain="reconciliation") == 2
    assert total(assigned_user_id=str(workspace.actor)) == 1
    assert total(customer_id=str(customer)) == 5
    assert total(customer_id=str(uuid4())) == 0
    assert total(status="open", severity="high", source_domain="settlement") == 1

    # Created-on boundaries are inclusive at the start and exclusive at the end.
    day2 = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    assert total(created_after=day2, created_before=day2 + timedelta(days=1)) == 1
    assert (
        total(created_after=day2 + timedelta(seconds=1), created_before=day2 + timedelta(days=1))
        == 0
    )
    assert total(created_before=day2) == 1

    seen: list[UUID] = []
    for offset, expected in ((0, 2), (2, 2), (4, 1), (5, 0), (500, 0)):
        result = exceptions.page(db, workspace.actor, 2, offset, {})
        assert (len(result["items"]), result["total"], result["limit"], result["offset"]) == (
            expected,
            5,
            2,
            offset,
        )
        seen += [UUID(str(item["id"])) for item in result["items"]]
    assert seen == list(reversed(made))  # newest first, no gaps, no repeats
    assert all(
        item["customer_id"] == customer
        for item in exceptions.page(db, workspace.actor, 25, 0, {})["items"]
    )


# ------------------------------------------------------------------ API: read versus manage


@pytest.mark.parametrize(
    ("role", "read", "manage"),
    [
        ("operator", 200, 200),
        ("admin", 200, 200),
        ("approver", 200, 403),
        ("auditor", 200, 403),
        ("viewer", 403, 403),
    ],
)
def test_read_and_manage_permissions_by_role(
    db: Session,
    api_app: FastAPI,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
    role: str,
    read: int,
    manage: int,
) -> None:
    ident = new_exception(db, workspace, clock)
    user = make_user((role,))
    add_member(migrator_engine, customer_of(db, workspace), user.id)
    with TestClient(api_app, raise_server_exceptions=False) as client:
        token = str(login(client, user.email)["csrf_token"])
        headers = {"X-CSRF-Token": token}
        assert client.get("/api/v1/exceptions").status_code == read
        assert client.get(f"/api/v1/exceptions/{ident}").status_code == read
        assert client.get(f"/api/v1/exceptions/{ident}/assignees").status_code == manage
        assert (
            client.post(
                f"/api/v1/exceptions/{ident}/assign",
                json={"assigned_user_id": str(user.id)},
                headers=headers,
            ).status_code
            == manage
        )
        assert (
            client.post(
                f"/api/v1/exceptions/{ident}/transition",
                json={"status": "investigating"},
                headers=headers,
            ).status_code
            == manage
        )


def test_viewer_membership_can_read_but_not_manage(
    db: Session,
    api_app: FastAPI,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    ident = new_exception(db, workspace, clock)
    user = make_user(("operator",))  # global manage permission, read-only customer membership
    add_member(migrator_engine, customer_of(db, workspace), user.id, role="viewer")
    with TestClient(api_app, raise_server_exceptions=False) as client:
        login(client, user.email)
        assert client.get(f"/api/v1/exceptions/{ident}").status_code == 200
        assert client.get(f"/api/v1/exceptions/{ident}/assignees").status_code == 404


def test_queue_api_contract_and_bounds(
    db: Session, api_app: FastAPI, workspace: Workspace, clock: FakeClock
) -> None:
    ident = new_exception(db, workspace, clock)
    with TestClient(api_app, raise_server_exceptions=False) as client:
        token = str(login(client, workspace.email)["csrf_token"])
        body = client.get("/api/v1/exceptions?limit=1").json()
        assert set(body) == {"items", "total", "limit", "offset"}
        assert body["items"][0]["id"] == str(ident)
        assert body["items"][0]["customer_id"] == str(customer_of(db, workspace))
        for query in ("limit=0", "limit=101", "offset=-1", "created_on=not-a-date"):
            assert client.get(f"/api/v1/exceptions?{query}").status_code == 422
        assert client.get("/api/v1/exceptions?limit=100&offset=0").status_code == 200
        assert client.get("/api/v1/exceptions?created_on=2026-11-18").json()["total"] == 1
        assert client.get("/api/v1/exceptions?created_on=2026-11-19").json()["total"] == 0
        long_reason = {
            "status": "awaiting_information",
            "reason": "x" * (exceptions.REASON_MAX + 1),
        }
        assert (
            client.post(
                f"/api/v1/exceptions/{ident}/transition",
                json=long_reason,
                headers={"X-CSRF-Token": token},
            ).status_code
            == 422
        )


# ------------------------------------------------------------------ concurrency (real PostgreSQL)


def test_a_second_transition_waits_for_the_row_lock_and_validates_fresh_state(
    db: Session, runtime_engine: Engine, workspace: Workspace, clock: FakeClock
) -> None:
    """Deterministic proof of blocking: hold the lock, observe the waiter, then commit."""
    ident = new_exception(db, workspace, clock)
    holder = Session(runtime_engine)
    outcome: dict[str, object] = {}

    def waiter() -> None:
        with Session(runtime_engine) as session:
            try:
                exceptions.transition(
                    session, workspace.actor, ident, "investigating", "", AuditWriter(clock), None
                )
                outcome["result"] = "ok"
            except AppError as exc:
                outcome["result"] = exc.code

    try:
        exceptions._scoped(holder, workspace.actor, ident, manage=True, lock=True)
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(waiter)
            deadline = time.monotonic() + 2
            blocked = 0
            while time.monotonic() < deadline and not blocked:
                # An ungranted transactionid lock means a session is queued behind another
                # transaction. pg_locks is readable by every role, unlike other sessions' queries.
                blocked = int(
                    holder.scalar(
                        text(
                            "SELECT count(*) FROM pg_locks "
                            "WHERE NOT granted AND locktype='transactionid'"
                        )
                    )
                    or 0
                )
                time.sleep(0.05)
            assert blocked == 1, "the second transition did not wait for the row lock"
            assert not future.done()
            holder.execute(
                text("UPDATE ledgerops.exceptions SET status='investigating' WHERE id=:id"),
                {"id": ident},
            )
            holder.commit()
            future.result(timeout=5)
    finally:
        holder.close()
    # investigating -> investigating is invalid, so the waiter saw the committed status.
    assert outcome["result"] == "invalid_exception_transition"


def test_concurrent_identical_transitions_apply_exactly_once(
    db: Session, runtime_engine: Engine, workspace: Workspace, clock: FakeClock
) -> None:
    ident = new_exception(db, workspace, clock)
    audit = AuditWriter(clock)

    def start(session: Session) -> object:
        return exceptions.transition(
            session, workspace.actor, ident, "investigating", "", audit, None
        )

    outcomes = race(runtime_engine, [start, start])
    assert sorted(str(o) for o in outcomes) == ["invalid_exception_transition", "ok"]
    events = exceptions.detail(db, workspace.actor, ident)["events"]
    assert [e["kind"] for e in events] == ["created", "status_changed"]
    audits = db.scalar(
        text(
            "SELECT count(*) FROM ledgerops.audit_events "
            "WHERE target_id=:id AND action='exception.investigating'"
        ),
        {"id": str(ident)},
    )
    assert audits == 1


def test_concurrent_conflicting_transitions_leave_one_consistent_outcome(
    db: Session, runtime_engine: Engine, workspace: Workspace, clock: FakeClock
) -> None:
    ident = new_exception(db, workspace, clock)
    audit = AuditWriter(clock)
    exceptions.transition(db, workspace.actor, ident, "investigating", "", audit, None)

    def resolve(session: Session) -> object:
        return exceptions.transition(
            session, workspace.actor, ident, "resolved", "Done", audit, None
        )

    def await_info(session: Session) -> object:
        return exceptions.transition(
            session, workspace.actor, ident, "awaiting_information", "Need evidence", audit, None
        )

    outcomes = race(runtime_engine, [resolve, await_info])
    assert sorted(str(o) for o in outcomes) == ["invalid_exception_transition", "ok"]
    record = exceptions.detail(db, workspace.actor, ident)
    winner = record["events"][-1]
    assert record["status"] == winner["next_status"]
    assert len(record["events"]) == 3  # created, investigating, and exactly one competing change
    assert (record["resolution_summary"] is not None) == (record["status"] == "resolved")


def test_concurrent_assignments_form_a_consistent_history(
    db: Session,
    runtime_engine: Engine,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    customer = customer_of(db, workspace)
    first, second = make_user(("operator",)), make_user(("operator",))
    add_member(migrator_engine, customer, first.id)
    add_member(migrator_engine, customer, second.id)
    ident = new_exception(db, workspace, clock)
    audit = AuditWriter(clock)

    def assign_to(target: UUID) -> Callable[[Session], object]:
        return lambda session: exceptions.assign(
            session, workspace.actor, ident, target, audit, None
        )

    assert race(runtime_engine, [assign_to(first.id), assign_to(second.id)]) == ["ok", "ok"]
    record = exceptions.detail(db, workspace.actor, ident)
    kinds = [e["kind"] for e in record["events"]]
    assert kinds == ["created", "assigned", "reassigned"]  # never two "assigned" from a stale read
    last = record["events"][-1]["metadata"]
    assert record["assigned_user_id"] == UUID(last["assigned_user_id"])
    assert last["previous_assigned_user_id"] == record["events"][1]["metadata"]["assigned_user_id"]


def test_exception_workflow_over_the_api(
    db: Session,
    api_app: FastAPI,
    migrator_engine: Engine,
    make_user: UserFactory,
    workspace: Workspace,
    clock: FakeClock,
) -> None:
    """The exact calls the Exceptions Workspace makes, in order, with CSRF."""
    colleague = make_user(("operator",))
    add_member(migrator_engine, customer_of(db, workspace), colleague.id)
    ident = new_exception(db, workspace, clock)
    base = f"/api/v1/exceptions/{ident}"
    with TestClient(api_app, raise_server_exceptions=False) as client:
        headers = {"X-CSRF-Token": str(login(client, workspace.email)["csrf_token"])}

        people = client.get(f"{base}/assignees").json()
        assert {p["id"] for p in people} == {str(workspace.actor), str(colleague.id)}
        assigned = client.post(
            f"{base}/assign", json={"assigned_user_id": str(colleague.id)}, headers=headers
        )
        assert assigned.status_code == 200
        assert assigned.json()["assigned_user_id"] == str(colleague.id)
        bad = client.post(
            f"{base}/assign", json={"assigned_user_id": str(uuid4())}, headers=headers
        )
        assert (bad.status_code, "invalid_assignee" in bad.text) == (422, True)

        started = client.post(
            f"{base}/transition", json={"status": "investigating"}, headers=headers
        )
        assert started.json()["status"] == "investigating"
        again = client.post(f"{base}/transition", json={"status": "investigating"}, headers=headers)
        assert (again.status_code, "invalid_exception_transition" in again.text) == (409, True)
        no_reason = client.post(
            f"{base}/transition", json={"status": "awaiting_information"}, headers=headers
        )
        assert (no_reason.status_code, "reason_required" in no_reason.text) == (422, True)

        noted = client.post(
            f"{base}/notes", json={"body": "Rail evidence attached."}, headers=headers
        )
        assert noted.status_code == 200
        resolved = client.post(
            f"{base}/resolve", json={"body": "Simulated failure."}, headers=headers
        )
        assert resolved.json()["resolution_summary"] == "Simulated failure."
        closed = client.post(
            f"{base}/close", json={"status": "closed", "reason": "Complete."}, headers=headers
        )
        assert closed.json()["status"] == "closed"
        history = client.get(base).json()["events"]
        assert [e["kind"] for e in history] == [
            "created",
            "assigned",
            "status_changed",
            "note_added",
            "resolved",
            "status_changed",
        ]
        assert (
            client.post(
                f"{base}/assign", json={"assigned_user_id": str(workspace.actor)}, headers=headers
            ).status_code
            == 409
        )
        assert client.get(f"/api/v1/exceptions/{uuid4()}").status_code == 404
        # Mutations without the CSRF token are refused before reaching the service.
        assert client.post(f"{base}/notes", json={"body": "x"}).status_code == 403
