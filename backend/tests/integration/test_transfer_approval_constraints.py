"""Exercise policy revision matching and decision constraints as ledgerops_runtime."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import AuditWriter
from app.modules.finance import holds
from app.modules.finance.approval_policies import match_policy
from tests.helpers import FakeClock
from tests.integration.conftest import UserFactory, Workspace


def test_policy_revisions_and_decision_integrity(
    db: Session, workspace: Workspace, make_user: UserFactory, clock: FakeClock
) -> None:
    checker = make_user(("approver",))
    maker = workspace.actor
    customer = db.scalar(
        text("SELECT customer_id FROM ledgerops.accounts WHERE id=:id"), {"id": workspace.src}
    )
    now = clock.now()
    amount = Decimal("25.00")
    assert match_policy(db, customer, amount, "INR", now) is None
    policy = uuid4()
    revision = text("""INSERT INTO ledgerops.approval_policies
        VALUES(:id,:v,:customer,'Review','INR',25,25,2,NULL,:active,:now,:maker)""")
    params = {
        "id": policy,
        "v": 1,
        "customer": customer,
        "active": True,
        "now": now,
        "maker": maker,
    }
    db.execute(revision, params)
    selected = match_policy(db, customer, amount, "INR", now)
    assert selected
    assert selected.version == 1
    assert selected.required_count == 2
    assert match_policy(db, customer, Decimal("25.01"), "INR", now) is None
    with db.begin_nested() as nested:
        db.execute(revision, {**params, "id": uuid4()})
        with pytest.raises(AppError, match="Multiple transfer policies"):
            match_policy(db, customer, amount, "INR", now)
        nested.rollback()
    receipt, _ = holds.change(
        db,
        maker,
        workspace.src,
        None,
        amount,
        "approval",
        AuditWriter(clock),
        None,
        reason="Review",
    )
    request = uuid4()
    insert_request = text("""INSERT INTO ledgerops.approval_requests
        (id,subject_type,subject_id,maker,customer_id,policy_id,policy_version,source_id,
         destination_id,amount,currency,description,payload_hash,idempotency_key,hold_id,
         created_at,status)
        VALUES(:request,'internal_transfer',:subject,:maker,:customer,:id,:v,:src,:dst,
               25,'INR','Review',repeat('a',64),'request',:hold,:now,:status)""")
    values = dict(
        **params,
        request=request,
        subject=uuid4(),
        src=workspace.src,
        dst=workspace.dst,
        hold=receipt["hold_id"],
        status="pending_approval",
    )
    for changes in ({"v": 9}, {"customer": uuid4()}, {"status": "unknown"}):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(insert_request, {**values, **changes})
    db.execute(insert_request, values)
    db.execute(revision, {**params, "v": 2, "active": False, "now": now + timedelta(seconds=1)})
    assert match_policy(db, customer, amount, "INR", now) == selected
    assert match_policy(db, customer, amount, "INR", now + timedelta(seconds=1)) is None
    assert (
        db.scalar(
            text("SELECT policy_version FROM ledgerops.approval_requests WHERE id=:id"),
            {"id": request},
        )
        == 1
    )
    for sql in (
        "UPDATE ledgerops.approval_policies SET required_count=1 WHERE id=:id",
        "DELETE FROM ledgerops.approval_policies WHERE id=:id",
    ):
        with pytest.raises(ProgrammingError), db.begin_nested():
            db.execute(text(sql), params)
    decision = text("""INSERT INTO ledgerops.approval_decisions
        VALUES(:request,:maker,:actor,'approve','Reviewed',:now)""")
    for actor, claimed_maker in ((maker, maker), (maker, checker.id)):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(decision, {**values, "actor": actor, "maker": claimed_maker})
    db.execute(decision, {**values, "actor": checker.id})
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(decision, {**values, "actor": checker.id})
