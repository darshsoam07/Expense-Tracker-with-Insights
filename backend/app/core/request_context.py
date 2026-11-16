"""Per-request middleware. For every HTTP request it:

  1. assigns a request ID (reusing a safe inbound X-Request-ID, else generating one),
  2. returns that ID in the X-Request-ID response header (including on errors),
  3. writes one structured access-log line (method, path WITHOUT query string, status, duration),
  4. turns any unexpected exception into the standard 500 JSON body, logging the traceback
     server-side only.

Written as a plain ASGI middleware (not BaseHTTPMiddleware) so context variables propagate
correctly and streaming responses are not buffered.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import internal_error_response
from app.core.logging import request_id_var

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
# Only accept short, plain IDs. Anything else could be used to forge or inject log content.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")


def _request_id_from_headers(scope: Scope) -> str:
    wanted = REQUEST_ID_HEADER.lower().encode("latin-1")
    for name, value in scope.get("headers", []):
        if name == wanted:
            candidate: str = value.decode("latin-1")
            if _VALID_REQUEST_ID.fullmatch(candidate):
                return candidate
            break
    return uuid.uuid4().hex


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_headers(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        context_token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception("request.unhandled_exception")
            if response_started:
                raise  # too late to send a clean 500; let the server close the connection
            status_code = 500
            await internal_error_response(request_id)(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request.completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_var.reset(context_token)
