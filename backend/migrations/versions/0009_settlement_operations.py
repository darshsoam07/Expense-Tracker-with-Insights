"""Operational settlement batches and statement reconciliation."""

from alembic import op

revision = "0009_settlement_operations"
down_revision = "0008_platform_nostro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    CREATE TABLE settlement_batches (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), customer_id uuid NOT NULL REFERENCES customers,
      actor_id uuid NOT NULL REFERENCES users, created_at timestamptz NOT NULL DEFAULT now(),
      processed_at timestamptz, currency text NOT NULL DEFAULT 'INR' CHECK(currency='INR'),
      status text NOT NULL DEFAULT 'created' CHECK(status IN
        ('created','processing','partially_settled','settled','failed')),
      UNIQUE(id,customer_id));
    CREATE TABLE settlement_candidates (
      payment_id uuid PRIMARY KEY, batch_id uuid NOT NULL, customer_id uuid NOT NULL, failure text,
      FOREIGN KEY(batch_id,customer_id) REFERENCES settlement_batches(id,customer_id),
      FOREIGN KEY(payment_id,customer_id) REFERENCES payment_instructions(id,customer_id),
      UNIQUE(batch_id,payment_id));
    ALTER TABLE settlement_items ADD COLUMN batch_id uuid,
      ADD FOREIGN KEY(batch_id,payment_id) REFERENCES settlement_candidates(batch_id,payment_id);
    CREATE TABLE statement_imports (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),customer_id uuid NOT NULL REFERENCES customers,
      actor_id uuid NOT NULL REFERENCES users,filename text NOT NULL,checksum text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(customer_id,checksum));
    CREATE TABLE statement_lines (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),import_id uuid NOT NULL REFERENCES
        statement_imports,
      external_reference text NOT NULL,provider_reference text NOT NULL, amount
        numeric(18,2) NOT NULL,
      currency text NOT NULL,direction text NOT NULL,transaction_date date NOT NULL,
      settlement_date date NOT NULL,status text NOT NULL, duplicate boolean NOT NULL,
      UNIQUE(import_id,external_reference));
    CREATE TABLE reconciliation_runs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),import_id uuid NOT NULL REFERENCES
        statement_imports,
      actor_id uuid NOT NULL REFERENCES users,created_at timestamptz NOT NULL DEFAULT now(),
      completed_at timestamptz);
    CREATE TABLE reconciliation_results (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),run_id uuid NOT NULL REFERENCES
        reconciliation_runs,
      line_id uuid REFERENCES statement_lines,payment_id uuid REFERENCES payment_instructions,
      classification text NOT NULL,evidence jsonb NOT NULL);
    GRANT SELECT,INSERT ON settlement_batches,settlement_candidates,statement_imports,
        statement_lines,
      reconciliation_runs,reconciliation_results TO ledgerops_runtime;
    GRANT UPDATE(status,processed_at) ON settlement_batches TO ledgerops_runtime;
    GRANT UPDATE(failure) ON settlement_candidates TO ledgerops_runtime;
    GRANT UPDATE(batch_id) ON settlement_items TO ledgerops_runtime;
    GRANT UPDATE(completed_at) ON reconciliation_runs TO ledgerops_runtime;
    """)


def downgrade() -> None:
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    DO $$ BEGIN IF EXISTS(SELECT FROM settlement_batches) OR EXISTS(SELECT FROM statement_imports)
      THEN RAISE EXCEPTION 'Operational history exists'; END IF; END $$;
    ALTER TABLE settlement_items DROP COLUMN batch_id;
    DROP TABLE reconciliation_results,reconciliation_runs,statement_lines,statement_imports,
      settlement_candidates,settlement_batches;
    """)
