"""The permission catalogue and the standard roles, as code.

Migration 0002 seeds the same data into the database (frozen, not imported from here).
`rbac.rbac_drift()` and a test compare the two, so they cannot diverge unnoticed. Permissions
are added together with the feature that uses them, through a new migration.
"""

from enum import StrEnum


class Permission(StrEnum):
    ACCOUNTS_READ = "accounts.read"
    LEDGER_READ = "ledger.read"
    TRANSFERS_CREATE = "transfers.create"
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


# Every grant is listed explicitly. Nothing is inherited or implied, and a permission added
# later reaches no role until a migration and this table both grant it (a test enforces this).
# Least privilege for PR 4a, when only these four permissions exist:
#   * user administration (users.read, users.manage) is admin-only;
#   * the audit trail (audit.read) is for admin and auditor;
#   * platform.read (service health, non-sensitive) is the baseline every role holds;
#   * operator and approver gain their working permissions with the features that need them
#     (transfers and approvals arrive in PR 6 and PR 7a, each through its own migration).
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        {
            Permission.ACCOUNTS_READ,
            Permission.LEDGER_READ,
            Permission.TRANSFERS_CREATE,
            Permission.USERS_READ,
            Permission.USERS_MANAGE,
            Permission.AUDIT_READ,
            Permission.PLATFORM_READ,
        }
    ),
    Role.OPERATOR: frozenset(
        {
            Permission.PLATFORM_READ,
            Permission.ACCOUNTS_READ,
            Permission.LEDGER_READ,
            Permission.TRANSFERS_CREATE,
        }
    ),
    Role.APPROVER: frozenset({Permission.PLATFORM_READ}),
    Role.AUDITOR: frozenset(
        {
            Permission.AUDIT_READ,
            Permission.PLATFORM_READ,
            Permission.ACCOUNTS_READ,
            Permission.LEDGER_READ,
        }
    ),
    Role.VIEWER: frozenset({Permission.PLATFORM_READ}),
}


def as_permission(code: str) -> Permission:
    """Resolve a permission code or raise, so a typo in a route declaration fails at import."""
    try:
        return Permission(code)
    except ValueError:
        raise ValueError(f"unknown permission {code!r}") from None
