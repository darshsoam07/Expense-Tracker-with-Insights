import logging
import sys

import pytest

from app.core.logging import (
    REDACTED,
    _StdoutHandler,
    configure_logging,
    redact,
    request_id_var,
)
from tests.helpers import json_lines

logger = logging.getLogger("test.logger")


def test_each_record_is_one_json_object_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logger.info("first", extra={"amount_count": 1})
    logger.warning("second")
    first, second = json_lines(capsys.readouterr().out)
    assert first["event"] == "first"
    assert first["level"] == "INFO"
    assert first["logger"] == "test.logger"
    assert first["amount_count"] == 1
    assert first["timestamp"].endswith("+00:00")
    assert second["level"] == "WARNING"


def test_request_id_from_context_is_included(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    token = request_id_var.set("req-context-123")
    try:
        logger.info("inside request")
    finally:
        request_id_var.reset(token)
    logger.info("outside request")
    inside, outside = json_lines(capsys.readouterr().out)
    assert inside["request_id"] == "req-context-123"
    assert "request_id" not in outside


def test_explicit_request_id_wins_over_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    token = request_id_var.set("from-context-1")
    try:
        logger.info("x", extra={"request_id": "explicit-id-99"})
    finally:
        request_id_var.reset(token)
    assert json_lines(capsys.readouterr().out)[0]["request_id"] == "explicit-id-99"


def test_sensitive_fields_are_redacted_everywhere(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logger.info(
        "login attempt",
        extra={
            "password": "hunter2",
            "user": {"Authorization": "Bearer abc.def.ghi", "name": "Asha"},
            "headers": [{"set-cookie": "session=topsecretcookie"}],
            "csrf_token": "csrf-value-xyz",
        },
    )
    raw = capsys.readouterr().out
    for leaked in ("hunter2", "abc.def.ghi", "topsecretcookie", "csrf-value-xyz"):
        assert leaked not in raw
    record = json_lines(raw)[0]
    assert record["password"] == REDACTED
    assert record["user"] == {"Authorization": REDACTED, "name": "Asha"}  # harmless data kept


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "PASSWORD",
        "user_password",
        "Set-Cookie",
        "session_id",
        "API_KEY",
        "x-csrf-token",
        "Authorization",
        "client_secret",
        "refresh_token",
    ],
)
def test_redact_matches_sensitive_key_names(key: str) -> None:
    assert redact("value", key) == REDACTED


def test_redact_keeps_harmless_values_and_converts_tuples() -> None:
    assert redact("12.50", "amount") == "12.50"
    assert redact(("a", {"token": "x"})) == ["a", {"token": REDACTED}]


def test_exceptions_are_logged_with_traceback_inside_valid_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    try:
        1 / 0  # noqa: B018
    except ZeroDivisionError:
        logger.exception("calculation failed")
    record = json_lines(capsys.readouterr().out)[0]
    assert record["level"] == "ERROR"
    assert "ZeroDivisionError" in record["exception"]


def test_unserialisable_values_fall_back_to_text(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logger.info("odd", extra={"thing": object()})
    assert "object object at" in json_lines(capsys.readouterr().out)[0]["thing"]


def test_extra_fields_cannot_overwrite_core_fields(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logger.info("real event", extra={"level": "FAKE", "timestamp": "never"})
    record = json_lines(capsys.readouterr().out)[0]
    assert record["event"] == "real event"
    assert record["level"] == "INFO"
    assert record["extra_level"] == "FAKE"
    assert record["extra_timestamp"] == "never"


def test_configure_logging_is_idempotent() -> None:
    for _ in range(3):
        configure_logging("INFO")
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, _StdoutHandler)]
    assert len(handlers) == 1


def test_log_level_is_respected(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING")
    logger.info("hidden")
    logger.warning("shown")
    assert [r["event"] for r in json_lines(capsys.readouterr().out)] == ["shown"]


def test_uvicorn_logging_is_rerouted() -> None:
    configure_logging("INFO")
    assert logging.getLogger("uvicorn.error").propagate is True
    assert logging.getLogger("uvicorn.access").propagate is False  # we log requests ourselves


def test_uvicorn_colour_duplicate_is_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logging.getLogger("uvicorn.error").info("Started %d", 1, extra={"color_message": "\x1b[36m"})
    record = json_lines(capsys.readouterr().out)[0]
    assert "color_message" not in record
    assert record["event"] == "Started 1"


def test_stack_info_is_included_when_requested(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logger.info("where am I", stack_info=True)
    assert "test_stack_info_is_included" in json_lines(capsys.readouterr().out)[0]["stack"]


def test_a_failing_log_write_never_crashes_the_application(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenStream:
        def write(self, _text: str) -> None:
            raise OSError("disk full")

        def flush(self) -> None:  # pragma: no cover - write fails first
            pass

    configure_logging("INFO")
    monkeypatch.setattr(sys, "stdout", BrokenStream())
    logger.info("this write fails")  # must not raise
    assert "Logging error" in capsys.readouterr().err
