"""Versioned customer policies and internal transfer approval records."""

from alembic import op
from sqlalchemy import text

revision = "0005_transfer_approvals"
down_revision = "0004_account_holds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    CREATE TABLE approval_policies (
        id uuid NOT NULL, version integer NOT NULL CHECK(version>0),
        customer_id uuid NOT NULL REFERENCES customers, name text NOT NULL CHECK(trim(name)<>''),
        currency text NOT NULL CHECK(currency='INR'),
        minimum numeric(18,2) NOT NULL CHECK(minimum>=0 AND minimum<>'NaN'),
        maximum numeric(18,2) CHECK(maximum>=minimum AND maximum<>'NaN'),
        required_count integer NOT NULL CHECK(required_count>0),
        ttl_seconds integer CHECK(ttl_seconds>0), active boolean NOT NULL,
        recorded_at timestamptz NOT NULL, actor uuid NOT NULL REFERENCES users,
        PRIMARY KEY(id,version), UNIQUE(customer_id,id,version)
    );
    CREATE TABLE approval_requests (
        id uuid PRIMARY KEY, subject_type text NOT NULL CHECK(subject_type='internal_transfer'),
        subject_id uuid NOT NULL UNIQUE, maker uuid NOT NULL REFERENCES users,
        customer_id uuid NOT NULL REFERENCES customers, policy_id uuid NOT NULL,
        policy_version integer NOT NULL, FOREIGN KEY(customer_id,policy_id,policy_version)
            REFERENCES approval_policies(customer_id,id,version),
        source_id uuid NOT NULL REFERENCES accounts,
        destination_id uuid NOT NULL REFERENCES accounts, CHECK(source_id<>destination_id),
        amount numeric(18,2) NOT NULL CHECK(amount>0 AND amount<>'NaN'),
        currency text NOT NULL CHECK(currency='INR'), description text NOT NULL,
        payload_hash text NOT NULL CHECK(length(payload_hash)=64), idempotency_key text NOT NULL,
        UNIQUE(maker,idempotency_key), hold_id uuid NOT NULL UNIQUE REFERENCES account_holds,
        original_hold_id uuid REFERENCES account_holds, created_at timestamptz NOT NULL,
        expires_at timestamptz CHECK(expires_at>created_at),
        status text NOT NULL CHECK(status IN ('pending_approval','approved','rejected','expired')),
        completed_at timestamptz, CHECK((status='pending_approval')=(completed_at IS NULL)),
        UNIQUE(id,maker)
    );
    CREATE INDEX approval_queue ON approval_requests(customer_id,status,created_at,id);
    CREATE TABLE approval_decisions (
        request_id uuid NOT NULL, maker uuid NOT NULL, actor uuid NOT NULL REFERENCES users,
        FOREIGN KEY(request_id,maker) REFERENCES approval_requests(id,maker),
        CHECK(actor<>maker), PRIMARY KEY(request_id,actor),
        decision text NOT NULL CHECK(decision IN ('approve','reject')),
        reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 256),
        decided_at timestamptz NOT NULL
    );
    CREATE TABLE approval_events (
        id uuid PRIMARY KEY, request_id uuid NOT NULL REFERENCES approval_requests,
        kind text NOT NULL CHECK(kind IN ('requested','decision','approved','rejected','expired')),
        actor uuid REFERENCES users, CHECK((actor IS NULL)=(kind='expired')),
        occurred_at timestamptz NOT NULL, correlation_id text
    );
    REVOKE ALL ON approval_policies,approval_requests,approval_decisions,approval_events
        FROM ledgerops_runtime;
    GRANT SELECT,INSERT ON approval_policies,approval_requests,approval_decisions,approval_events
        TO ledgerops_runtime;
    GRANT UPDATE(status,completed_at) ON approval_requests TO ledgerops_runtime;
    """)


def downgrade() -> None:
    if op.get_bind().scalar(text("SELECT EXISTS(SELECT FROM ledgerops.approval_policies)")):
        raise RuntimeError("Approval policy history exists; refusing destructive downgrade")
    op.execute("""
    DROP TABLE ledgerops.approval_events,ledgerops.approval_decisions,
        ledgerops.approval_requests,ledgerops.approval_policies
    """)
