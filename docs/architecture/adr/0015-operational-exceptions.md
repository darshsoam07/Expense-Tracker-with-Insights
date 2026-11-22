# ADR 0015 — Operational exceptions and investigations

LedgerOps records an operational exception only for an observed source event. The supported sources are a confirmed or ambiguous payment outcome, an expired approval, a failed settlement item, and every persisted reconciliation discrepancy: amount, currency, direction and status mismatches, missing internal or statement records, duplicate provider references, and timing differences. Successful payments and exact matches create no exception. `RECONCILIATION_TYPES` is the single list the reconcile step uses to select discrepancies, and a test fails if `reconcile()` ever emits a classification that has no exception rule.

The unique `(source_domain, source_reference, exception_type)` constraint is the idempotency boundary. Source transitions create the exception in their existing database transaction. Reconciliation uses its persisted statement-line or payment identity, so reruns do not create unlimited duplicate work items.

Exception records are customer-scoped work items rather than financial records. Operators can assign, investigate, note, resolve, and close them through append-only `exception_events`. Resolution never posts, reverses, releases, captures, or otherwise changes a journal, balance projection, or hold.

The lifecycle is `open → investigating|awaiting_information`, `investigating → awaiting_information|resolved`, `awaiting_information → investigating`, and `resolved → closed`. Resolution and closure need a meaningful operational reason. Closed records cannot reopen. Admin and operator roles manage only active customer memberships; approvers and auditors have read access; viewers have none.

## API

`GET /api/v1/exceptions` lists a bounded, customer-scoped queue. `GET /api/v1/exceptions/{id}` returns the record and immutable timeline. Assignment, transitions, notes, resolution and closure use the corresponding POST paths beneath the record. Each write requires an authenticated session, CSRF, `exceptions.manage`, and a writable customer membership, and writes its audit event in the same transaction.

## Concurrency and atomicity

Lifecycle transitions and assignment take `SELECT ... FOR UPDATE OF e` on the exception row before validating anything. A second request for the same exception waits, then re-reads the committed row, so it validates against current state instead of a stale status. The status update also carries `AND status = :previous` as a second guard. The status or assignee change, its `exception_events` row and its audit record are written in one transaction and commit together.

The runtime database role has no privilege to lock `customer_members` rows (and should not). Assignment therefore re-checks the assignee's active, non-viewer membership inside the same `UPDATE` statement. A membership revoked mid-request is refused with `invalid_assignee` rather than silently assigned.

Concurrency is proven against PostgreSQL, not mocked: a deterministic test holds the row lock and observes a second transition queued behind it through `pg_locks`, and race tests run simultaneous identical and conflicting transitions and assignments. Removing the lock makes those tests fail.

## History ordering

`exception_events.sequence` is a `bigint GENERATED ALWAYS AS IDENTITY` column, and history is read `ORDER BY sequence`. Event order never depends on timestamps, which can tie. The id is a random UUID and carries no order.

## Assignment

Assignee discovery lists only active, non-viewer members of the exception's own customer. Assigning someone else is `invalid_assignee` (422). Assigning the current assignee is a no-op that writes no history. A closed exception cannot be reassigned (`exception_closed`, 409). Assignment events store the assignee's display name as a snapshot so history stays accurate if the name later changes.

## Queue contract

`GET /api/v1/exceptions` returns `{items, total, limit, offset}`; each item includes `customer_id`. The page and the total come from one SQL statement, so they share a snapshot, and an offset past the end still returns the total. `limit` is 1 to 100 and `offset` is 0 or more. The `created_on` filter is a UTC calendar day, inclusive at the start and exclusive at the end, regardless of the database session timezone. Text limits: transition reasons 500 characters; notes and resolution summaries 2,000. The API, the service and the workspace UI enforce the same limits.

## Known limits

The dedupe key means a payment that is missing from the statement appears as one `missing_statement_record` exception even if it is missing from several imports. Exceptions never reopen once closed. Assignment is by explicit choice only. There is no automatic routing.

## Migration

Migration `0010` creates the history `sequence` column and its index. Its downgrade refuses to run while any exception exists. A development database that applied an earlier draft of `0010` must be recreated, or have its exceptions removed before downgrading.
