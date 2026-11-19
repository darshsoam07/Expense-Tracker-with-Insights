"""Account reservations and append-only lifecycle commands."""

from alembic import op
from sqlalchemy import text

revision = "0004_account_holds"
down_revision = "0003_financial_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    ALTER TABLE account_balances DROP COLUMN available_balance,
        ADD COLUMN held_amount numeric(18,2) NOT NULL DEFAULT 0
            CHECK(held_amount BETWEEN 0 AND ledger_balance);
    ALTER TABLE account_balances ADD COLUMN available_balance numeric(18,2)
        GENERATED ALWAYS AS (ledger_balance-held_amount) STORED;
    ALTER TABLE accounts ADD CONSTRAINT account_currency UNIQUE(id,currency);
    CREATE TABLE account_holds (
        id uuid PRIMARY KEY, account_id uuid NOT NULL, currency text NOT NULL,
        FOREIGN KEY(account_id,currency) REFERENCES accounts(id,currency),
        original_amount numeric(18,2) NOT NULL CHECK(original_amount>0 AND original_amount<>'NaN'),
        remaining numeric(18,2) NOT NULL CHECK(remaining BETWEEN 0 AND original_amount),
        status text NOT NULL CHECK(status IN ('active','partially_released','released',
                                              'expired','captured')),
        reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 256),
        business_reference text, creator uuid NOT NULL REFERENCES users,
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, expires_at timestamptz,
        CHECK(expires_at IS NULL OR expires_at>created_at),
        CHECK((remaining>0)=(status IN ('active','partially_released')))
    );
    CREATE INDEX holds_by_account ON account_holds(account_id,created_at DESC,id);
    CREATE INDEX due_holds ON account_holds(account_id,expires_at) WHERE remaining>0;
    CREATE TABLE hold_events (
        id uuid PRIMARY KEY, hold_id uuid NOT NULL REFERENCES account_holds
            DEFERRABLE INITIALLY DEFERRED, account_id uuid NOT NULL REFERENCES accounts,
        kind text NOT NULL CHECK(kind IN ('created','partially_released','released',
                                          'expired','captured')),
        currency text NOT NULL CHECK(currency='INR'), amount numeric(18,2) NOT NULL
            CHECK(amount>0 AND amount<>'NaN'), remaining numeric(18,2) NOT NULL CHECK(remaining>=0),
        occurred_at timestamptz NOT NULL, actor uuid REFERENCES users,
        CHECK((actor IS NULL)=(kind='expired')),
        command text NOT NULL, key text, digest text,
        UNIQUE(actor,command,key),
        CHECK((key IS NOT NULL AND digest IS NOT NULL)=(command IN ('create','release'))),
        CHECK(command=CASE kind WHEN 'created' THEN 'create' WHEN 'expired' THEN 'expire'
                  WHEN 'captured' THEN 'capture' ELSE 'release' END),
        reason text, business_reference text, expires_at timestamptz,
        journal_id uuid UNIQUE REFERENCES journal_entries DEFERRABLE INITIALLY DEFERRED,
        CHECK((journal_id IS NOT NULL)=(kind='captured'))
    );
    CREATE INDEX events_by_hold ON hold_events(hold_id,occurred_at,id);
    REVOKE ALL ON account_holds,hold_events FROM ledgerops_runtime;
    GRANT SELECT ON account_holds,hold_events TO ledgerops_runtime;
    GRANT INSERT ON hold_events TO ledgerops_runtime;
    CREATE FUNCTION apply_hold_event() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog,ledgerops AS $$
    DECLARE previous account_holds; delta numeric;
    BEGIN
        IF NEW.kind='created' THEN
            IF NEW.remaining<>NEW.amount THEN RAISE EXCEPTION 'Invalid opening amount'; END IF;
            INSERT INTO account_holds(id,account_id,currency,original_amount,remaining,status,
                reason,business_reference,creator,created_at,updated_at,expires_at)
            VALUES(NEW.hold_id,NEW.account_id,NEW.currency,NEW.amount,NEW.amount,'active',
                NEW.reason,NEW.business_reference,NEW.actor,NEW.occurred_at,NEW.occurred_at,
                NEW.expires_at);
            delta=NEW.amount;
        ELSE
            SELECT * INTO STRICT previous FROM account_holds WHERE id=NEW.hold_id FOR UPDATE;
            IF previous.account_id<>NEW.account_id OR previous.currency<>NEW.currency
               OR previous.remaining<=0 OR previous.remaining-NEW.amount<>NEW.remaining
               OR ((NEW.kind='partially_released')<>(NEW.remaining>0))
               OR ((NEW.kind='expired')<>coalesce(previous.expires_at<=NEW.occurred_at,false))
            THEN RAISE EXCEPTION 'Invalid hold transition'; END IF;
            IF NEW.kind='captured' AND NOT EXISTS (
                SELECT FROM transfers WHERE journal_id=NEW.journal_id AND source_id=NEW.account_id
                    AND amount=NEW.amount AND currency=NEW.currency AND actor_id=NEW.actor
                    AND xmin=pg_current_xact_id()::text::xid
            ) THEN RAISE EXCEPTION 'Capture requires matching transfer'; END IF;
            UPDATE account_holds SET remaining=NEW.remaining,status=NEW.kind,
                updated_at=NEW.occurred_at WHERE id=NEW.hold_id;
            delta=-NEW.amount;
        END IF;
        UPDATE account_balances b SET held_amount=b.held_amount+delta,updated_at=NEW.occurred_at
          FROM accounts a WHERE a.id=NEW.account_id AND a.ledger_id=b.ledger_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Missing balance projection'; END IF;
        RETURN NULL;
    END $$;
    CREATE TRIGGER project_hold AFTER INSERT ON hold_events
        FOR EACH ROW EXECUTE FUNCTION apply_hold_event();
    CREATE FUNCTION check_hold_capture() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,ledgerops AS $$
    BEGIN
        IF NOT EXISTS(SELECT FROM journal_entries j JOIN journal_postings p ON p.journal_id=j.id
            JOIN accounts a ON a.ledger_id=p.ledger_id WHERE j.id=NEW.journal_id AND
            j.status='posted' AND a.id=NEW.account_id AND p.debit=NEW.amount AND p.credit=0)
        THEN RAISE EXCEPTION 'Capture requires posted deposit debit'; END IF;
        RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER validate_capture AFTER INSERT ON hold_events
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.kind='captured')
        EXECUTE FUNCTION check_hold_capture();
    CREATE FUNCTION reject_hold_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Hold events are append-only'; END $$;
    CREATE TRIGGER immutable_hold_events BEFORE UPDATE OR DELETE OR TRUNCATE ON hold_events
        FOR EACH STATEMENT EXECUTE FUNCTION reject_hold_history_change();
    INSERT INTO permissions(code,description) VALUES ('holds.read','Read scoped reservations'),
        ('holds.create','Reserve available funds'),('holds.release','Release scoped reservations');
    INSERT INTO role_permissions(role_id,permission_id)
      SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
      WHERE (r.code IN ('admin','operator') AND p.code IN ('holds.read','holds.create',
                                                          'holds.release'))
         OR (r.code='auditor' AND p.code='holds.read');
    """)


def downgrade() -> None:
    if op.get_bind().scalar(text("SELECT EXISTS(SELECT FROM ledgerops.hold_events)")):
        raise RuntimeError("Hold history exists; refusing destructive downgrade")
    op.execute("""
    SET LOCAL search_path=ledgerops,pg_catalog;
    DELETE FROM role_permissions WHERE permission_id IN
        (SELECT id FROM permissions WHERE code IN ('holds.read','holds.create','holds.release'));
    DELETE FROM permissions WHERE code IN ('holds.read','holds.create','holds.release');
    DROP TABLE hold_events,account_holds;
    DROP FUNCTION apply_hold_event(),check_hold_capture(),reject_hold_history_change();
    ALTER TABLE accounts DROP CONSTRAINT account_currency;
    ALTER TABLE account_balances DROP COLUMN available_balance,DROP COLUMN held_amount;
    ALTER TABLE account_balances ADD COLUMN available_balance numeric(18,2)
        GENERATED ALWAYS AS (ledger_balance) STORED;
    """)
