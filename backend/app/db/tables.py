"""SQLAlchemy Core table definitions for the identity, RBAC, session and audit tables.

The Alembic migrations are the schema source of truth. These definitions exist so services
can build typed queries; an integration test asserts they match the migrated database, so
the two cannot silently drift apart.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
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
