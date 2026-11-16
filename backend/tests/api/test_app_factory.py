import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import ConfigurationError
from app.main import create_app
from tests.helpers import STRONG_SECRET, TEST_SECRET, json_lines, make_settings


def test_docs_and_schema_live_under_the_api_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/docs").status_code == 200
    schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["info"] == {"title": "LedgerOps API", "version": __version__}


def test_default_unprefixed_doc_urls_are_not_exposed(client: TestClient) -> None:
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert client.get(path).status_code == 404


def test_docs_can_be_disabled() -> None:
    app = create_app(make_settings(enable_docs=False))
    with TestClient(app) as client:
        assert client.get("/api/v1/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 404


def test_each_app_has_its_own_state() -> None:
    first = create_app(make_settings(log_level="DEBUG"))
    second = create_app(make_settings(log_level="ERROR"))
    with TestClient(first):
        assert first.state.readiness.run() == {"app_started": True}
        assert second.state.readiness.run() == {"app_started": False}
    assert first.state.settings.log_level == "DEBUG"
    assert second.state.settings.log_level == "ERROR"


def test_explicit_settings_ignore_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "bad")  # would be rejected if it were read
    settings = make_settings()
    assert create_app(settings).state.settings is settings


def test_without_settings_the_factory_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    monkeypatch.chdir(str(tmp_path))  # a folder with no .env
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", STRONG_SECRET)
    monkeypatch.setenv("COOKIE_SECURE", "true")
    assert create_app().state.settings.app_env == "production"


def test_without_settings_an_incomplete_environment_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    monkeypatch.chdir(str(tmp_path))
    for name in ("APP_ENV", "SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigurationError, match="refusing to start"):
        create_app()


def test_lifecycle_is_logged_without_leaking_the_secret(capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(make_settings())
    with TestClient(app):
        pass
    output = capsys.readouterr().out
    assert TEST_SECRET not in output
    events = [record["event"] for record in json_lines(output)]
    assert events.index("app.startup") < events.index("app.shutdown")
    startup = next(r for r in json_lines(output) if r["event"] == "app.startup")
    assert startup["app_env"] == "test"
