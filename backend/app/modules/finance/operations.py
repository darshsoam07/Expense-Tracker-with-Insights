"""Customer-scoped operational workflows for the simulated INR rail."""

import hashlib
import re
from collections import Counter
from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.modules.audit import AuditWriter
from app.modules.finance import exceptions
from app.modules.finance.settlement import settle
from app.modules.finance.statements import parse_statement

BATCH = """SELECT b.*,count(c.payment_id) AS item_count,sum(p.amount)::text AS total,
 count(s.payment_id) AS settled_count,count(c.failure) AS failed_count
 FROM ledgerops.settlement_batches b JOIN ledgerops.settlement_candidates c ON c.batch_id=b.id
 JOIN ledgerops.payment_instructions p ON p.id=c.payment_id
 LEFT JOIN ledgerops.settlement_items s ON s.payment_id=p.id"""
IMPORT = """SELECT b.*,'SIMULATED_INR' AS provider,'INR' AS currency,'imported' AS status,
 (SELECT count(*) FROM ledgerops.statement_lines WHERE import_id=b.id) AS row_count
 FROM ledgerops.statement_imports b"""
RUN = """SELECT b.*,i.customer_id,CASE WHEN completed_at IS NULL THEN 'processing' ELSE
        'completed' END AS status,
 (SELECT count(*) FROM ledgerops.reconciliation_results WHERE run_id=b.id AND
        classification='exact_match') AS matched_count,
 (SELECT count(*) FROM ledgerops.reconciliation_results WHERE run_id=b.id AND
        classification<>'exact_match') AS exception_count
 FROM ledgerops.reconciliation_runs b JOIN ledgerops.statement_imports i ON i.id=b.import_id"""
QUERIES = {"batches": BATCH, "statements": IMPORT, "reconciliation-runs": RUN}


def records(
    db: Session, kind: str, actor: UUID, ident: UUID | None = None, limit: int = 25, offset: int = 0
) -> list[dict[str, Any]]:
    customer = "i.customer_id" if kind == "reconciliation-runs" else "b.customer_id"
    query = (
        QUERIES[kind] + f" JOIN ledgerops.customer_members m ON m.customer_id={customer}"
        " WHERE m.user_id=:actor AND m.active"
    )
    if ident:
        query += " AND b.id=:id"
    if kind == "batches":
        query += " GROUP BY b.id"
    query += " ORDER BY b.created_at DESC,b.id LIMIT :limit OFFSET :offset"
    return [
        dict(r)
        for r in db.execute(
            text(query), {"actor": actor, "id": ident, "limit": limit, "offset": offset}
        ).mappings()
    ]


def detail(db: Session, kind: str, actor: UUID, ident: UUID) -> dict[str, Any]:
    found = records(db, kind, actor, ident)
    if not found:
        raise AppError(404, "unavailable", "Record unavailable.")
    return found[0]


def authorize(db: Session, customer: UUID, actor: UUID) -> None:
    if not db.scalar(
        text("""SELECT 1 FROM ledgerops.customer_members WHERE customer_id=:c
        AND user_id=:a AND active AND role<>'viewer'"""),
        {"c": customer, "a": actor},
    ):
        raise AppError(404, "unavailable", "Workspace unavailable.")


def log(
    db: Session, audit: AuditWriter, actor: UUID, action: str, ident: UUID, request: str | None
) -> None:
    audit.record(
        db,
        principal=Principal.user(actor),
        action=action,
        target_type=action.split(".")[0],
        target_id=str(ident),
        request_id=request,
    )


def batch(
    db: Session, customer: UUID, actor: UUID, audit: AuditWriter, request: str | None
) -> dict[str, Any]:
    authorize(db, customer, actor)
    ident = db.execute(
        text("""INSERT INTO ledgerops.settlement_batches(customer_id,actor_id)
        VALUES (:c,:a) RETURNING id"""),
        {"c": customer, "a": actor},
    ).scalar_one()
    added = db.execute(
        text("""INSERT INTO ledgerops.settlement_candidates(payment_id,batch_id,customer_id)
      SELECT p.id,:id,p.customer_id FROM ledgerops.payment_instructions p
      JOIN ledgerops.account_holds h ON h.id=p.hold_id WHERE p.customer_id=:c AND
        p.status='accepted'
      AND h.remaining=p.amount AND NOT EXISTS(SELECT FROM ledgerops.settlement_items
        WHERE payment_id=p.id)
      AND NOT EXISTS(SELECT FROM ledgerops.settlement_candidates WHERE payment_id=p.id)
      ORDER BY p.id LIMIT 100 ON CONFLICT DO NOTHING RETURNING payment_id"""),
        {"id": ident, "c": customer},
    ).all()
    if not added:
        db.rollback()
        raise AppError(409, "empty_batch", "No eligible accepted payments.")
    log(db, audit, actor, "batch.created", ident, request)
    db.commit()
    return detail(db, "batches", actor, ident)


