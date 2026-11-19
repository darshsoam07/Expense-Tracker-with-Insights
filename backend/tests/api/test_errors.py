import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Message, Receive, Scope, Send

from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.main import create_app
from tests.helpers import json_lines, make_settings


def assert_standard_shape(body: dict[str, Any], code: str) -> dict[str, Any]:
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "request_id", "details"}
    assert error["code"] == code
    assert isinstance(error["details"], list)
    return error  # type: ignore[no-any-return]


def test_unknown_route_returns_the_standard_json_error(client: TestClient) -> None:
    response = client.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    error = assert_standard_shape(response.json(), "not_found")
    assert error["message"] == "Not Found"
    assert error["request_id"] == response.headers["x-request-id"]


def test_wrong_method_returns_405_and_keeps_the_allow_header(client: TestClient) -> None:
    response = client.post("/health/live")
    assert response.status_code == 405
    assert_standard_shape(response.json(), "method_not_allowed")
    assert "GET" in response.headers["allow"]


class Payload(BaseModel):
    amount: int
    password: str


def test_validation_errors_are_structured_and_never_echo_input(
    app: FastAPI, client: TestClient
) -> None:
    def echo(payload: Payload) -> Payload:
        return payload

    app.add_api_route("/echo", echo, methods=["POST"])
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/echo",
        json={"amount": "not-a-number", "password": 12345},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422
    error = assert_standard_shape(response.json(), "validation_error")
    assert error["message"] == "Request validation failed."
    locations = [detail["loc"] for detail in error["details"]]
    assert ["body", "amount"] in locations
    assert all(set(detail) == {"loc", "msg", "type"} for detail in error["details"])  # no "input"
    assert "not-a-number" not in response.text


def test_a_submitted_password_is_not_echoed_back_in_a_validation_error(
    app: FastAPI, client: TestClient
) -> None:
    def echo(payload: Payload) -> Payload:
        return payload

    app.add_api_route("/echo", echo, methods=["POST"])
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/echo",
        json={"amount": "bad", "password": "hunter2-secret"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422
    assert "hunter2-secret" not in response.text


def test_app_error_uses_its_status_code_and_details(app: FastAPI, client: TestClient) -> None:
    def conflict() -> None:
        raise AppError(409, "duplicate_request", "Already processed.", [{"field": "key"}])

    app.add_api_route("/conflict", conflict)
    response = client.get("/conflict")
    assert response.status_code == 409
    error = assert_standard_shape(response.json(), "duplicate_request")
    assert error["message"] == "Already processed."
    assert error["details"] == [{"field": "key"}]


@pytest.mark.parametrize("debug", [False, True])
def test_unexpected_exceptions_become_a_generic_500(
    debug: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(make_settings(debug=debug))

    def explode() -> None:
        raise RuntimeError("internal detail: SELECT * FROM users /etc/passwd")

    app.add_api_route("/explode", explode)
    with TestClient(app, raise_server_exceptions=False) as client:
        capsys.readouterr()
        response = client.get("/explode")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    error = assert_standard_shape(response.json(), "internal_error")
    assert error["message"] == "An unexpected error occurred."
    assert error["request_id"] == response.headers["x-request-id"]
    for leaked in ("internal detail", "SELECT", "Traceback", "RuntimeError", "passwd"):
        assert leaked not in response.text

    records = json_lines(capsys.readouterr().out)  # ...but the server log has the full story
    failure = next(r for r in records if r["event"] == "request.unhandled_exception")
    assert failure["level"] == "ERROR"
    assert failure["request_id"] == response.headers["x-request-id"]
    assert "RuntimeError" in failure["exception"]
    completed = next(r for r in records if r["event"] == "request.completed")
    assert completed["status"] == 500


def test_failure_after_the_response_started_is_logged_and_reraised(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Too late for a clean 500 once headers are sent: log it and let the server cut the stream."""

    async def failing_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("broke mid-stream")

    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    configure_logging("INFO")
    scope: Scope = {"type": "http", "method": "GET", "path": "/stream", "headers": []}
    with pytest.raises(RuntimeError, match="broke mid-stream"):
        asyncio.run(RequestContextMiddleware(failing_app)(scope, receive, send))
    assert sent[0]["status"] == 200
    assert len(sent) == 1  # no second (500) response was attempted
    events = [r["event"] for r in json_lines(capsys.readouterr().out)]
    assert "request.unhandled_exception" in events


def test_streaming_responses_still_work(app: FastAPI, client: TestClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"one,"
        yield b"two"

    app.add_api_route("/stream", lambda: StreamingResponse(chunks()))
    response = client.get("/stream")
    assert response.text == "one,two"
    assert "x-request-id" in response.headers


def test_non_http_scopes_pass_straight_through() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:  # pragma: no cover - never called
        raise AssertionError

    asyncio.run(RequestContextMiddleware(inner)({"type": "lifespan"}, receive, send))
    assert seen == ["lifespan"]


def test_http_errors_without_a_dedicated_code_use_a_generic_one(
    app: FastAPI, client: TestClient
) -> None:
    def teapot() -> None:
        raise StarletteHTTPException(418, detail="internal detail must not be echoed")

    app.add_api_route("/teapot", teapot)
    response = client.get("/teapot")
    assert response.status_code == 418
    error = assert_standard_shape(response.json(), "http_error")
    assert error["message"] == "I'm a Teapot"
    assert "internal detail" not in response.text


def test_http_errors_with_a_non_standard_status_still_get_a_safe_message(
    app: FastAPI, client: TestClient
) -> None:
    def odd() -> None:
        raise StarletteHTTPException(599, detail="nope")

    app.add_api_route("/odd", odd)
    response = client.get("/odd")
    assert response.status_code == 599
    assert assert_standard_shape(response.json(), "http_error")["message"] == "Request failed"
