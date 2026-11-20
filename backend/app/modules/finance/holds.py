"""Reservation commands share the deposit projection lock with internal transfers."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.modules.audit import AuditWriter

SELECT_HOLDS = """SELECT id,account_id,currency,original_amount::text,remaining::text,status,
    reason,business_reference,creator,created_at,updated_at,expires_at
    FROM ledgerops.account_holds"""
INSERT = text("""
    INSERT INTO ledgerops.hold_events(id,hold_id,account_id,kind,currency,amount,remaining,
        occurred_at,actor,command,key,digest,reason,business_reference,expires_at,journal_id)
    VALUES (:id,:hold,:account,:kind,'INR',:amount,:remaining,:now,:actor,:command,:key,
        :digest,:reason,:reference,:expires,:journal)
    ON CONFLICT(actor,command,key) DO NOTHING RETURNING id
""")


def append_event(
    db: Session,
    audit: AuditWriter,
    request_id: str | None,
    *,
    hold: UUID,
    account: UUID,
    kind: str,
    amount: Decimal,
    remaining: Decimal,
    now: datetime,
    actor: UUID | None,
    command: str,
    key: str | None = None,
    digest: str | None = None,
    reason: str | None = None,
    reference: str | None = None,
    expires: datetime | None = None,
    journal: UUID | None = None,
) -> bool:
    inserted = db.scalar(
        INSERT,
        {
            "id": uuid4(),
            "hold": hold,
            "account": account,
            "kind": kind,
            "amount": amount,
            "remaining": remaining,
            "now": now,
            "actor": actor,
            "command": command,
            "key": key,
            "digest": digest,
            "reason": reason,
            "reference": reference,
            "expires": expires,
            "journal": journal,
        },
    )
    if inserted is None:
        return False
    audit.record(
        db,
        principal=Principal.user(actor) if actor else Principal.system("hold-expiry"),
        action=f"account_hold.{kind}",
        target_type="account_hold",
        target_id=str(hold),
        request_id=request_id,
        metadata={"account_id": str(account)},
    )
    return True


def expire_locked(
    db: Session, account: UUID, now: datetime, audit: AuditWriter, request_id: str | None
) -> int:
    due = db.execute(
        text("""
        SELECT id,remaining FROM ledgerops.account_holds WHERE account_id=:account
        AND remaining>0 AND expires_at<=:now ORDER BY expires_at,id
    """),
        {"account": account, "now": now},
    ).all()
    for hold, remaining in due:
        append_event(
            db,
            audit,
            request_id,
            hold=hold,
            account=account,
            kind="expired",
            amount=remaining,
            remaining=Decimal(0),
            now=now,
            actor=None,
            command="expire",
        )

    approvals = db.execute(
        text("""SELECT id,hold_id,amount,maker,payload_hash
        FROM ledgerops.approval_requests WHERE source_id=:account AND status='pending_approval'
        AND expires_at<=:now ORDER BY id FOR UPDATE"""),
        {"account": account, "now": now},
    ).all()
    for row in approvals:
        if not append_event(
            db,
            audit,
            request_id,
            hold=row.hold_id,
            account=account,
            kind="released",
            amount=row.amount,
            remaining=Decimal(0),
            now=now,
            actor=row.maker,
            command="release",
            key=f"approval/{row.id}",
            digest=row.payload_hash,
            reason="Approval expired",
        ):
            raise AppError(409, "release_conflict", "Reservation release conflicted.")
        values = {"id": row.id, "event": uuid4(), "now": now, "request": request_id}
        db.execute(
            text("""UPDATE ledgerops.approval_requests SET status='expired',
            completed_at=:now WHERE id=:id"""),
            values,
        )
        db.execute(
            text("""INSERT INTO ledgerops.approval_events
            VALUES(:event,:id,'expired',NULL,:now,:request)"""),
            values,
        )
        audit.record(
            db,
            principal=Principal.system("approval-expiry"),
            action="approval.expired",
            target_type="approval_request",
            target_id=str(row.id),
            request_id=request_id,
        )
    return len(due) + len(approvals)


def refresh(
    db: Session, actor: UUID, account: UUID | None, audit: AuditWriter, request_id: str | None
) -> tuple[dict[UUID, str], datetime, int]:
    # Both queries order by financial account id, including when a caller owns many accounts.
    rows = db.execute(
        text("""
        SELECT a.id,m.role FROM ledgerops.accounts a
        JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
        JOIN ledgerops.account_balances b USING(ledger_id)
        WHERE m.active AND m.user_id=:actor AND (CAST(:account AS uuid) IS NULL OR a.id=:account)
        ORDER BY a.id FOR UPDATE OF b
    """),
        {"account": account, "actor": actor},
    ).all()
    if account and not rows:
        raise AppError(404, "account_not_found", "Account unavailable.")
    now = audit.clock.now()
    expired = sum(expire_locked(db, account_id, now, audit, request_id) for account_id, _ in rows)
    return {row.id: row.role for row in rows}, now, expired


def locate(db: Session, actor: UUID, hold: UUID) -> UUID:
    result = db.scalar(
        text("""
        SELECT h.account_id FROM ledgerops.account_holds h
        JOIN ledgerops.accounts a ON a.id=h.account_id
        JOIN ledgerops.customer_members m ON m.customer_id=a.customer_id
        WHERE h.id=:hold AND m.active AND m.user_id=:actor
    """),
        {"actor": actor, "hold": hold},
    )
    if not isinstance(result, UUID):
        raise AppError(404, "hold_not_found", "Hold unavailable.")
    return result


def detail(db: Session, hold: UUID) -> dict[str, Any]:
    return dict(db.execute(text(SELECT_HOLDS + " WHERE id=:hold"), {"hold": hold}).mappings().one())


def page(db: Session, account: UUID, limit: int, offset: int) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in db.execute(
            text(
                SELECT_HOLDS
                + """ WHERE account_id=:account
        ORDER BY created_at DESC,id LIMIT :limit OFFSET :offset
    """
            ),
            {"account": account, "limit": limit, "offset": offset},
        ).mappings()
    ]


def receipt(db: Session, actor: UUID, command: str, key: str, digest: str) -> dict[str, Any] | None:
    row = (
        db.execute(
            text("""
        SELECT hold_id,kind,remaining::text,currency,digest,id AS event_id
        FROM ledgerops.hold_events WHERE actor=:actor AND command=:command AND key=:key
    """),
            {"actor": actor, "command": command, "key": key},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    result = dict(row)
    if result.pop("digest") != digest:
        raise AppError(409, "idempotency_conflict", "This key belongs to a different command.")
    return result


def require_unassigned(db: Session, hold: UUID) -> None:
    if db.scalar(
        text("""SELECT EXISTS(SELECT FROM ledgerops.approval_requests
        WHERE hold_id=:hold AND status='pending_approval')"""),
        {"hold": hold},
    ):
        raise AppError(409, "hold_reserved", "Reservation belongs to a pending approval.")


def may_release(role: str, actor: UUID, creator: UUID) -> bool:
    return role in {"administrator", "owner"} or (role == "member" and actor == creator)


def change(
    db: Session,
    actor: UUID,
    account: UUID,
    hold: UUID | None,
    amount: Decimal | None,
    key: str,
    audit: AuditWriter,
    request_id: str | None,
    *,
    reason: str | None = None,
    reference: str | None = None,
    expires: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    if amount is not None and (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or amount <= 0
        or amount >= Decimal("1e16")
        or amount != amount.quantize(Decimal("0.01"))
    ):
        raise AppError(
            422, "invalid_amount", "Use a positive INR amount with at most two decimals."
        )
    if expires is not None and expires.utcoffset() is None:
        raise AppError(422, "invalid_expiry", "Expiration requires a timezone.")
    roles, now, expired = refresh(db, actor, account, audit, request_id)
    # Expiry observed under lock survives a business rejection. Infrastructure failures
    # still roll back both expiry and the command, including their audit records.
    try:
        with db.begin_nested():
            return _change_locked(
                db,
                actor,
                account,
                hold,
                amount,
                key,
                audit,
                request_id,
                reason,
                reference,
                expires,
                roles[account],
                now,
            )
    except AppError:
        if expired:
            db.commit()
        raise


def _change_locked(
    db: Session,
    actor: UUID,
    account: UUID,
    hold: UUID | None,
    amount: Decimal | None,
    key: str,
    audit: AuditWriter,
    request_id: str | None,
    reason: str | None,
    reference: str | None,
    expires: datetime | None,
    role: str,
    now: datetime,
) -> tuple[dict[str, Any], bool]:
    previous = detail(db, hold) if hold else None
    if role == "viewer" or (previous and not may_release(role, actor, previous["creator"])):
        raise AppError(403, "forbidden", "Membership does not permit this command.")
    state = db.execute(
        text("""
        SELECT a.status,b.available_balance FROM ledgerops.accounts a
        JOIN ledgerops.account_balances b USING(ledger_id) WHERE a.id=:id
    """),
        {"id": account},
    ).one()
    if state.status != "active":
        raise AppError(409, "account_unavailable", "Account must be active.")
    command = "release" if hold else "create"
    if expires:
        expires = expires.astimezone(UTC)
    payload = [
        str(account),
        str(hold),
        format(amount, ".2f") if amount is not None else None,
        reason,
        reference,
        expires.isoformat() if expires else None,
        "INR",
    ]
    digest = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    replay = receipt(db, actor, command, key, digest)
    if replay is not None:
        return replay, False
    if previous is None:
        if amount is None or amount <= 0 or not reason or not reason.strip():
            raise AppError(422, "invalid_hold", "A positive amount and reason are required.")
        if expires and expires <= now:
            raise AppError(422, "invalid_expiry", "Expiration must be in the future.")
        if amount > state.available_balance:
            raise AppError(409, "insufficient_funds", "Available funds are insufficient.")
        kind = "created"
        remaining = amount
    else:
        require_unassigned(db, previous["id"])
        available = Decimal(previous["remaining"])
        amount = available if amount is None else amount
        if available <= 0 or amount <= 0 or amount > available:
            raise AppError(409, "invalid_release", "Hold has insufficient remaining funds.")
        remaining = available - amount
        kind = "partially_released" if remaining else "released"
    created = append_event(
        db,
        audit,
        request_id,
        hold=hold or uuid4(),
        account=account,
        kind=kind,
        amount=amount,
        remaining=remaining,
        now=now,
        actor=actor,
        command=command,
        key=key,
        digest=digest,
        reason=reason,
        reference=reference,
        expires=expires,
    )
    result = receipt(db, actor, command, key, digest)
    if result is None:
        raise RuntimeError("Hold event receipt missing")
    return result, created
