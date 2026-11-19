"""Transfers endpoint placeholder (PR 4b).

Financial transfer processing arrives in PR 6. This endpoint exists solely to provide
an honest, authenticated 501 Not Implemented response that prevents client-side
mock posting or fake balances.
"""

from fastapi import APIRouter

from app.api import API_V1_PREFIX
from app.api.deps import CurrentSession
from app.core.errors import AppError

router = APIRouter(prefix=f"{API_V1_PREFIX}/transfers", tags=["transfers"])


@router.post("", status_code=501)
def create_transfer(_active: CurrentSession) -> None:
    """Explicitly reject transfer processing until the double-entry ledger lands in PR 6."""
    raise AppError(501, "not_implemented", "Transfers are not available yet.")
