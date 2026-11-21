"""Payment instructions, simulated rail events and approval subjects."""

from alembic import op
from sqlalchemy import text

revision = "0007_payment_instructions"
down_revision = "0006_approval_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    ALTER TABLE approval_requests DROP CONSTRAINT approval_requests_subject_type_check;
    ALTER TABLE approval_requests DROP CONSTRAINT approval_requests_check;
    ALTER TABLE approval_requests ALTER COLUMN destination_id DROP NOT NULL;
    ALTER TABLE approval_requests ADD CHECK(subject_type IN ('internal_transfer','payment'));
    ALTER TABLE approval_requests ADD CHECK(
      (subject_type='internal_transfer' AND destination_id IS NOT NULL
       AND source_id<>destination_id) OR
      (subject_type='payment' AND destination_id IS NULL));

    CREATE TABLE payment_instructions (
      id uuid PRIMARY KEY, customer_id uuid NOT NULL REFERENCES customers,
      source_id uuid NOT NULL REFERENCES accounts, actor_id uuid NOT NULL REFERENCES users,
      customer_reference text NOT NULL CHECK(length(trim(customer_reference)) BETWEEN 1 AND 128),
      beneficiary_name text NOT NULL CHECK(length(trim(beneficiary_name)) BETWEEN 1 AND 128),
      destination_reference text NOT NULL
        CHECK(length(trim(destination_reference)) BETWEEN 1 AND 128),
      amount numeric(18,2) NOT NULL CHECK(amount>0 AND amount<>'NaN'),
      currency text NOT NULL CHECK(currency='INR'), rail text NOT NULL CHECK(rail='SIMULATED_INR'),
      status text NOT NULL CHECK(status IN ('pending_approval','ready_for_submission',
        'submitted','accepted','failed','outcome_unknown','cancelled')),
      hold_id uuid NOT NULL UNIQUE REFERENCES account_holds,
      approval_id uuid UNIQUE REFERENCES approval_requests DEFERRABLE INITIALLY DEFERRED,
      idempotency_key text NOT NULL, payload_hash text NOT NULL CHECK(length(payload_hash)=64),
      provider_reference text NOT NULL UNIQUE,
      created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
      UNIQUE(actor_id,idempotency_key)
    );
    CREATE INDEX payments_by_customer ON payment_instructions(customer_id,created_at DESC,id);
    CREATE TABLE payment_events (
      id uuid PRIMARY KEY, payment_id uuid NOT NULL REFERENCES payment_instructions,
      kind text NOT NULL CHECK(kind IN ('created','approved','submitted','accepted','failed',
        'outcome_unknown','retry_ready','cancelled')),
      actor uuid REFERENCES users, occurred_at timestamptz NOT NULL,
      provider_reference text, detail text, correlation_id text
    );
    CREATE INDEX payment_history ON payment_events(payment_id,occurred_at,id);
    CREATE FUNCTION project_payment_event() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE previous ledgerops.payment_instructions%ROWTYPE;
    BEGIN
      SELECT * INTO STRICT previous FROM ledgerops.payment_instructions
        WHERE id=NEW.payment_id FOR UPDATE;
      IF NEW.kind='created' AND previous.status IN
        ('pending_approval','ready_for_submission') THEN
        NULL;
      ELSIF NEW.kind='approved' AND previous.status='pending_approval' THEN
        UPDATE ledgerops.payment_instructions
          SET status='ready_for_submission',updated_at=NEW.occurred_at
          WHERE id=NEW.payment_id;
      ELSIF NEW.kind='submitted' AND previous.status='ready_for_submission' THEN
        UPDATE ledgerops.payment_instructions SET status='submitted',updated_at=NEW.occurred_at
          WHERE id=NEW.payment_id;
      ELSIF NEW.kind='accepted' AND previous.status IN ('submitted','outcome_unknown') THEN
        UPDATE ledgerops.payment_instructions SET status='accepted',updated_at=NEW.occurred_at
          WHERE id=NEW.payment_id;
      ELSIF NEW.kind='failed' AND previous.status IN
        ('ready_for_submission','submitted','outcome_unknown') THEN
        UPDATE ledgerops.payment_instructions SET status='failed',updated_at=NEW.occurred_at
          WHERE id=NEW.payment_id;
      ELSIF NEW.kind='outcome_unknown' AND previous.status='submitted' THEN
        UPDATE ledgerops.payment_instructions
          SET status='outcome_unknown',updated_at=NEW.occurred_at
          WHERE id=NEW.payment_id;
      ELSIF NEW.kind='retry_ready' AND previous.status='submitted' THEN
        UPDATE ledgerops.payment_instructions
          SET status='ready_for_submission',updated_at=NEW.occurred_at
          WHERE id=NEW.payment_id;
      ELSIF NEW.kind='cancelled' AND previous.status IN
        ('pending_approval','ready_for_submission') THEN
        UPDATE ledgerops.payment_instructions SET status='cancelled',updated_at=NEW.occurred_at
          WHERE id=NEW.payment_id;
      ELSE RAISE EXCEPTION 'Invalid payment transition';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER payment_transition BEFORE INSERT ON payment_events
      FOR EACH ROW EXECUTE FUNCTION project_payment_event();
    CREATE FUNCTION reject_payment_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Payment history is append-only'; END $$;
    CREATE TRIGGER immutable_payment_events BEFORE UPDATE OR DELETE OR TRUNCATE ON payment_events
      FOR EACH STATEMENT EXECUTE FUNCTION reject_payment_history_change();

    REVOKE ALL ON payment_instructions,payment_events FROM ledgerops_runtime;
    GRANT SELECT,INSERT ON payment_instructions,payment_events TO ledgerops_runtime;
    GRANT UPDATE(status,updated_at,approval_id) ON payment_instructions TO ledgerops_runtime;
    INSERT INTO permissions(code,description) VALUES
      ('payments.read','Read scoped payment instructions'),
      ('payments.create','Create payment instructions'),
      ('payments.submit','Submit instructions to the simulated rail'),
      ('payments.cancel','Cancel eligible payment instructions');
    INSERT INTO role_permissions(role_id,permission_id)
      SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE
      (p.code='payments.read' AND r.code IN ('admin','operator','auditor','approver')) OR
      (p.code IN ('payments.create','payments.submit','payments.cancel')
       AND r.code IN ('admin','operator'));
    """)


def downgrade() -> None:
    if op.get_bind().scalar(text("SELECT EXISTS(SELECT FROM ledgerops.payment_instructions)")):
        raise RuntimeError("Payment history exists; refusing destructive downgrade")
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    DELETE FROM role_permissions WHERE permission_id IN
      (SELECT id FROM permissions WHERE code LIKE 'payments.%');
    DELETE FROM permissions WHERE code LIKE 'payments.%';
    DROP TABLE payment_events,payment_instructions;
    DROP FUNCTION project_payment_event(),reject_payment_history_change();
    ALTER TABLE approval_requests DROP CONSTRAINT approval_requests_check;
    ALTER TABLE approval_requests DROP CONSTRAINT approval_requests_subject_type_check;
    ALTER TABLE approval_requests ALTER COLUMN destination_id SET NOT NULL;
    ALTER TABLE approval_requests ADD CHECK(subject_type='internal_transfer');
    ALTER TABLE approval_requests ADD CHECK(source_id<>destination_id);
    """)
