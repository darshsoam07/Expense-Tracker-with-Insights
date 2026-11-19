"""The permission catalogue and the standard roles, as code.

Migration 0002 seeds the same data into the database (frozen, not imported from here).
`rbac.rbac_drift()` and a test compare the two, so they cannot diverge unnoticed. Permissions
are added together with the feature that uses them, through a new migration.
"""

from enum import StrEnum


class Permission(StrEnum):
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    AUDIT_READ = "audit.read"
    PLATFORM_READ = "platform.read"


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    VIEWER = "viewer"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.OPERATOR: frozenset({Permission.USERS_READ, Permission.PLATFORM_READ}),
    Role.APPROVER: frozenset({Permission.PLATFORM_READ}),
    Role.AUDITOR: frozenset(
        {Permission.USERS_READ, Permission.AUDIT_READ, Permission.PLATFORM_READ}
    ),
    Role.VIEWER: frozenset({Permission.PLATFORM_READ}),
}


def as_permission(code: str) -> Permission:
    """Resolve a permission code or raise, so a typo in a route declaration fails at import."""
    try:
        return Permission(code)
    except ValueError:
        raise ValueError(f"unknown permission {code!r}") from None
