"""Who performed an action. Audit rows always carry a principal, never a null actor."""

import re
from dataclasses import dataclass
from uuid import UUID

_SYSTEM_NAME = re.compile(r"[a-z][a-z0-9_-]*")


@dataclass(frozen=True, slots=True)
class Principal:
    """`user:<uuid>`, `system:<name>` or `anonymous`."""

    value: str
    user_id: UUID | None = None

    @classmethod
    def user(cls, user_id: UUID) -> "Principal":
        return cls(f"user:{user_id}", user_id)

    @classmethod
    def system(cls, name: str) -> "Principal":
        if not _SYSTEM_NAME.fullmatch(name):
            raise ValueError("system principal names are lower-case words, digits, _ or -")
        return cls(f"system:{name}")


ANONYMOUS = Principal("anonymous")
