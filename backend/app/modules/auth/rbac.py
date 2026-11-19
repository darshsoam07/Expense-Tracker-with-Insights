"""Effective permissions, resolved from user_roles and role_permissions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.tables import permissions, role_permissions, roles, user_roles
from app.modules.auth.policy import ROLE_PERMISSIONS


def roles_for_user(db: Session, user_id: UUID) -> list[str]:
    rows = db.execute(
        select(roles.c.code)
        .join(user_roles, user_roles.c.role_id == roles.c.id)
        .where(user_roles.c.user_id == user_id)
        .order_by(roles.c.code)
    ).scalars()
    return list(rows)


def effective_permissions(db: Session, user_id: UUID) -> frozenset[str]:
    rows = db.execute(
        select(permissions.c.code)
        .join(role_permissions, role_permissions.c.permission_id == permissions.c.id)
        .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
        .where(user_roles.c.user_id == user_id)
        .distinct()
    ).scalars()
    return frozenset(rows)


def rbac_drift(db: Session) -> list[str]:
    """Differences between the database seed and policy.py. An empty list means they agree."""
    expected = {
        (role.value, permission.value)
        for role, granted in ROLE_PERMISSIONS.items()
        for permission in granted
    }
    actual = {
        (str(role), str(permission))
        for role, permission in db.execute(
            select(roles.c.code, permissions.c.code)
            .join(role_permissions, role_permissions.c.role_id == roles.c.id)
            .join(permissions, permissions.c.id == role_permissions.c.permission_id)
        )
    }
    known_roles = set(db.execute(select(roles.c.code)).scalars())
    drift = [f"missing in database: {role}/{perm}" for role, perm in sorted(expected - actual)]
    drift += [f"unexpected in database: {role}/{perm}" for role, perm in sorted(actual - expected)]
    drift += [
        f"role missing in database: {role.value}"
        for role in ROLE_PERMISSIONS
        if role.value not in known_roles
    ]
    return drift
