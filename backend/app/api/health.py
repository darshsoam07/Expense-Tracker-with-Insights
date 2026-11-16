"""Health endpoints. They live OUTSIDE the /api/v1 prefix on purpose: they are for the
platform (load balancer, container runtime), not part of the versioned application API.

  /health/live   Is the process running and able to answer? Never depends on anything else,
                 so a failing dependency cannot cause a restart loop.
  /health/ready  Is it safe to send traffic? 200 when every readiness check passes, else 503.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.readiness import ReadinessRegistry

router = APIRouter(tags=["health"], include_in_schema=False)

_NO_STORE = {"Cache-Control": "no-store"}


@router.get("/health/live")
async def live() -> JSONResponse:
    return JSONResponse({"status": "alive"}, headers=_NO_STORE)


@router.get("/health/ready")
def ready(request: Request) -> JSONResponse:
    # Plain `def` (not async): FastAPI runs it in a worker thread, so future blocking checks
    # (the PR 3 database check) will not stall the event loop.
    registry: ReadinessRegistry = request.app.state.readiness
    results = registry.run()
    all_ok = all(results.values())
    body = {
        "status": "ready" if all_ok else "not_ready",
        "checks": {name: "ok" if passed else "fail" for name, passed in results.items()},
    }
    return JSONResponse(body, status_code=200 if all_ok else 503, headers=_NO_STORE)
