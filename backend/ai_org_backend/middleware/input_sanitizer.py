"""S6-09: Input sanitization middleware.

Two responsibilities:

1. **Request body size guard** — rejects payloads that exceed a
   configurable maximum (default 10 MB) with HTTP 413.
2. **Dangerous pattern filter** — scans JSON string values for common
   injection vectors (script tags, SQL injection fragments) and strips
   or rejects them before they reach the application layer.

Only applies to ``application/json`` request bodies.  File uploads and
other content types pass through unchanged.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Patterns we consider dangerous in JSON string values
_DANGEROUS_PATTERNS = [
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onload=, onclick=, …
]

# SQL injection fragments (only the most blatant)
_SQL_INJECTION_PATTERNS = [
    re.compile(r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|EXEC)\s", re.IGNORECASE),
    re.compile(r"'\s*OR\s+'1'\s*=\s*'1", re.IGNORECASE),
    re.compile(r"UNION\s+SELECT", re.IGNORECASE),
]


def _scan_value(value: str) -> Optional[str]:
    """Return the name of the first dangerous pattern found, or None."""
    for p in _DANGEROUS_PATTERNS:
        if p.search(value):
            return "xss"
    for p in _SQL_INJECTION_PATTERNS:
        if p.search(value):
            return "sql_injection"
    return None


def _scan_json(obj, depth: int = 0) -> Optional[str]:
    """Recursively scan JSON values for dangerous patterns."""
    if depth > 20:
        return None
    if isinstance(obj, str):
        return _scan_value(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            result = _scan_json(v, depth + 1)
            if result:
                return result
    if isinstance(obj, list):
        for item in obj:
            result = _scan_json(item, depth + 1)
            if result:
                return result
    return None


class InputSanitizerMiddleware(BaseHTTPMiddleware):
    """Reject oversized or injection-laden request bodies."""

    def __init__(self, app, max_body_bytes: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip non-mutating methods
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        # Check Content-Length header first (cheap check)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_bytes:
            logger.warning(
                "[S6-09] Request body too large: %s bytes from %s",
                content_length,
                request.url.path,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "error": "payload_too_large",
                    "detail": f"Request body exceeds {self.max_body_bytes} bytes.",
                },
            )

        # For JSON payloads, scan for injection patterns
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            try:
                body = await request.body()
                if len(body) > self.max_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "payload_too_large",
                            "detail": f"Request body exceeds {self.max_body_bytes} bytes.",
                        },
                    )
                if body:
                    parsed = json.loads(body)
                    threat = _scan_json(parsed)
                    if threat:
                        logger.warning(
                            "[S6-09] Dangerous input detected (%s) from %s on %s",
                            threat,
                            request.client.host if request.client else "?",
                            request.url.path,
                        )
                        return JSONResponse(
                            status_code=422,
                            content={
                                "error": "dangerous_input",
                                "detail": f"Request rejected: suspected {threat} pattern detected.",
                            },
                        )
            except json.JSONDecodeError:
                pass  # Let FastAPI handle malformed JSON
            except Exception:
                pass  # Don't block on scan errors

        return await call_next(request)
