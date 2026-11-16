import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.helpers import make_settings


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    """create_app()/configure_logging() change global logging; undo that after every test."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    uvicorn_state = {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).propagate)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    }
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    for name, (handlers, propagate) in uvicorn_state.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.propagate = propagate


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client with startup/shutdown running. Server errors become 500 responses, not raises."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
