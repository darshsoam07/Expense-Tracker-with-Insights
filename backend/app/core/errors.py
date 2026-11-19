"""One standard error shape for every failed API response:

    {"error": {"code": "not_found", "message": "Not Found",
               "request_id": "...", "details": []}}

Error bodies never contain tracebacks, SQL, or the values a client submitted.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    501: "not_implemented",
}


class AppError(Exception):
    """An expected, client-visible failure. Raise it from services and routes.

    Example: raise AppError(409, "duplicate_request", "This request was already processed.")
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or [],
        }
    }
    return JSONResponse(body, status_code=status_code, headers=headers)


def internal_error_response(request_id: str | None) -> JSONResponse:
    """The only thing a client ever learns about an unexpected server failure."""
    return error_response(500, "internal_error", "An unexpected error occurred.", request_id)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or request_id_var.get()


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - narrows the type for mypy
    return error_response(exc.status_code, exc.code, exc.message, _request_id(request), exc.details)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    try:
        message = HTTPStatus(exc.status_code).phrase  # fixed text: never echo exc.detail
    except ValueError:
        message = "Request failed"
    headers = dict(exc.headers) if exc.headers else None  # keeps e.g. the 405 "Allow" header
    return error_response(exc.status_code, code, message, _request_id(request), headers=headers)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Deliberately copy only where / what / type. pydantic's "input" field holds the value the
    # client sent, which could be a password, so it must never be echoed back.
    details = [
        {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
        for item in exc.errors()
    ]
    return error_response(
        422, "validation_error", "Request validation failed.", _request_id(request), details
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach handlers. Unexpected exceptions are handled by RequestContextMiddleware."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
