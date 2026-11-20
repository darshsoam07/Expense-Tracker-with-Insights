"""Explicit approval reviewer grants."""

from alembic import op

revision = "0006_approval_grants"
down_revision = "0005_transfer_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        SET LOCAL search_path=ledgerops,pg_catalog;
        INSERT INTO permissions(code,description) VALUES
        ('approvals.read','Read scoped approval requests'),('approvals.decide','Review transfers');
        INSERT INTO role_permissions(role_id,permission_id)
        SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE
        (p.code='approvals.read' AND r.code IN ('admin','operator','auditor','approver')) OR
        (p.code='approvals.decide' AND r.code IN ('admin','approver'));
    """)


def downgrade() -> None:
    op.execute("""
        SET LOCAL search_path=ledgerops,pg_catalog;
        DELETE FROM role_permissions WHERE permission_id IN
        (SELECT id FROM permissions WHERE code IN ('approvals.read','approvals.decide'));
        DELETE FROM permissions WHERE code IN ('approvals.read','approvals.decide');
    """)
