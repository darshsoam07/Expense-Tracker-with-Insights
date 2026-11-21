"""SQLAlchemy Core table definitions for the identity, RBAC, session and audit tables.

The Alembic migrations are the schema source of truth. These definitions exist so services
can build typed queries; an integration test asserts they match the migrated database, so
the two cannot silently drift apart.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

SCHEMA = "ledgerops"
metadata = MetaData(schema=SCHEMA)

_UUID_DEFAULT = text("gen_random_uuid()")

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=_UUID_DEFAULT),
    Column("email", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("failed_login_count", Integer, nullable=False, server_default=text("0")),
    Column("locked_until", DateTime(timezone=True)),
    Column("last_login_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

roles = Table(
    "roles",
    metadata,
    Column("id", SmallInteger, primary_key=True, autoincrement=True),
    Column("code", Text, nullable=False),
    Column("description", Text, nullable=False),
)

permissions = Table(
    "permissions",
    metadata,
    Column("id", SmallInteger, primary_key=True, autoincrement=True),
    Column("code", Text, nullable=False),
    Column("description", Text, nullable=False),
)

role_permissions = Table(
    "role_permissions",
    metadata,
    Column("role_id", SmallInteger, ForeignKey(roles.c.id), primary_key=True),
    Column("permission_id", SmallInteger, ForeignKey(permissions.c.id), primary_key=True),
)

user_roles = Table(
    "user_roles",
    metadata,
    Column("user_id", Uuid, ForeignKey(users.c.id), primary_key=True),
    Column("role_id", SmallInteger, ForeignKey(roles.c.id), primary_key=True),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("granted_by", Text, nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=_UUID_DEFAULT),
    Column("user_id", Uuid, ForeignKey(users.c.id), nullable=False),
    Column("token_hash", LargeBinary, nullable=False),
    Column("csrf_token", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=_UUID_DEFAULT),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("actor_principal", Text, nullable=False),
    Column("actor_user_id", Uuid, ForeignKey(users.c.id)),
    Column("action", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("target_type", Text),
    Column("target_id", Text),
    Column("request_id", Text),
    Column("reason", Text),
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)

currencies = Table(
    "currencies",
    metadata,
    Column("code", Text, primary_key=True),
)

customers = Table(
    "customers",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

customer_members = Table(
    "customer_members",
    metadata,
    Column("customer_id", Uuid, primary_key=True),
    Column("user_id", Uuid, primary_key=True),
    Column("role", Text, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

chart_accounts = Table(
    "chart_accounts",
    metadata,
    Column("code", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("classification", Text, nullable=False),
    Column("normal_side", Text, nullable=False),
    Column("postable", Boolean, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ledger_accounts = Table(
    "ledger_accounts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("code", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("active", Boolean, nullable=False),
)

accounts = Table(
    "accounts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("reference", Uuid, nullable=False),
    Column("customer_id", Uuid, nullable=False),
    Column("account_type", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("ledger_id", Uuid, nullable=False),
    Column("code", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

account_balances = Table(
    "account_balances",
    metadata,
    Column("lock_marker", Boolean, nullable=False),
    Column("ledger_id", Uuid, primary_key=True),
    Column("currency", Text, nullable=False),
    Column("ledger_balance", Numeric(18, 2), nullable=False),
    Column("held_amount", Numeric(18, 2), nullable=False),
    Column("available_balance", Numeric(18, 2)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

journal_entries = Table(
    "journal_entries",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("reference", Uuid, nullable=False),
    Column("description", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("actor_id", Uuid),
    Column("actor_principal", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("posted_at", DateTime(timezone=True)),
)

journal_postings = Table(
    "journal_postings",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("journal_id", Uuid, nullable=False),
    Column("ledger_id", Uuid, nullable=False),
    Column("currency", Text, nullable=False),
    Column("debit", Numeric(18, 2), nullable=False),
    Column("credit", Numeric(18, 2), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

transfers = Table(
    "transfers",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("actor_id", Uuid, nullable=False),
    Column("operation", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("payload_hash", Text, nullable=False),
    Column("source_id", Uuid, nullable=False),
    Column("destination_id", Uuid, nullable=False),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("currency", Text, nullable=False),
    Column("journal_id", Uuid, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

account_holds = Table(
    "account_holds",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("account_id", Uuid, nullable=False),
    Column("currency", Text, nullable=False),
    Column("original_amount", Numeric(18, 2), nullable=False),
    Column("remaining", Numeric(18, 2), nullable=False),
    Column("status", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("business_reference", Text),
    Column("creator", Uuid, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
)

hold_events = Table(
    "hold_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("hold_id", Uuid, nullable=False),
    Column("account_id", Uuid, nullable=False),
    Column("kind", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("remaining", Numeric(18, 2), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("actor", Uuid),
    Column("command", Text, nullable=False),
    Column("key", Text),
    Column("digest", Text),
    Column("reason", Text),
    Column("business_reference", Text),
    Column("expires_at", DateTime(timezone=True)),
    Column("journal_id", Uuid),
)

approval_policies = Table(
    "approval_policies",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("customer_id", Uuid, nullable=False),
    Column("name", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("minimum", Numeric(18, 2), nullable=False),
    Column("maximum", Numeric(18, 2)),
    Column("required_count", Integer, nullable=False),
    Column("ttl_seconds", Integer),
    Column("active", Boolean, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("actor", Uuid, nullable=False),
)

approval_requests = Table(
    "approval_requests",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("subject_type", Text, nullable=False),
    Column("subject_id", Uuid, nullable=False),
    Column("maker", Uuid, nullable=False),
    Column("customer_id", Uuid, nullable=False),
    Column("policy_id", Uuid, nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("source_id", Uuid, nullable=False),
    Column("destination_id", Uuid),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("currency", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("payload_hash", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("hold_id", Uuid, nullable=False),
    Column("original_hold_id", Uuid),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("status", Text, nullable=False),
    Column("completed_at", DateTime(timezone=True)),
)

approval_decisions = Table(
    "approval_decisions",
    metadata,
    Column("request_id", Uuid, primary_key=True),
    Column("maker", Uuid, nullable=False),
    Column("actor", Uuid, primary_key=True),
    Column("decision", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
)

approval_events = Table(
    "approval_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("request_id", Uuid, nullable=False),
    Column("kind", Text, nullable=False),
    Column("actor", Uuid),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", Text),
)

payment_instructions = Table(
    "payment_instructions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("customer_id", Uuid, nullable=False),
    Column("source_id", Uuid, nullable=False),
    Column("actor_id", Uuid, nullable=False),
    Column("customer_reference", Text, nullable=False),
    Column("beneficiary_name", Text, nullable=False),
    Column("destination_reference", Text, nullable=False),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("currency", Text, nullable=False),
    Column("rail", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("hold_id", Uuid, nullable=False),
    Column("approval_id", Uuid),
    Column("idempotency_key", Text, nullable=False),
    Column("payload_hash", Text, nullable=False),
    Column("provider_reference", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

payment_events = Table(
    "payment_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("payment_id", Uuid, nullable=False),
    Column("kind", Text, nullable=False),
    Column("actor", Uuid),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("provider_reference", Text),
    Column("detail", Text),
    Column("correlation_id", Text),
)
