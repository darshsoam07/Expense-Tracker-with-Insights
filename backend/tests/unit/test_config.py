import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import PLACEHOLDER_MARKERS, ConfigurationError, Settings, load_settings
from tests.helpers import STRONG_SECRET, TEST_SECRET, make_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
SETTING_NAMES = ("APP_ENV", "SECRET_KEY", "LOG_LEVEL", "COOKIE_SECURE", "DEBUG", "ENABLE_DOCS")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure the developer's own shell variables cannot change these tests."""
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)


def load(**values: object) -> Settings:
    return load_settings(env_file=None, **values)


def problems_of(**values: object) -> list[str]:
    with pytest.raises(ConfigurationError) as caught:
        load(**values)
    return caught.value.problems


# ------------------------------------------------------------------ valid configurations


def test_valid_local_config_loads_with_safe_defaults() -> None:
    settings = load(app_env="local", secret_key="local-dev-key")
    assert settings.app_env == "local"
    assert settings.log_level == "INFO"
    assert settings.cookie_secure is True  # secure unless explicitly turned off
    assert settings.debug is False
    assert settings.enable_docs is True


def test_valid_production_config_loads() -> None:
    settings = load(app_env="production", secret_key=STRONG_SECRET, cookie_secure=True)
    assert settings.app_env == "production"


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("LOG_LEVEL", "debug")  # lower case is accepted and normalised
    settings = load_settings(env_file=None)
    assert settings.log_level == "DEBUG"


def test_reads_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"APP_ENV=local\nSECRET_KEY={TEST_SECRET}\nENABLE_DOCS=false\n")
    settings = load_settings(env_file=env_file)
    assert settings.enable_docs is False


# ------------------------------------------------------------------ missing / invalid values


def test_missing_secret_key_is_rejected() -> None:
    assert "SECRET_KEY: Field required" in problems_of(app_env="local")


def test_missing_app_env_is_rejected() -> None:
    assert "APP_ENV: Field required" in problems_of(secret_key=TEST_SECRET)


def test_unknown_app_env_is_rejected() -> None:
    problems = problems_of(app_env="prod", secret_key=TEST_SECRET)
    assert any(p.startswith("APP_ENV:") for p in problems)


def test_invalid_log_level_is_rejected() -> None:
    problems = problems_of(app_env="test", secret_key=TEST_SECRET, log_level="LOUD")
    assert any(p.startswith("LOG_LEVEL:") for p in problems)


@pytest.mark.parametrize("env", ["local", "test", "staging", "production"])
def test_blank_secret_is_rejected_in_every_environment(env: str) -> None:
    problems = problems_of(app_env=env, secret_key="   ", cookie_secure=True)
    assert any("must not be empty" in p for p in problems)


# ------------------------------------------------------------------ secret strength


@pytest.mark.parametrize("env", ["staging", "production"])
def test_short_secret_is_rejected_outside_local_and_test(env: str) -> None:
    problems = problems_of(app_env=env, secret_key="Ab1-short-but-varied", cookie_secure=True)
    assert any("at least 32 characters" in p for p in problems)


@pytest.mark.parametrize("env", ["local", "test"])
def test_short_secret_is_tolerated_in_local_and_test(env: str) -> None:
    assert load(app_env=env, secret_key="short").app_env == env


@pytest.mark.parametrize("marker", PLACEHOLDER_MARKERS)
def test_placeholder_secrets_are_rejected_in_production(marker: str) -> None:
    secret = f"aB3dE5gH7jK9mN2pQ4rS6tU8vW0xYzA-{marker}"
    problems = problems_of(app_env="production", secret_key=secret, cookie_secure=True)
    assert any("placeholder" in p for p in problems)


def test_low_variety_secret_is_rejected_in_production() -> None:
    problems = problems_of(app_env="production", secret_key="a" * 40, cookie_secure=True)
    assert any("too little variety" in p for p in problems)


# ------------------------------------------------------------------ cookie and debug rules


