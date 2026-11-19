"""Identity, RBAC, sessions and the append-only audit trail (PR 4a).

Design notes (see docs/architecture/pr4a-identity-rbac-audit.md):
  * Every object lives in the ``ledgerops`` schema and every constraint is named explicitly,
    so later migrations and drift checks never depend on generated names.
  * The migration is additive and self-contained: the seed data below is frozen here and is
    NOT imported from application code, so editing application constants can never rewrite
    history. Later permission changes ship as new migrations.
  * ``audit_events`` is protected twice: a statement-level trigger that rejects UPDATE, DELETE
    and TRUNCATE even when no rows match, and revoked UPDATE/DELETE privileges for the
    runtime role. Role, permission and role-permission definitions are read-only for the
    runtime role, so a compromised application cannot grant itself new rights.
  * Timestamps have no database default on purpose: the application supplies them from its
    injected Clock so behaviour is deterministic in tests.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_identity_rbac_audit"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

_RUNTIME = "ledgerops_runtime"

_ROLES = (
    ("admin", "Manages users, roles and platform settings."),
    ("operator", "Runs day-to-day financial operations."),
    ("approver", "Reviews and decides approval requests."),
    ("auditor", "Read-only access to the audit trail."),
    ("viewer", "Read-only access to non-sensitive views."),
)
_PERMISSIONS = (
    ("users.read", "View users and their roles."),
    ("users.manage", "Create users and change role assignments."),
    ("audit.read", "View the audit trail."),
    ("platform.read", "View service health and platform information."),
)
_ROLE_PERMISSIONS = (
    ("admin", "users.read"),
    ("admin", "users.manage"),
    ("admin", "audit.read"),
    ("admin", "platform.read"),
    ("operator", "users.read"),
    ("operator", "platform.read"),
    ("approver", "platform.read"),
    ("auditor", "users.read"),
    ("auditor", "audit.read"),
    ("auditor", "platform.read"),
    ("viewer", "platform.read"),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ledgerops.users (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            email text NOT NULL,
            display_name text NOT NULL,
            password_hash text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            failed_login_count integer NOT NULL DEFAULT 0,
            locked_until timestamptz,
            last_login_at timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT pk_users PRIMARY KEY (id),
            CONSTRAINT uq_users_email UNIQUE (email),
            CONSTRAINT ck_users_email_normalised CHECK (
                email = lower(btrim(email))
                AND length(email) BETWEEN 3 AND 254
                AND position('@' IN email) > 1
            ),
            CONSTRAINT ck_users_display_name CHECK (length(btrim(display_name)) > 0),
            CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled')),
            CONSTRAINT ck_users_failed_login_count CHECK (failed_login_count >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ledgerops.roles (
            id smallint GENERATED ALWAYS AS IDENTITY,
            code text NOT NULL,
            description text NOT NULL,
            CONSTRAINT pk_roles PRIMARY KEY (id),
            CONSTRAINT uq_roles_code UNIQUE (code),
            CONSTRAINT ck_roles_code CHECK (code ~ '^[a-z][a-z_]{1,30}$')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ledgerops.permissions (
            id smallint GENERATED ALWAYS AS IDENTITY,
            code text NOT NULL,
            description text NOT NULL,
            CONSTRAINT pk_permissions PRIMARY KEY (id),
            CONSTRAINT uq_permissions_code UNIQUE (code),
            CONSTRAINT ck_permissions_code CHECK (code ~ '^[a-z][a-z_]*[.][a-z][a-z_]*$')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ledgerops.role_permissions (
            role_id smallint NOT NULL,
            permission_id smallint NOT NULL,
            CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission_id),
            CONSTRAINT fk_role_permissions_role_id_roles FOREIGN KEY (role_id)
                REFERENCES ledgerops.roles (id) ON DELETE RESTRICT,
            CONSTRAINT fk_role_permissions_permission_id_permissions FOREIGN KEY (permission_id)
                REFERENCES ledgerops.permissions (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ledgerops.user_roles (
            user_id uuid NOT NULL,
            role_id smallint NOT NULL,
            granted_at timestamptz NOT NULL,
            granted_by text NOT NULL,
            CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_id),
            CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY (user_id)
                REFERENCES ledgerops.users (id) ON DELETE RESTRICT,
            CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY (role_id)
                REFERENCES ledgerops.roles (id) ON DELETE RESTRICT,
            CONSTRAINT ck_user_roles_granted_by CHECK (
                granted_by ~ '^(user:[0-9a-f-]{36}|system:[a-z][a-z0-9_-]*)$'
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_user_roles_role_id ON ledgerops.user_roles (role_id)")
    op.execute(
        """
        CREATE TABLE ledgerops.sessions (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL,
            token_hash bytea NOT NULL,
            csrf_token text NOT NULL,
            created_at timestamptz NOT NULL,
            last_seen_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            CONSTRAINT pk_sessions PRIMARY KEY (id),
            CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash),
            CONSTRAINT fk_sessions_user_id_users FOREIGN KEY (user_id)
                REFERENCES ledgerops.users (id) ON DELETE RESTRICT,
            CONSTRAINT ck_sessions_token_hash_length CHECK (octet_length(token_hash) = 32),
            CONSTRAINT ck_sessions_csrf_token_length CHECK (length(csrf_token) >= 32),
            CONSTRAINT ck_sessions_expires_after_created CHECK (expires_at > created_at),
            CONSTRAINT ck_sessions_revoked_after_created CHECK (
                revoked_at IS NULL OR revoked_at >= created_at
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_sessions_user_id_active ON ledgerops.sessions (user_id) "
        "WHERE revoked_at IS NULL"
    )
    op.execute(
        """
        CREATE TABLE ledgerops.audit_events (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            occurred_at timestamptz NOT NULL,
            actor_principal text NOT NULL,
            actor_user_id uuid,
            action text NOT NULL,
            outcome text NOT NULL,
            target_type text,
            target_id text,
            request_id text,
            reason text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT pk_audit_events PRIMARY KEY (id),
            CONSTRAINT fk_audit_events_actor_user_id_users FOREIGN KEY (actor_user_id)
                REFERENCES ledgerops.users (id) ON DELETE RESTRICT,
            CONSTRAINT ck_audit_events_action CHECK (
                action ~ '^[a-z][a-z0-9_]*([.][a-z][a-z0-9_]*)+$'
            ),
            CONSTRAINT ck_audit_events_outcome CHECK (outcome IN ('success', 'failure', 'denied')),
            CONSTRAINT ck_audit_events_actor CHECK (
                (actor_user_id IS NOT NULL AND actor_principal = 'user:' || actor_user_id::text)
                OR (
                    actor_user_id IS NULL
                    AND (
                        actor_principal = 'anonymous'
                        OR actor_principal ~ '^system:[a-z][a-z0-9_-]*$'
                    )
                )
            ),
            CONSTRAINT ck_audit_events_metadata_is_object CHECK (jsonb_typeof(metadata) = 'object')
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_audit_events_occurred_at ON ledgerops.audit_events (occurred_at DESC, id)"
    )
    op.execute(
        "CREATE INDEX ix_audit_events_actor_user_id ON ledgerops.audit_events "
        "(actor_user_id, occurred_at DESC) WHERE actor_user_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_audit_events_action ON ledgerops.audit_events (action, occurred_at DESC)"
    )
    op.execute("CREATE INDEX ix_audit_events_request_id ON ledgerops.audit_events (request_id)")

    # Append-only enforcement. The trigger is statement-level so it fires even for statements
    # that match no rows: "UPDATE ... WHERE false" must not silently succeed.
    op.execute(
        """
        CREATE FUNCTION ledgerops.audit_events_reject_change() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only: % is not permitted', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE ON ledgerops.audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION ledgerops.audit_events_reject_change()
        """
    )

    # Privileges. ADR-0008: default DML grants must be overridden for protected tables.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON ledgerops.audit_events FROM {_RUNTIME}")
    op.execute(f"REVOKE DELETE ON ledgerops.users FROM {_RUNTIME}")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON "
        f"ledgerops.roles, ledgerops.permissions, ledgerops.role_permissions FROM {_RUNTIME}"
    )

    # Frozen seed data, inserted with bound parameters.
    bind = op.get_bind()
    for code, description in _ROLES:
        bind.execute(
            sa.text("INSERT INTO ledgerops.roles (code, description) VALUES (:c, :d)"),
            {"c": code, "d": description},
        )
    for code, description in _PERMISSIONS:
        bind.execute(
            sa.text("INSERT INTO ledgerops.permissions (code, description) VALUES (:c, :d)"),
            {"c": code, "d": description},
        )
    for role_code, permission_code in _ROLE_PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO ledgerops.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM ledgerops.roles r, ledgerops.permissions p "
                "WHERE r.code = :r AND p.code = :p"
            ),
            {"r": role_code, "p": permission_code},
        )


def downgrade() -> None:
    """Destructive by design: dropping the tables discards identities, sessions and audit rows."""
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_append_only ON ledgerops.audit_events")
    op.execute("DROP FUNCTION IF EXISTS ledgerops.audit_events_reject_change()")
    op.execute("DROP TABLE ledgerops.audit_events")
    op.execute("DROP TABLE ledgerops.sessions")
    op.execute("DROP TABLE ledgerops.user_roles")
    op.execute("DROP TABLE ledgerops.role_permissions")
    op.execute("DROP TABLE ledgerops.permissions")
    op.execute("DROP TABLE ledgerops.roles")
    op.execute("DROP TABLE ledgerops.users")
