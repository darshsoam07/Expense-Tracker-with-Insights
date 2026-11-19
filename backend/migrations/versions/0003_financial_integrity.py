"""Customer scope, immutable journals and internal transfers."""

from alembic import op
from sqlalchemy import text

revision = "0003_financial_integrity"
down_revision = "0002_identity_rbac_audit"
branch_labels = None
depends_on = None

TABLES = (
    "currencies",
    "customers",
    "customer_members",
    "chart_accounts",
    "ledger_accounts",
    "accounts",
    "account_balances",
    "journal_entries",
    "journal_postings",
    "transfers",
)


def upgrade() -> None:
    op.execute("SET LOCAL search_path = ledgerops, pg_catalog")
    op.execute("""
    INSERT INTO ledgerops.permissions(code,description) VALUES
        ('accounts.read','View member accounts'),('ledger.read','View member account postings'),
        ('transfers.create','Post internal transfers between authorized accounts');
    INSERT INTO ledgerops.role_permissions(role_id,permission_id)
        SELECT r.id,p.id FROM ledgerops.roles r CROSS JOIN ledgerops.permissions p
        WHERE (r.code IN ('admin','operator','auditor') AND p.code IN
               ('accounts.read','ledger.read'))
           OR (r.code IN ('admin','operator') AND p.code='transfers.create');
    CREATE TABLE currencies (code text PRIMARY KEY CHECK (code ~ '^[A-Z]{3}$'));
    INSERT INTO currencies(code) VALUES ('INR');
    CREATE TABLE customers (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL CHECK
            (length(trim(name))>0),
        kind text NOT NULL CHECK (kind IN ('individual','organization')),
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE customer_members (
        customer_id uuid NOT NULL REFERENCES customers, user_id uuid NOT NULL REFERENCES users,
        role text NOT NULL CHECK (role IN ('owner','administrator','member','viewer')),
        active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(customer_id,user_id)
    );
    CREATE INDEX member_customers ON customer_members(user_id,customer_id) WHERE active;
    CREATE TABLE chart_accounts (
        code text PRIMARY KEY, name text NOT NULL,
        classification text NOT NULL CHECK(classification IN
            ('asset','liability','equity','revenue','expense')),
        normal_side text NOT NULL CHECK(normal_side IN ('debit','credit')),
        postable boolean NOT NULL DEFAULT true, active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    INSERT INTO chart_accounts(code,name,classification,normal_side) VALUES
        ('2000','Customer deposits','liability','credit'),('1000','Simulated cash','asset','debit');
    CREATE TABLE ledger_accounts (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL REFERENCES chart_accounts,
        currency text NOT NULL REFERENCES currencies(code) CHECK(currency='INR'), active boolean
            NOT NULL DEFAULT true,
        UNIQUE(id,currency), UNIQUE(id,code,currency)
    );
    CREATE TABLE accounts (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(), reference uuid UNIQUE NOT NULL DEFAULT
            gen_random_uuid(),
        customer_id uuid NOT NULL REFERENCES customers, account_type text NOT NULL DEFAULT
            'deposit' CHECK(account_type='deposit'),
        currency text NOT NULL REFERENCES currencies(code) CHECK(currency='INR'), status text NOT
            NULL DEFAULT 'active' CHECK(status IN ('active','closed','frozen')),
        ledger_id uuid NOT NULL UNIQUE, code text NOT NULL DEFAULT '2000' CHECK(code='2000'),
        FOREIGN KEY(ledger_id,code,currency) REFERENCES ledger_accounts(id,code,currency),
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX customer_accounts ON accounts(customer_id,id);
    CREATE TABLE account_balances (
        lock_marker boolean NOT NULL DEFAULT true CHECK(lock_marker),
        ledger_id uuid PRIMARY KEY, currency text NOT NULL,
        FOREIGN KEY(ledger_id,currency) REFERENCES ledger_accounts(id,currency),
        ledger_balance numeric(18,2) NOT NULL DEFAULT 0 CHECK(ledger_balance>=0 AND
            ledger_balance<>'NaN'),
        available_balance numeric(18,2) GENERATED ALWAYS AS (ledger_balance) STORED,
        updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE journal_entries (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(), reference uuid UNIQUE NOT NULL DEFAULT
            gen_random_uuid(),
        description text NOT NULL, currency text NOT NULL REFERENCES currencies(code)
            CHECK(currency='INR'),
        status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','posted')),
        actor_id uuid REFERENCES users, actor_principal text NOT NULL,
        CHECK ((actor_id IS NOT NULL AND actor_principal = 'user:' || actor_id::text) OR
               (actor_id IS NULL AND actor_principal ~ '^system:[a-z][a-z0-9_-]*$')),
        created_at timestamptz NOT NULL DEFAULT now(),
        posted_at timestamptz, UNIQUE(id,currency)
    );
    CREATE TABLE journal_postings (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(), journal_id uuid NOT NULL, ledger_id uuid NOT
            NULL,
        currency text NOT NULL, debit numeric(18,2) NOT NULL, credit numeric(18,2) NOT NULL,
        CHECK(debit<>'NaN' AND credit<>'NaN' AND ((debit>0 AND credit=0) OR (credit>0 AND
            debit=0))),
        FOREIGN KEY(journal_id,currency) REFERENCES journal_entries(id,currency),
        FOREIGN KEY(ledger_id,currency) REFERENCES ledger_accounts(id,currency),
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ledger_activity ON journal_postings(ledger_id,created_at DESC,id);
    CREATE INDEX journal_lines ON journal_postings(journal_id);
    CREATE TABLE transfers (
        id uuid PRIMARY KEY, actor_id uuid NOT NULL REFERENCES users, operation text NOT NULL
            DEFAULT 'internal_transfer',
        idempotency_key text NOT NULL, payload_hash text NOT NULL,
            UNIQUE(actor_id,operation,idempotency_key),
        source_id uuid NOT NULL REFERENCES accounts, destination_id uuid NOT NULL REFERENCES
            accounts,
        CHECK(source_id<>destination_id), amount numeric(18,2) NOT NULL CHECK(amount>0 AND
            amount<>'NaN'),
        currency text NOT NULL REFERENCES currencies(code) CHECK(currency='INR'), journal_id uuid
            NOT NULL UNIQUE,
        FOREIGN KEY(journal_id,currency) REFERENCES journal_entries(id,currency) DEFERRABLE
            INITIALLY DEFERRED,
        status text NOT NULL DEFAULT 'posted' CHECK(status='posted'), created_at timestamptz NOT
            NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE FUNCTION ledgerops.guard_header() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='INSERT' AND NEW.status='draft' AND NEW.posted_at IS NULL THEN RETURN NEW; END IF;
      IF TG_OP='UPDATE' AND OLD.status='draft' AND NEW.status='posted' THEN
        NEW.posted_at=clock_timestamp(); RETURN NEW;
      END IF;
      RAISE EXCEPTION 'Invalid journal transition';
    END $$;
    CREATE TRIGGER protect_header BEFORE INSERT OR UPDATE OR DELETE ON journal_entries
      FOR EACH ROW EXECUTE FUNCTION ledgerops.guard_header();
    CREATE FUNCTION ledgerops.guard_line() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='INSERT' AND (SELECT status FROM ledgerops.journal_entries WHERE id=NEW.journal_id
          FOR UPDATE)='draft'
        AND EXISTS(SELECT FROM ledgerops.ledger_accounts l JOIN ledgerops.chart_accounts c
            USING(code)
                   WHERE l.id=NEW.ledger_id AND l.active AND c.active AND c.postable)
      THEN RETURN NEW; END IF;
      RAISE EXCEPTION 'Invalid journal posting';
    END $$;
    CREATE TRIGGER protect_line BEFORE INSERT OR UPDATE OR DELETE ON journal_postings
      FOR EACH ROW EXECUTE FUNCTION ledgerops.guard_line();
    CREATE FUNCTION ledgerops.validate_journal() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (SELECT status FROM ledgerops.journal_entries WHERE id=NEW.id)<>'posted'
        OR (SELECT count(*)<2 OR sum(debit)<>sum(credit) FROM ledgerops.journal_postings WHERE
            journal_id=NEW.id)
      THEN RAISE EXCEPTION 'Journal incomplete or unbalanced'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER journal_balanced AFTER INSERT ON journal_entries
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledgerops.validate_journal();
    CREATE FUNCTION ledgerops.project_journal() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
      SET search_path=pg_catalog,ledgerops AS $$
    BEGIN
      UPDATE ledgerops.account_balances b SET ledger_balance=b.ledger_balance+d.delta,
          updated_at=clock_timestamp()
      FROM (SELECT p.ledger_id, sum(CASE c.normal_side WHEN 'credit' THEN p.credit-p.debit ELSE
          p.debit-p.credit END) delta
            FROM ledgerops.journal_postings p JOIN ledgerops.ledger_accounts l ON l.id=p.ledger_id
            JOIN ledgerops.chart_accounts c USING(code) WHERE p.journal_id=NEW.id GROUP BY
                p.ledger_id) d
      WHERE b.ledger_id=d.ledger_id;
      IF EXISTS (SELECT FROM ledgerops.journal_postings p LEFT JOIN ledgerops.account_balances b
          USING(ledger_id)
                 WHERE p.journal_id=NEW.id AND b.ledger_id IS NULL) THEN
          RAISE EXCEPTION 'Missing projection';
      END IF;
      RETURN NULL;
    END $$;
    CREATE TRIGGER apply_projection AFTER UPDATE ON journal_entries
      FOR EACH ROW EXECUTE FUNCTION ledgerops.project_journal();
    """)
    for table in TABLES:
        op.execute(f"REVOKE ALL ON ledgerops.{table} FROM ledgerops_runtime")
        op.execute(f"GRANT SELECT ON ledgerops.{table} TO ledgerops_runtime")
    op.execute(
        "GRANT INSERT ON ledgerops.transfers, ledgerops.journal_entries, "
        "ledgerops.journal_postings TO ledgerops_runtime"
    )
    op.execute("GRANT UPDATE(status) ON ledgerops.journal_entries TO ledgerops_runtime")
    # One inert column permits row locking without granting write access to either balance.
    op.execute("GRANT UPDATE(lock_marker) ON ledgerops.account_balances TO ledgerops_runtime")


def downgrade() -> None:
    if op.get_bind().scalar(
        text(
            "SELECT EXISTS(SELECT FROM ledgerops.customers) OR EXISTS(SELECT FROM "
            "ledgerops.ledger_accounts) OR EXISTS(SELECT FROM ledgerops.journal_entries)"
        )
    ):
        raise RuntimeError("Financial data exists; refusing destructive downgrade")
    op.execute("""
    DELETE FROM ledgerops.role_permissions WHERE permission_id IN
        (SELECT id FROM ledgerops.permissions WHERE code IN
            ('accounts.read','ledger.read','transfers.create'));
    DELETE FROM ledgerops.permissions WHERE code IN
        ('accounts.read','ledger.read','transfers.create');
    """)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE ledgerops.{table}")
    for function in ("guard_header", "guard_line", "validate_journal", "project_journal"):
        op.execute(f"DROP FUNCTION ledgerops.{function}()")
