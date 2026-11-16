"""Application factory.

Run locally (from the backend/ folder):
    uvicorn app.main:create_app --factory --reload

`--factory` makes uvicorn call create_app() itself, so importing this module never reads
configuration or starts anything (important for tests and tooling).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import API_V1_PREFIX
from app.api.health import router as health_router
from app.core.config import Settings, load_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.readiness import ReadinessRegistry
from app.core.request_context import RequestContextMiddleware

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application. Raises ConfigurationError if the settings are missing or insecure."""
    if settings is None:
        settings = load_settings()
    configure_logging(settings.log_level)
    readiness = ReadinessRegistry()

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
            readiness.mark_stopping()  # readiness turns 503 first, so traffic drains
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
    )
    app.state.settings = settings
    app.state.readiness = readiness

    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health_router)
    return app
