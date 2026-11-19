"""Create the first privileged user from the command line.

There is deliberately no public registration endpoint in PR 4a. Privileged accounts are
created here, with the runtime database role, and every creation is audited under the
`system:bootstrap-cli` principal.

    python -m app.modules.auth.bootstrap --email admin@example.com --name "Ada Admin" --role admin

The password is read from LEDGEROPS_BOOTSTRAP_PASSWORD or prompted for. It is never accepted
as a command-line argument, because arguments appear in process listings and shell history.
"""

import argparse
import getpass
import os
import sys
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock, SystemClock
from app.core.errors import AppError
from app.core.principal import Principal
from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password
from app.db import make_engine, open_session
from app.db.tables import roles, user_roles, users
from app.modules.audit import AuditWriter
from app.modules.auth.service import normalise_email

BOOTSTRAP_PRINCIPAL = Principal.system("bootstrap-cli")


def create_user(
    db: Session,
    clock: Clock,
    *,
    email: str,
    display_name: str,
    password: str,
    role_codes: list[str],
) -> UUID:
    """Insert a user with roles and audit rows in one transaction, then commit."""
    email = normalise_email(email)
    display_name = display_name.strip()
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise AppError(
            422,
            "weak_password",
            f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters.",
        )
    if not display_name:
        raise AppError(422, "validation_error", "A display name is required.")
    # list() first: a CursorResult has keys(), so dict() would treat it as a mapping.
    role_ids = dict(
        list(
            db.execute(
                select(roles.c.code, roles.c.id).where(roles.c.code.in_(role_codes))
            ).tuples()
        )
    )
    unknown = sorted(set(role_codes) - set(role_ids))
    if unknown:
        raise AppError(422, "unknown_role", f"Unknown role(s): {', '.join(unknown)}.")

    now = clock.now()
    audit = AuditWriter(clock)
    try:
        user_id: UUID = db.execute(
            insert(users)
            .values(
                email=email,
                display_name=display_name,
                password_hash=hash_password(password),
                created_at=now,
                updated_at=now,
            )
            .returning(users.c.id)
        ).scalar_one()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "email_in_use", "A user with this email already exists.") from None

    audit.record(
        db,
        principal=BOOTSTRAP_PRINCIPAL,
        action="users.created",
        target_type="user",
        target_id=str(user_id),
        metadata={"roles": sorted(role_ids)},
    )
    for code, role_id in sorted(role_ids.items()):
        db.execute(
            insert(user_roles).values(
                user_id=user_id,
                role_id=role_id,
                granted_at=now,
                granted_by=BOOTSTRAP_PRINCIPAL.value,
            )
        )
        audit.record(
            db,
            principal=BOOTSTRAP_PRINCIPAL,
            action="users.role_granted",
            target_type="user",
            target_id=str(user_id),
            metadata={"role": code},
        )
    db.commit()
    return user_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a LedgerOps user (uses DATABASE_URL).")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", action="append", required=True, dest="roles")
    args = parser.parse_args(argv)

    password = os.environ.get("LEDGEROPS_BOOTSTRAP_PASSWORD") or getpass.getpass("Password: ")
    engine = make_engine(os.environ["DATABASE_URL"])
    try:
        with open_session(engine) as db:
            user_id = create_user(
                db,
                SystemClock(),
                email=args.email,
                display_name=args.name,
                password=password,
                role_codes=args.roles,
            )
    except AppError as error:
        print(f"error: {error.message}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"Created user {user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
