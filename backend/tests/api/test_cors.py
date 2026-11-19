"""Tests verifying the same-origin application contract (PR 4b).

The temporary local CORS allowance has been removed in favour of the Vite development proxy
and reverse-proxy production architecture. The API never emits Access-Control-Allow-Origin
headers to cross-origin browsers.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import STRONG_SECRET, make_settings


@pytest.mark.parametrize(
    ("environment", "origin"),
    [
        ("local", "http://localhost:5173"),
        ("local", "http://example.test"),
        ("production", "http://localhost:5173"),
        ("production", "https://malicious.origin.test"),
    ],
)
def test_no_cors_headers_emitted(environment: str, origin: str) -> None:
    """Same-origin reverse proxy contract: no cross-origin browser access allowed."""
    settings = make_settings(app_env=environment, cookie_secure=True, secret_key=STRONG_SECRET)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready", headers={"Origin": origin})
    # Readiness returns 503 because database is unconfigured in this unit test
    assert response.status_code == 503
    assert "access-control-allow-origin" not in response.headers
    assert response.headers.get("access-control-allow-origin") is None
