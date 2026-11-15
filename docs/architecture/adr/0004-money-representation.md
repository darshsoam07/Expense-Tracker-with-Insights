# ADR-0004: Money representation

- **Status:** Accepted (2026-11-15)

## Context

The legacy app stored money as binary floating point. Its own summary endpoint returned `0.30000000000000004` for `0.1 + 0.2`, and it accepted `NaN` and `Infinity`, which crashed it.

## Decision

- Database: `NUMERIC(18,2)`.
- Python: `decimal.Decimal`. Never `float` for money.
- JSON: amounts are **strings**, for example `"2000.00"`. The API rejects JSON numbers for money fields.
- The API **rejects** `NaN`, `Infinity`, negative or zero amounts where a positive amount is required, and more than two decimal places. It does not silently round.
- Currency: **INR is the only supported currency in version 1.** A `currency` column is kept on money-bearing tables, constrained to `'INR'`, so adding currencies later does not require restructuring.

## Consequences

- Clients must send `"2000.00"`, not `2000`.
- Aggregations happen in the database or with `Decimal`, never with float arithmetic.
- The currency column is intentionally redundant today and is the extension point.