def process(
    db: Session, ident: UUID, actor: UUID, audit: AuditWriter, request: str | None
) -> dict[str, Any]:
    b = detail(db, "batches", actor, ident)
    authorize(db, b["customer_id"], actor)
    if b["status"] == "settled":
        return b
    ids = (
        db.execute(
            text("""SELECT payment_id FROM ledgerops.settlement_candidates
        WHERE batch_id=:id ORDER BY payment_id"""),
            {"id": ident},
        )
        .scalars()
        .all()
    )
    changed = db.scalar(
        text("""UPDATE ledgerops.settlement_batches SET status='processing'
        WHERE id=:id AND status NOT IN ('processing','settled') RETURNING id"""),
        {"id": ident},
    )
    if changed:
        log(db, audit, actor, "batch.processing", ident, request)
    db.commit()
    for payment in ids:
        authorize(db, b["customer_id"], actor)
        failure = None
        try:
            settle(db, payment, actor, audit, request)
            db.execute(
                text("""UPDATE ledgerops.settlement_items SET batch_id=:id
                 WHERE payment_id=:payment AND batch_id IS NULL"""),
                {"id": ident, "payment": payment},
            )
        except AppError as exc:
            db.rollback()
            failure = exc.code
            log(db, audit, actor, "settlement.failed", payment, request)
            exceptions.generate(
                db,
                b["customer_id"],
                "settlement",
                payment,
                "settlement_failed",
                actor,
                audit.clock.now(),
            )
        db.execute(
            text("""UPDATE ledgerops.settlement_candidates SET failure=CASE
           WHEN EXISTS(SELECT FROM ledgerops.settlement_items WHERE payment_id=:payment)
           THEN NULL ELSE :failure END
           WHERE payment_id=:payment"""),
            {"payment": payment, "failure": failure},
        )
        db.commit()
    b = detail(db, "batches", actor, ident)
    status = (
        "settled"
        if b["item_count"] == b["settled_count"]
        else ("partially_settled" if b["settled_count"] else "failed")
    )
    if db.scalar(
        text("""UPDATE ledgerops.settlement_batches SET status=:status,processed_at=now()
         WHERE id=:id AND status<>'settled' AND status<>:status RETURNING id"""),
        {"id": ident, "status": status},
    ):
        log(db, audit, actor, "batch." + status, ident, request)
    db.commit()
    return detail(db, "batches", actor, ident)


def ingest(
    db: Session,
    customer: UUID,
    actor: UUID,
    filename: str,
    content: bytes,
    audit: AuditWriter,
    request: str | None,
) -> dict[str, Any]:
    authorize(db, customer, actor)
    if not re.fullmatch(r"[\w.-]{1,110}\.csv", filename, re.I):
        raise AppError(422, "invalid_filename", "Use a CSV filename.")
    lines = parse_statement(content)
    args = {
        "c": customer,
        "a": actor,
        "name": filename,
        "digest": hashlib.sha256(content).hexdigest(),
    }
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"statement/{customer}"},
    )
    ident = db.scalar(
        text("""INSERT INTO ledgerops.statement_imports(customer_id,actor_id,filename,checksum)
        VALUES (:c,:a,:name,:digest) ON CONFLICT DO NOTHING RETURNING id"""),
        args,
    )
    replay = ident is None
    if replay:
        ident = db.execute(
            text(
                """SELECT id FROM ledgerops.statement_imports WHERE customer_id=:c AND
        checksum=:digest"""
            ),
            args,
        ).scalar_one()
    else:
        counts = Counter(line.external_reference for line in lines)
        seen = set()
        for line in lines:
            if line.external_reference in seen:
                continue
            seen.add(line.external_reference)
            db.execute(
                text("""INSERT INTO
        ledgerops.statement_lines(import_id,external_reference,provider_reference,
            amount,currency,direction,transaction_date,settlement_date,status,duplicate)
            VALUES (:id,:external_reference,:provider_reference,:amount,:currency,
        :direction,:transaction_date,
            :settlement_date,:status,:duplicate OR EXISTS(SELECT FROM
        ledgerops.statement_lines l JOIN ledgerops.statement_imports i
            ON i.id=l.import_id WHERE i.customer_id=:c AND
        l.external_reference=:external_reference))
"""),
                {
                    **asdict(line),
                    "id": ident,
                    "c": customer,
                    "duplicate": counts[line.external_reference] > 1,
                },
            )
        log(db, audit, actor, "statement.imported", ident, request)
    db.commit()
    return {**detail(db, "statements", actor, ident), "replayed": replay}


