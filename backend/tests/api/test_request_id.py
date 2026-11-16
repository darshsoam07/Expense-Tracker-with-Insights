import json
import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.helpers import json_lines

HEX_ID = re.compile(r"[0-9a-f]{32}")


@pytest.mark.parametrize(
    ("method", "path", "expected_status"),
    [("GET", "/health/live", 200), ("GET", "/does-not-exist", 404), ("POST", "/health/live", 405)],
)
def test_every_response_carries_a_request_id(
    client: TestClient, method: str, path: str, expected_status: int
) -> None:
    response = client.request(method, path)
    assert response.status_code == expected_status
    assert HEX_ID.fullmatch(response.headers["x-request-id"])


def test_a_new_id_is_generated_for_each_request(client: TestClient) -> None:
    ids = {client.get("/health/live").headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5


def test_a_safe_inbound_id_is_reused(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "trace-abc.123_XYZ"})
    assert response.headers["x-request-id"] == "trace-abc.123_XYZ"


@pytest.mark.parametrize(
    "bad_id", ["short", "x" * 65, "has space in it", "semi;colon;12345", 'quote"mark12345']
)
def test_an_unsafe_inbound_id_is_replaced(client: TestClient, bad_id: str) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": bad_id})
    assert response.headers["x-request-id"] != bad_id
    assert HEX_ID.fullmatch(response.headers["x-request-id"])


def test_error_body_and_header_share_the_same_id(client: TestClient) -> None:
    response = client.get("/missing")
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_access_log_records_the_request(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()  # discard start-up lines
    response = client.get("/health/live")
    access = [r for r in json_lines(capsys.readouterr().out) if r["event"] == "request.completed"]
    assert len(access) == 1
    assert access[0]["request_id"] == response.headers["x-request-id"]
    assert access[0]["method"] == "GET"
    assert access[0]["path"] == "/health/live"
    assert access[0]["status"] == 200
    assert isinstance(access[0]["duration_ms"], float)


def test_access_log_never_contains_the_query_string(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    client.get("/health/live?token=super-secret-query-value")
    # Only look at the application's own access log. (The test client library, httpx2, also logs
    # the URL it requested; that is a test-harness artifact, not the server's behaviour.)
    access = [r for r in json_lines(capsys.readouterr().out) if r["logger"] == "app.request"]
    assert len(access) == 1
    assert access[0]["path"] == "/health/live"
    assert "super-secret-query-value" not in json.dumps(access[0])


def test_logs_written_while_handling_a_request_carry_its_id(
    app: FastAPI, client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler() -> dict[str, str]:
        logging.getLogger("app.test").info("inside handler")
        return {"ok": "yes"}

    app.add_api_route("/probe", handler)
    capsys.readouterr()
    response = client.get("/probe")
    records = {r["event"]: r for r in json_lines(capsys.readouterr().out)}
    assert records["inside handler"]["request_id"] == response.headers["x-request-id"]
