import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import STRONG_SECRET, make_settings


@pytest.mark.parametrize(
    ("environment", "origin", "allowed"),
    [
        ("local", "http://localhost:5173", True),
        ("local", "http://example.test", False),
        ("production", "http://localhost:5173", False),
    ],
)
def test_readiness_cors(environment: str, origin: str, allowed: bool) -> None:
    settings = make_settings(app_env=environment, cookie_secure=True, secret_key=STRONG_SECRET)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)