@pytest.mark.parametrize("env", ["staging", "production"])
def test_insecure_cookies_are_rejected_in_staging_and_production(env: str) -> None:
    problems = problems_of(app_env=env, secret_key=STRONG_SECRET, cookie_secure=False)
    assert problems == [f"COOKIE_SECURE must be true when APP_ENV={env}"]


@pytest.mark.parametrize("env", ["staging", "production"])
def test_debug_is_rejected_in_staging_and_production(env: str) -> None:
    problems = problems_of(app_env=env, secret_key=STRONG_SECRET, cookie_secure=True, debug=True)
    assert problems == [f"DEBUG must be false when APP_ENV={env}"]


@pytest.mark.parametrize("env", ["local", "test"])
def test_insecure_cookies_and_debug_are_allowed_locally(env: str) -> None:
    settings = load(app_env=env, secret_key=TEST_SECRET, cookie_secure=False, debug=True)
    assert settings.debug is True


def test_all_problems_are_reported_together() -> None:
    problems = problems_of(
        app_env="production", secret_key="short", cookie_secure=False, debug=True
    )
    assert len(problems) >= 4  # short, low variety, cookies, debug


# ------------------------------------------------------------------ secrets never leak


def test_error_message_never_contains_the_secret() -> None:
    secret = "my-private-key-value"
    with pytest.raises(ConfigurationError) as caught:
        load(app_env="production", secret_key=secret, cookie_secure=True)
    assert secret not in str(caught.value)
    assert all(secret not in problem for problem in caught.value.problems)
    assert caught.value.__cause__ is None  # the raw pydantic error (with input) is dropped


def test_settings_repr_hides_the_secret() -> None:
    settings = make_settings(secret_key="visible-if-leaked-0123456789abcdef")
    assert "visible-if-leaked" not in repr(settings)
    assert "visible-if-leaked" not in str(settings)
    assert str(settings.secret_key) == "**********"


# ------------------------------------------------------------------ .env.example stays honest


def example_lines() -> list[str]:
    text = (BACKEND_DIR / ".env.example").read_text()
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def test_env_example_loads_for_local_development() -> None:
    settings = load_settings(env_file=BACKEND_DIR / ".env.example")
    assert settings.app_env == "local"


def test_env_example_documents_every_setting() -> None:
    documented = {line.split("=", 1)[0] for line in example_lines()}
    assert documented == {name.upper() for name in Settings.model_fields}


def test_env_example_secret_is_rejected_if_copied_to_production() -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_settings(
            env_file=BACKEND_DIR / ".env.example", app_env="production", cookie_secure=True
        )
    assert any("placeholder" in problem for problem in caught.value.problems)


# ------------------------------------------------------------------ a real failed start-up


def run_create_app(env_overrides: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Start the app factory in a fresh interpreter, in a folder with no .env file."""
    env = {key: value for key, value in os.environ.items() if key not in SETTING_NAMES}
    env.update(env_overrides)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    return subprocess.run(
        [sys.executable, "-c", "from app.main import create_app; create_app()"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_startup_fails_clearly_when_secret_key_is_missing(tmp_path: Path) -> None:
    result = run_create_app({"APP_ENV": "local"}, tmp_path)
    assert result.returncode != 0
    assert "refusing to start" in result.stderr
    assert "SECRET_KEY" in result.stderr


def test_startup_fails_on_placeholder_secret_without_printing_it(tmp_path: Path) -> None:
    secret = "change-me-this-exact-text-must-never-be-printed-123456"
    result = run_create_app(
        {"APP_ENV": "production", "SECRET_KEY": secret, "COOKIE_SECURE": "true"}, tmp_path
    )
    assert result.returncode != 0
    assert "placeholder" in result.stderr
    assert secret not in result.stdout + result.stderr


def test_startup_succeeds_with_valid_config(tmp_path: Path) -> None:
    result = run_create_app({"APP_ENV": "test", "SECRET_KEY": TEST_SECRET}, tmp_path)
    assert result.returncode == 0, result.stderr
