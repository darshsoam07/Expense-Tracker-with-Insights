# ADR-0002: Double-entry ledger as source of truth, balance as a projection

- **Status:** Accepted (2026-11-15)

## Context

Customers need fast, correct balance checks, and concurrent transfers must never overspend. A balance that is edited directly can drift from the transaction history.

## Decision

- The **double-entry ledger** (journal entries and postings) is the financial source of truth.
- Each customer account has a **balance projection** (`account_balances`) that is updated **only by the ledger service, in the same database transaction as the postings it reflects**.
- **No independent or manual balance update may bypass the ledger service.** This will be enforced by an architecture test (import rules) and a test that attempts a bypass.
- Concurrency: the ledger service locks the affected account rows with `SELECT ... FOR UPDATE` **in ascending account-ID order** for every operation. A consistent order prevents deadlocks between opposite transfers.
- A **reconciliation routine** recomputes balances from postings and reports any difference from the projection.
- **The database enforces the invariants**, not only the application:
  - A deferred constraint trigger checks that, per journal entry, the sum of debits equals the sum of credits at commit.
  - Triggers reject `UPDATE` and `DELETE` on posted journal entries and postings.
  - Reversals are **new** journal entries that reference the original (`reverses_entry_id`, unique). The original is never modified.
  - Customer account balances carry `CHECK (ledger_balance >= 0)`.
- A posting is stored as one `amount NUMERIC(18,2) CHECK (amount > 0)` plus a `direction` of `debit` or `credit`.

## Consequences

- Overdraft checks are fast and lockable.
- There are two representations to keep consistent. Reconciliation and bypass tests are mandatory, not optional.
- Pending and failed states live on the `transfers` table. A journal entry is created already posted, in one transaction with its postings.
