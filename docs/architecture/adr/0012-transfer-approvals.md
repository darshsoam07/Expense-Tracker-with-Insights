# 0012. Independent review of reserved transfers

Internal INR transfers use the latest effective revision of each source-customer policy.
Bounds are inclusive. No match posts immediately. Overlapping matches return a conflict.
Pending requests pin their policy revision and original submission fingerprint.
The request's subject ID identifies the transfer intent and becomes the posted transfer ID.

Authenticated operators, auditors, approvers and administrators with active membership on both
accounts can read the queue at `GET /api/v1/approvals` and individual requests by ID. Approvers
and administrators can post a reason to `/{id}/approve` or `/{id}/reject` under that route
using the existing CSRF header. Makers cannot decide their own request. Each reviewer can
record one decision. Approvers have no implicit transfer creation permission.

The final independent approval captures the hold and posts the balanced journal in the same
database transaction as the decision and audit history. Rejection releases the reservation.
Expiry is lazy: accessing balances, refreshing the queue or attempting a decision observes
the deadline under lock. An idle workspace has no background expiry schedule.

Policy configuration uses immutable database revisions in this milestone. The console exposes
review decisions. It has no policy editor. All accounts, amounts and transfers are simulated.
