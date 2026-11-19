# ADR 0010. Internal INR financial core

PR 6a implements simulated internal movements. External payment rails, FX, holds and reversals remain outside this milestone.

## Ownership and permissions

Users and customers have a many-to-many relationship. Every account belongs to one customer. Admin and operator can read accounts and postings and create transfers. Auditor can read accounts and postings. Approver and viewer have no financial permissions. Every financial query also requires active membership, including for admins. A source membership must be owner, administrator or member. Destination access and history require active membership. An inaccessible account returns 404. Transfer history requires access to both ends.

## Accounting

Chart code 1000 represents simulated cash (debit-normal asset). Code 2000 represents customer deposits (credit-normal liability). Each deposit has a unique posting account. One currency per account and journal is enforced through composite foreign keys. Processing supports INR, decimal strings over HTTP, Python Decimal and PostgreSQL NUMERIC(18,2).

The posting service inserts a draft header and one-sided lines, then finalizes the journal. A deferred constraint validates the final state, minimum line count and equality of debit and credit totals. The finalization trigger applies net changes to projections inside the same transaction. Available balance equals ledger balance until holds exist. The application role can lock projections through a constrained marker column. It has no grant to change either balance amount. The database owner can administratively change triggers or grants.

## Transfers and retries

The service locks both projection rows in ledger UUID order, reads fresh balances and writes a transfer, journal and two audit events in one transaction. An outgoing deposit debit reduces the source balance. The destination receives a deposit credit. An actor, operation and idempotency key uniquely identify a committed request. Its SHA-256 fingerprint includes both accounts, canonical two-decimal amount, currency and trimmed description. Failed requests roll back their key reservation. The request timeout bounds lock waits. Retry a busy or ambiguous result with the original key and unchanged body.

Use the existing cookie session and CSRF token. GET /api/v1/accounts lists authorized accounts. Append an account UUID for details, or append /ledger to the account URL for postings. GET /api/v1/transfers returns scoped history. Listings of postings and transfers accept limit (1–100) and offset.

POST /api/v1/transfers requires X-CSRF-Token and Idempotency-Key. Send source_id, destination_id, amount (for example "12.50"), currency ("INR") and optional description. A new post returns 201. Replay returns 200 and the same transfer and journal reference. Reusing the key with a different valid payload returns 409.

## Local synthetic provisioning

From the repository root, configure the existing Compose environment and start the stack. Use an existing local admin or operator UUID for the explicit provisioning command.

```powershell
docker compose up --build -d --wait
docker compose run --rm --no-deps migrate python -m app.modules.finance.provision --user-id <existing-user-uuid>
```

The command uses the migration identity, creates one synthetic organization with two zero-balance accounts, and posts INR 1,000 of opening funding to the first deposit against simulated cash. Repeating it for the same user is a no-op. Startup never invokes it. Provisioning and opening funding carry the system:synthetic-provision principal.

Migration 0003 refuses downgrade when customer or ledger data exists. Use an empty, disposable database for upgrade/downgrade tests.
