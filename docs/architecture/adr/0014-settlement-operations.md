# ADR 0014 — Simulated settlement operations

Settlement reserves candidate payments for one customer and one batch. A payment must be accepted and fully reserved. Processing a batch moves it from created to processing. Each successful item commits its journal, hold capture, attribution and audit together through the platform nostro. Failed financial preconditions are recorded per item. Persisted posted counts determine settled, partially_settled or failed. Processing again resumes incomplete work. Unexpected infrastructure errors leave prior commits durable and the batch available for retry.

## API

All paths are under /api/v1/settlements and require an authenticated session. Reads use ledger.read. Writes use payments.submit, CSRF and an active writable customer membership. GET batches, statements and reconciliation-runs accept limit (1–100) and offset. Append /{id} for summary or /{id}/items for paginated detail. The latter lists reconciliation exceptions first.

POST /batches takes customer_id. POST /batches/{id}/process executes or retries the batch. POST /statements/import takes customer_id and filename query parameters with a raw text/csv body. POST /reconciliation-runs takes import_id. UUIDs serve as stable operational references.

## Simulated statement format

Upload a UTF-8 CSV with this header, at most 500 data rows and at most 256 KiB.

    provider_reference,external_reference,amount,currency,transaction_date,settlement_date,direction,status
    sim_example,EXT-001,125.50,INR,2026-11-20,2026-11-21,outbound,settled

Amounts must be positive decimal strings with at most two fractional digits. Dates use YYYY-MM-DD. Direction is outbound or inbound. Status is settled or failed. Only INR outbound settlement posts money. Other reported currency or direction values support discrepancy evidence. A byte-identical statement replay returns the original import within the customer. Each import retains one normalized row per external reference. Repeated references within the file or in earlier imports are flagged for review.

## Matching

Reconciliation snapshots evidence using the provider reference within the importing customer. An exact match requires a posted settlement, equal amount and currency, outbound direction, settled provider status and transaction and settlement dates within one calendar day of their respective UTC internal dates. Duplicate or ambiguous references take precedence over ordinary comparisons. A provider failure produces status_mismatch. Internal settlements within the inclusive range of statement settlement dates that have no corresponding line produce missing_statement_record. Runs write comparison results and audit history only.
