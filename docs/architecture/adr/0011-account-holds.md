# ADR 0011. Account reservations and available balance

## Decision

Each INR deposit has one balance projection. PostgreSQL derives available balance as ledger balance minus held amount. The database requires held amount to stay between zero and ledger balance. Migration 0004 initializes existing accounts with zero held funds. Ordinary journal posting continues to update the ledger projection. Reserving, releasing and expiring funds leave the ledger unchanged.

The runtime identity can append lifecycle events and read hold state. A database trigger applies each event to its hold and the deposit projection. The runtime has no write grant on hold state or monetary projection columns. Events reject update, delete and truncate. Administrators with schema ownership can change the database controls.

## Lifecycle and concurrency

Creation reserves a positive decimal amount. Partial release reduces the remaining amount. Full release and expiry clear it. A terminal hold cannot transition again. Each lifecycle event records the amount changed, the resulting remainder, timestamp and actor. Expiry uses the named system:hold-expiry audit principal. The event, projection change and audit record commit in the same transaction.

Hold commands and internal transfers take the existing projection row locks in financial account UUID order. The service samples the injected UTC clock after locking. Account list, detail, hold reads and financial commands expire due reservations synchronously under those locks. Frozen and closed accounts retain readable history and can expire. New reservations, manual releases and transfers require active accounts. Idle accounts can retain an unprocessed expiry until the next relevant access. The UI displays the last server response.

A transfer may supply hold_id to consume the entire remaining reservation on its source account. The caller needs transfer and release authority. The event links to the journal of a matching transfer created in the same database transaction. A deferred database check verifies a posted debit on the deposit. Capture, posting, projections and audit roll back together. Ordinary transfers use available funds. There is no standalone capture operation.

## Access

| Platform role | Read | Create | Release |
|---|---|---|---|
| Admin or operator | Yes | Yes | Yes |
| Auditor | Yes | No | No |
| Approver or viewer | No | No | No |

Active customer membership is mandatory for every role. A viewer membership can read when platform permissions allow. A member can create and release their own holds. An owner or customer administrator may release any hold on that customer's accounts. Other customers' account and hold IDs return 404.

## HTTP contract

Use the same-origin API, session cookie and CSRF header. Amounts are INR decimal strings with up to two fractional digits. Mutations also require Idempotency-Key. Successful commands return a receipt containing event_id, hold_id, kind, currency and remaining. The database uniquely scopes a key by actor and operation. Replay returns the original receipt even after later releases. A different fingerprint returns 409. Rejected commands do not consume a key.

| Operation | Request |
|---|---|
| Create | POST /api/v1/accounts/{id}/holds with amount, currency, reason, optional business_reference and optional timezone-aware expires_at |
| List | GET /api/v1/accounts/{id}/holds with limit and offset |
| Inspect | GET /api/v1/holds/{id} with limit and offset for lifecycle events |
| Release | POST /api/v1/holds/{id}/release with currency and optional amount. Omitting amount releases the remainder. |
| Consume | POST /api/v1/transfers with the existing transfer fields and optional hold_id |

A new reservation returns 201, a replay returns 200, and release returns 200. Insufficient funds, an unusable account or an invalid transition returns 409. Account responses include ledger_balance, held_amount and available_balance.

## Local verification

Run the existing Compose stack and provision a synthetic operator and two accounts using [ADR 0010](0010-internal-financial-core.md). In the console, open the funded account, reserve INR 100.00, inspect its history and partially release INR 25.00. Its available balance should increase by INR 25.00 while its ledger balance stays constant.

With TEST_DATABASE_URL and TEST_MIGRATION_DATABASE_URL pointing at a dedicated database migrated to head, run `pytest tests/integration/test_holds.py` from backend. Use a separate empty database for migration round trips. Downgrade refuses to remove hold history. PR 7b can build on these reservations.
