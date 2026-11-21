# 0013. Payment instructions and simulated INR rail

LedgerOps stores external payment instructions separately from internal transfers. Instructions
snapshot the beneficiary name and destination reference, reserve funds with an account hold, and
use persistent actor scoped idempotency. They contain synthetic data and never make network calls.

The lifecycle is `pending_approval`, `ready_for_submission`, `submitted`, then `accepted`,
`failed`, or `outcome_unknown`. Eligible instructions may become `cancelled`. Lifecycle
events are append only and PostgreSQL validates transitions. A matching customer policy reuses
the maker checker engine. Final approval makes a payment ready for submission and leaves its hold
active.

The deterministic adapter identifies itself as `SIMULATED_INR`. Automated tests inject accepted,
rejected, temporary unavailable, and timeout outcomes. Provider references are stable per payment.
A confirmed rejection releases the hold. Temporary unavailability returns the instruction to
ready state. An ambiguous timeout retains the hold and reuses the same payment and provider
reference on resolution.

Accepted means the simulated rail accepted the instruction. It does not mean settled. Accepted
instructions retain their holds, create no journal, and await the separate settlement milestone.
The API and console support INR only. They do not integrate real providers or credentials.

Use `POST /api/v1/payments` with an Idempotency-Key and a decimal-string amount.
Supply source_id, beneficiary_name, destination_reference, customer_reference and currency.
Read instructions with `GET /api/v1/payments?limit=25&offset=0` or by appending an ID.
POST to the instruction's `/submit` endpoint for initial submission or retry, or to
`/cancel` before submission is irrevocable. Mutations use the existing session and CSRF token.

| Role | Payment permissions in an active customer membership |
|---|---|
| Admin, operator | Read, create, submit, cancel. Mutation requires a writable membership. |
| Auditor, approver | Read. Independent approval uses the existing decision permission. |
| Viewer | None. |

## PR 7d accounting amendment — platform INR nostro

The platform owns one simulated INR asset named PLATFORM-INR-NOSTRO. Chart code 1010 is debit-normal. Its deterministic ledger UUID and unique chart index identify it across workspaces. It has no customer account row. The provision command creates its zero projection explicitly. Synthetic workspace provisioning uses the same account for all future opening journals.

Run `python -m app.modules.finance.nostro` under the migration identity to provision the empty asset. Inspect legacy balances and opening journals before running the explicit `--consolidate` option. It locks the nostro and funded legacy cash projections, identifies the originating customer from posted synthetic opening journals, debits 1010 and credits the legacy 1000 asset. An ambiguous owner aborts the transaction. Zero balances need no journal. Each legacy ledger has a deterministic reclassification journal ID. Existing accounts and posted history remain available.

Outbound settlement debits customer deposit liabilities (2000) and credits 1010. The service locks the shared asset projection, verifies liquidity and the full payment reservation, then records a hold capture, balanced journal, customer-attributed settlement item and audit in the caller's transaction. Rail acceptance alone retains the hold. Inbound items require exception review and have no automatic accounting entry in this milestone.

PR 7d batch processing uses the settlement item journal as its posting receipt. Subsequent statement reconciliation stores comparison evidence separately. Batch retries and reconciliation rules are documented in [ADR 0014](0014-settlement-operations.md).
