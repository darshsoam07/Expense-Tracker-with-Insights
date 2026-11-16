"""Application settings, loaded from environment variables (and an optional .env file).

Design rules:
  * Safe by default: APP_ENV and SECRET_KEY have NO default, so forgetting them fails loudly
    instead of silently running in a weak mode.
  * The application refuses to start on an insecure configuration.
  * Error messages never contain secret values.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Environments where weak settings are tolerated. Everything else is "strict".
RELAXED_ENVIRONMENTS: frozenset[str] = frozenset({"local", "test"})
STRICT_COOKIE_AND_DEBUG_ENVIRONMENTS: frozenset[str] = frozenset({"staging", "production"})

MIN_SECRET_LENGTH = 32
MIN_DISTINCT_CHARACTERS = 10
PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "change-this",
    "replace",
    "placeholder",
    "example",
    "default",
    "insecure",
    "dev-secret",
)
GENERATE_HINT = 'generate one with: python -c "import secrets; print(secrets.token_hex(32))"'


class ConfigurationError(Exception):
    """Raised when settings are missing or insecure. The message is safe to print."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"Invalid configuration, refusing to start:\n{lines}")


class Settings(BaseSettings):
    """All runtime configuration. Environment variable names are the upper-case field names."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Environment
    secret_key: SecretStr
    log_level: LogLevel = "INFO"
    cookie_secure: bool = True
    debug: bool = False
    enable_docs: bool = True

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _enforce_secure_configuration(self) -> "Settings":
        problems: list[str] = []
        secret = self.secret_key.get_secret_value()

        if not secret.strip():
            problems.append(f"SECRET_KEY must not be empty ({GENERATE_HINT})")
        elif self.app_env not in RELAXED_ENVIRONMENTS:
            if len(secret) < MIN_SECRET_LENGTH:
                problems.append(
                    f"SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters "
                    f"when APP_ENV={self.app_env} ({GENERATE_HINT})"
                )
            if any(marker in secret.lower() for marker in PLACEHOLDER_MARKERS):
                problems.append(
                    f"SECRET_KEY looks like a placeholder; it is not allowed "
                    f"when APP_ENV={self.app_env} ({GENERATE_HINT})"
                )
            if len(set(secret)) < MIN_DISTINCT_CHARACTERS:
                problems.append(
                    f"SECRET_KEY has too little variety to be random when "
                    f"APP_ENV={self.app_env} ({GENERATE_HINT})"
                )

        if self.app_env in STRICT_COOKIE_AND_DEBUG_ENVIRONMENTS:
            if not self.cookie_secure:
                problems.append(f"COOKIE_SECURE must be true when APP_ENV={self.app_env}")
            if self.debug:
                problems.append(f"DEBUG must be false when APP_ENV={self.app_env}")

        if problems:
            # One ValueError carrying every problem; load_settings() splits it back into lines.
            raise ValueError("\n".join(problems))
        return self


def _sanitised_problems(error: ValidationError) -> list[str]:
    """Turn a pydantic error into safe messages. Never includes the offending input value."""
    problems: list[str] = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        message = item["msg"].removeprefix("Value error, ")
        location = ".".join(str(part) for part in item["loc"]).upper()
        if location:
            problems.append(f"{location}: {message}")
        else:
            problems.extend(line for line in message.splitlines() if line)
    return problems


def load_settings(env_file: str | Path | None = ".env", **overrides: Any) -> Settings:
    """Load and validate settings, or raise ConfigurationError.

    `env_file=None` disables .env reading (used by tests so a developer's real .env
    cannot change test results). Keyword overrides take precedence over the environment.
    """
    try:
        return Settings(_env_file=env_file, **overrides)
    except ValidationError as error:
        # "from None" drops the original error, whose traceback could contain input values.
        raise ConfigurationError(_sanitised_problems(error)) from None