def reconcile(
    db: Session, imp: UUID, actor: UUID, audit: AuditWriter, request: str | None
) -> dict[str, Any]:
    customer = detail(db, "statements", actor, imp)["customer_id"]
    authorize(db, customer, actor)
    run = db.execute(
        text("""INSERT INTO ledgerops.reconciliation_runs(import_id,actor_id)
        VALUES (:id,:a) RETURNING id"""),
        {"id": imp, "a": actor},
    ).scalar_one()
    db.execute(
        text("""WITH lines AS (SELECT l.*,count(*) OVER(PARTITION BY provider_reference) AS refs
      FROM ledgerops.statement_lines l WHERE import_id=:imp), internal AS (
      SELECT p.id,p.provider_reference,p.currency,p.amount,s.journal_id,s.batch_id,
        s.settled_at,p.created_at
      FROM ledgerops.payment_instructions p LEFT JOIN ledgerops.settlement_items s ON
        s.payment_id=p.id
      WHERE p.customer_id=:c), compared AS (
      SELECT l.id AS line_id,p.id AS payment_id,CASE
        WHEN l.duplicate OR l.refs>1 THEN 'duplicate_external_reference'
        WHEN l.id IS NULL THEN 'missing_statement_record'
        WHEN p.journal_id IS NULL THEN 'missing_internal_record'
        WHEN l.amount<>p.amount THEN 'amount_mismatch'
        WHEN l.currency<>p.currency THEN 'currency_mismatch'
        WHEN l.direction<>'outbound' THEN 'direction_mismatch'
        WHEN l.status<>'settled' THEN 'status_mismatch'
        WHEN abs(l.settlement_date-(p.settled_at AT TIME ZONE 'UTC')::date)>1
          OR abs(l.transaction_date-(p.created_at AT TIME ZONE 'UTC')::date)>1 THEN
        'timing_difference'
        ELSE 'exact_match' END AS classification,
        jsonb_build_object('statement',to_jsonb(l),'internal',to_jsonb(p)) AS evidence
      FROM lines l FULL JOIN internal p USING(provider_reference)
      WHERE l.id IS NOT NULL OR (p.settled_at AT TIME ZONE 'UTC')::date BETWEEN
        (SELECT min(settlement_date) FROM lines) AND (SELECT max(settlement_date) FROM lines))
      INSERT INTO ledgerops.reconciliation_results(run_id,line_id,payment_id,
        classification,evidence)
      SELECT :run,line_id,payment_id,classification,evidence FROM compared"""),
        {"imp": imp, "c": customer, "run": run},
    )
    results = db.execute(
        text(
            """SELECT COALESCE(line_id,payment_id), classification
            FROM ledgerops.reconciliation_results WHERE run_id=:run
            AND classification = ANY(:kinds)"""
        ),
        {"run": run, "kinds": list(exceptions.RECONCILIATION_TYPES)},
    ).all()
    now = audit.clock.now()
    for result_id, classification in results:
        exceptions.generate(db, customer, "reconciliation", result_id, classification, actor, now)
    db.execute(
        text(
            "UPDATE ledgerops.reconciliation_runs SET completed_at=clock_timestamp() WHERE id=:id"
        ),
        {"id": run},
    )
    log(db, audit, actor, "reconciliation.completed", run, request)
    db.commit()
    return detail(db, "reconciliation-runs", actor, run)


def children(
    db: Session, kind: str, actor: UUID, ident: UUID, limit: int, offset: int
) -> list[dict[str, Any]]:
    detail(db, kind, actor, ident)
    queries = {
        "batches": """SELECT c.payment_id,c.customer_id,p.provider_reference,p.amount::text,
          h.status AS hold_status,s.journal_id,c.failure,CASE WHEN s.journal_id IS NOT NULL
          THEN 'settled' WHEN c.failure IS NOT NULL THEN 'failed' ELSE 'pending' END AS status
          FROM ledgerops.settlement_candidates c JOIN ledgerops.payment_instructions p ON
        p.id=c.payment_id
          JOIN ledgerops.account_holds h ON h.id=p.hold_id LEFT JOIN ledgerops.settlement_items s
          ON s.payment_id=p.id WHERE c.batch_id=:id ORDER BY c.payment_id""",
        "statements": """SELECT id,provider_reference,external_reference,amount::text,
        currency,direction,
          transaction_date,settlement_date,status,duplicate FROM ledgerops.statement_lines
          WHERE import_id=:id ORDER BY external_reference""",
        "reconciliation-runs": """SELECT id,payment_id,line_id,classification,evidence
          FROM ledgerops.reconciliation_results WHERE run_id=:id
          ORDER BY (classification='exact_match'),id""",
    }
    return [
        dict(r)
        for r in db.execute(
            text(queries[kind] + " LIMIT :limit OFFSET :offset"),
            {"id": ident, "limit": limit, "offset": offset},
        ).mappings()
    ]
