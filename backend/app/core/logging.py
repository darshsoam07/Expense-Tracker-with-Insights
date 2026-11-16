"""Structured JSON logging with request IDs and redaction of sensitive fields.

Uses only the Python standard library (see ADR-0007). One JSON object per line on stdout,
which is what container platforms (Docker, ECS/CloudWatch) expect.

Rule for developers: never put secrets or personal data in the log *message* text.
Redaction below protects structured `extra=` fields, not free text.
"""

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# The ID of the request being handled. Set by RequestContextMiddleware.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "authorization",
    "api_key",
    "apikey",
    "csrf",
    "session",
)
_CORE_KEYS = ("timestamp", "level", "logger", "event")
_HANDLER_MARKER = "_ledgerops_json_handler"
# Attributes every LogRecord has; anything else was passed via `extra=`.
# "color_message" is uvicorn's terminal-coloured duplicate of the message; it is just noise here.
_STANDARD_ATTRIBUTES = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
    | {"message", "asctime", "color_message"}
)


def redact(value: Any, key: str | None = None) -> Any:
    """Return a copy of `value` with the contents of sensitive keys replaced."""
    if key is not None and any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Format a log record as one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        request_id = record.__dict__.get("request_id") or request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRIBUTES or key == "request_id":
                continue
            payload[f"extra_{key}" if key in _CORE_KEYS else key] = redact(value, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _StdoutHandler(logging.Handler):
    """Writes to whatever sys.stdout is *at emit time* (keeps test output capture working)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def configure_logging(level: str = "INFO") -> None:
    """Route all logging to JSON on stdout. Safe to call more than once."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
    handler = _StdoutHandler()
    handler.setFormatter(JsonFormatter())
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    root.setLevel(level)

    # Send uvicorn's own messages through our JSON handler, and silence its plain-text
    # access log because RequestContextMiddleware writes a structured one instead.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
