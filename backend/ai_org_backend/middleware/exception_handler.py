"""S6-04: Global exception handler with standardised error envelope.

Every unhandled exception is caught, logged with its correlation ID,
and returned as a consistent JSON response::

    {
        "error": "internal_error",
        "detail": "An unexpected error occurred.",
        "request_id": "a1b2c3d4e5f6",
        "status": 500
    }

Known FastAPI/Starlette exceptions (``HTTPException``, ``RequestValidationError``)
are re-formatted into the same envelope so that clients always see a
predictable shape.
"""

from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from ai_org_backend.middleware.request_id import get_request_id

logger = logging.getLogger(__name__)


def _error_envelope(
    status: int,
    error: str,
    detail: str,
    request_id: str | None = None,
) -> JSONResponse:
    body = {
        "error": error,
        "detail": detail,
        "status": status,
    }
    rid = request_id or get_request_id()
    if rid:
        body["request_id"] = rid
    return JSONResponse(status_code=status, content=body)


def install_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _error_envelope(
            status=exc.status_code,
            error=_status_to_slug(exc.status_code),
            detail=str(exc.detail) if exc.detail else "Request failed.",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        # Summarise first validation error for the detail field
        first = errors[0] if errors else {}
        loc = " → ".join(str(p) for p in first.get("loc", []))
        msg = first.get("msg", "Validation failed")
        detail = f"{loc}: {msg}" if loc else msg
        return _error_envelope(
            status=422,
            error="validation_error",
            detail=detail,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        rid = get_request_id()
        logger.error(
            "[S6-04] Unhandled exception on %s %s [rid=%s]: %s\n%s",
            request.method,
            request.url.path,
            rid,
            exc,
            traceback.format_exc(),
        )
        return _error_envelope(
            status=500,
            error="internal_error",
            detail="An unexpected error occurred.",
            request_id=rid,
        )


def _status_to_slug(status: int) -> str:
    """Convert HTTP status code to a machine-readable slug."""
    _MAP = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        413: "payload_too_large",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_error",
        502: "bad_gateway",
        503: "service_unavailable",
    }
    return _MAP.get(status, f"http_{status}")
