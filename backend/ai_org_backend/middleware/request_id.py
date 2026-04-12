"""S6-03: Request ID / Correlation ID middleware.

Assigns a unique ``X-Request-ID`` to every incoming request so that all
downstream log lines and error responses can be correlated.  If the
caller already supplies the header (e.g. an API gateway) the value is
reused; otherwise a new UUID-4 is generated.

The current request ID is stored in a ``contextvars.ContextVar`` so it
can be read from any async or sync code path in the same request.
"""

from __future__ import annotations

import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)

_HEADER = "X-Request-ID"


def get_request_id() -> str:
    """Return the current request's correlation ID (or empty outside a request)."""
    return REQUEST_ID_CTX.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject / propagate ``X-Request-ID`` on every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = request.headers.get(_HEADER) or uuid.uuid4().hex[:16]
        REQUEST_ID_CTX.set(rid)
        response = await call_next(request)
        response.headers[_HEADER] = rid
        return response
