"""Foundation schema and least-privilege defaults."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("REVOKE ALL ON SCHEMA ledgerops FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA ledgerops TO ledgerops_runtime")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA ledgerops "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ledgerops_runtime"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA ledgerops "
        "GRANT USAGE, SELECT ON SEQUENCES TO ledgerops_runtime"
    )
    op.execute("GRANT SELECT ON ledgerops.alembic_version TO ledgerops_runtime")


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA ledgerops "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM ledgerops_runtime"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA ledgerops "
        "REVOKE USAGE, SELECT ON SEQUENCES FROM ledgerops_runtime"
    )
    op.execute("REVOKE SELECT ON ledgerops.alembic_version FROM ledgerops_runtime")
    op.execute("REVOKE USAGE ON SCHEMA ledgerops FROM ledgerops_runtime")
