from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

# Chi nhan x-request-id "an toan" tu client (tranh log injection / ID qua dai).
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def resolve_correlation_id(header_value: str | None) -> str:
    candidate = (header_value or "").strip()
    return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else new_correlation_id()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Xoa context cua request truoc (worker tai su dung) de khong ro metadata giua cac request.
        clear_contextvars()

        correlation_id = resolve_correlation_id(request.headers.get("x-request-id"))
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.1f}"
        return response
