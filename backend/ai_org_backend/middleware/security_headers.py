"""S6-02: Security headers middleware.

Adds OWASP-recommended security headers to every HTTP response:

- ``X-Content-Type-Options: nosniff``
- ``X-Frame-Options: DENY``
- ``X-XSS-Protection: 1; mode=block``
- ``Strict-Transport-Security`` (HSTS) — only when served over HTTPS
- ``Referrer-Policy: strict-origin-when-cross-origin``
- ``Permissions-Policy`` — restricts browser features
- ``Cache-Control: no-store`` for API responses
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach OWASP security headers to every response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        # HSTS only when behind TLS
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
