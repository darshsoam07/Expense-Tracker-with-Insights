# ADR-0003: System settlement accounts for deposits and withdrawals

- **Status:** Accepted (2026-11-15)

## Context

A deposit has no second customer. To keep every journal entry balanced, the other side must be an account too.

## Decision

Introduce **system ledger accounts**, starting with `SYS-CASH` (simulated cash held by the bank).

### Debit/credit conventions

| Account kind | Normal balance | Increases with |
|---|---|---|
| Customer deposit account (a **liability** of the bank) | Credit | Credit |
| `SYS-CASH` (an **asset** of the bank) | Debit | Debit |

| Operation | Debit | Credit |
|---|---|---|
| Deposit of INR 500 | `SYS-CASH` 500 | Customer 500 |
| Withdrawal of INR 200 | Customer 200 | `SYS-CASH` 200 |
| Transfer of INR 2,000, A to B | A 2,000 | B 2,000 |

Every journal entry satisfies: sum of debits = sum of credits.

## Consequences

- Deposits and withdrawals balance without inventing a fake customer.
- The `SYS-CASH` balance equals total simulated money brought in, minus money taken out, which gives a built-in reconciliation check: it must equal the sum of all customer balances.
- All funds are simulated. No real cash, payment rails, or banks are involved.
