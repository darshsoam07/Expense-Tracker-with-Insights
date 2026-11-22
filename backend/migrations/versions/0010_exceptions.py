"""Operational exception investigations and immutable event history."""

from alembic import op

revision = "0010_exceptions"
down_revision = "0009_settlement_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        SET LOCAL search_path=ledgerops,pg_catalog;
        CREATE TABLE exceptions (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          reference uuid UNIQUE NOT NULL DEFAULT gen_random_uuid(),
          customer_id uuid NOT NULL REFERENCES customers, source_domain text NOT NULL,
          source_reference uuid NOT NULL, exception_type text NOT NULL,
          severity text NOT NULL CHECK(severity IN ('low','medium','high','critical')),
          status text NOT NULL
            CHECK(status IN ('open','investigating','awaiting_information','resolved','closed')),
          title text NOT NULL, description text NOT NULL, assigned_user_id uuid REFERENCES users,
          resolution_summary text, resolved_at timestamptz, closed_at timestamptz,
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          UNIQUE(source_domain,source_reference,exception_type)
        );
        CREATE INDEX exceptions_queue ON exceptions(customer_id,status,severity,created_at DESC);
        CREATE TABLE exception_events (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          sequence bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
          exception_id uuid NOT NULL REFERENCES exceptions,
          kind text NOT NULL, actor_id uuid REFERENCES users, occurred_at timestamptz NOT NULL,
          previous_status text, next_status text, note text, metadata jsonb NOT NULL DEFAULT '{}'
        );
        CREATE INDEX exception_events_history ON exception_events(exception_id, sequence);
        CREATE FUNCTION reject_exception_event_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Exception history is append-only'; END $$;
        CREATE TRIGGER immutable_exception_events
          BEFORE UPDATE OR DELETE OR TRUNCATE ON exception_events
          FOR EACH STATEMENT EXECUTE FUNCTION reject_exception_event_change();
        INSERT INTO permissions(code,description) VALUES
          ('exceptions.read','Read customer-scoped operational exceptions'),
          ('exceptions.manage','Investigate customer-scoped operational exceptions');
        INSERT INTO role_permissions(role_id,permission_id)
          SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE
          (p.code='exceptions.read' AND r.code IN ('admin','operator','approver','auditor')) OR
          (p.code='exceptions.manage' AND r.code IN ('admin','operator'));
        GRANT SELECT,INSERT ON exceptions,exception_events TO ledgerops_runtime;
        GRANT UPDATE(status,assigned_user_id,resolution_summary,resolved_at,closed_at,updated_at)
          ON exceptions TO ledgerops_runtime;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        SET LOCAL search_path=ledgerops,pg_catalog;
        DO $$ BEGIN
          IF EXISTS(SELECT FROM exceptions) THEN RAISE EXCEPTION 'Exception history exists'; END IF;
        END $$;
        DELETE FROM role_permissions
          WHERE permission_id IN (SELECT id FROM permissions WHERE code LIKE 'exceptions.%');
        DELETE FROM permissions WHERE code LIKE 'exceptions.%';
        DROP TABLE exception_events,exceptions;
        DROP FUNCTION reject_exception_event_change();
        """
    )
