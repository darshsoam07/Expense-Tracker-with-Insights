"""Platform nostro chart and attributable outbound settlement items."""

from alembic import op

revision = "0008_platform_nostro"
down_revision = "0007_payment_instructions"
branch_labels = None
depends_on = None


TRANSFER_GUARD = ") THEN RAISE EXCEPTION 'Capture requires matching transfer'"
SETTLEMENT_GUARD = """) AND NOT EXISTS (
    SELECT FROM ledgerops.settlement_items s JOIN ledgerops.payment_instructions p
    ON p.id=s.payment_id AND p.customer_id=s.customer_id
    WHERE s.journal_id=NEW.journal_id AND s.actor_id=NEW.actor
    AND s.xmin=pg_current_xact_id()::text::xid AND p.hold_id=NEW.hold_id
    AND p.source_id=NEW.account_id AND p.amount=NEW.amount AND p.currency=NEW.currency
    AND p.status='accepted'
    ) THEN RAISE EXCEPTION 'Capture requires matching transfer or settlement'"""


def update_capture_guard(old: str, new: str) -> None:
    definition = (
        op.get_bind()
        .exec_driver_sql("SELECT pg_get_functiondef('ledgerops.apply_hold_event()'::regprocedure)")
        .scalar_one()
    )
    if definition.count(old) != 1:
        raise RuntimeError("Unexpected capture guard definition")
    op.get_bind().exec_driver_sql(definition.replace(old, new))


def upgrade() -> None:
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    INSERT INTO chart_accounts(code,name,classification,normal_side)
      VALUES ('1010','Platform INR nostro','asset','debit');
    CREATE UNIQUE INDEX platform_inr_nostro ON ledger_accounts(code) WHERE code='1010';
    ALTER TABLE payment_instructions ADD UNIQUE(id,customer_id);
    CREATE TABLE settlement_items (
      payment_id uuid PRIMARY KEY, customer_id uuid NOT NULL,
      journal_id uuid NOT NULL UNIQUE REFERENCES journal_entries DEFERRABLE INITIALLY DEFERRED,
      settled_at timestamptz NOT NULL, actor_id uuid NOT NULL REFERENCES users,
      FOREIGN KEY(payment_id,customer_id) REFERENCES payment_instructions(id,customer_id)
    );
    GRANT SELECT,INSERT ON settlement_items TO ledgerops_runtime;
    """)

    update_capture_guard(TRANSFER_GUARD, SETTLEMENT_GUARD)


def downgrade() -> None:
    update_capture_guard(SETTLEMENT_GUARD, TRANSFER_GUARD)
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    DO $$ BEGIN IF EXISTS(SELECT FROM ledger_accounts WHERE code='1010') OR
      EXISTS(SELECT FROM settlement_items) THEN RAISE EXCEPTION 'Settlement history exists';
      END IF; END $$;
    DROP TABLE settlement_items;
    ALTER TABLE payment_instructions DROP CONSTRAINT payment_instructions_id_customer_id_key;
    DROP INDEX platform_inr_nostro;
    DELETE FROM chart_accounts WHERE code='1010';
    """)
