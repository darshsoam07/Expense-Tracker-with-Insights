"""Application factory.

Run locally (from the backend/ folder):
    uvicorn app.main:create_app --factory --reload

`--factory` makes uvicorn call create_app() itself, so importing this module never reads
configuration or starts anything (important for tests and tooling).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import __version__
from app.api import API_V1_PREFIX
from app.api.accounts import router as accounts_router
from app.api.approvals import router as approvals_router
from app.api.auth import me_router
from app.api.auth import router as auth_router
from app.api.deps import enforce_csrf
from app.api.health import router as health_router
from app.api.holds import router as holds_router
from app.api.payments import router as payments_router
from app.api.settlements import router as settlements_router
from app.api.transfers import router as transfers_router
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, load_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.readiness import ReadinessRegistry
from app.core.request_context import RequestContextMiddleware
from app.db import database_ready, make_engine

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None, *, clock: Clock | None = None) -> FastAPI:
    """Build an application. Raises ConfigurationError if the settings are missing or insecure.

    `clock` lets tests control time; production uses the system clock.
    """
    if settings is None:
        settings = load_settings()
    configure_logging(settings.log_level)
    readiness = ReadinessRegistry()
    engine = (
        make_engine(settings.database_url.get_secret_value()) if settings.database_url else None
    )
    readiness.register("database", lambda: database_ready(engine) if engine is not None else False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "app.startup",
            extra={"app_env": settings.app_env, "log_level": settings.log_level},
        )
        readiness.mark_started()
        try:
            yield
        finally:
            readiness.mark_stopping()
            if engine is not None:
                engine.dispose()
            # Readiness is disabled before disposing the pool.

            logger.info("app.shutdown")

    docs_enabled = settings.enable_docs
    app = FastAPI(
        title="LedgerOps API",
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        # Docs sit under the version prefix so a reverse proxy only needs to route /api/.
        docs_url=f"{API_V1_PREFIX}/docs" if docs_enabled else None,
        openapi_url=f"{API_V1_PREFIX}/openapi.json" if docs_enabled else None,
        redoc_url=None,
        # CSRF protection applies to every state-changing route, including future ones.
        dependencies=[Depends(enforce_csrf)],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.clock = clock or SystemClock()
    app.state.readiness = readiness

    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(holds_router)
    app.include_router(payments_router)
    app.include_router(settlements_router)
    app.include_router(accounts_router)
    app.include_router(approvals_router)
    app.include_router(transfers_router)
    return app
