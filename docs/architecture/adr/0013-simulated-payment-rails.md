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
