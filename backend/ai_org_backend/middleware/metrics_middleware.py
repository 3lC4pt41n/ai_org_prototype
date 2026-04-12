"""S6-07: HTTP request metrics middleware for Prometheus.

Emits three collectors that give full visibility into the API layer:

- ``http_requests_total`` (Counter) — label: method, path, status
- ``http_request_duration_seconds`` (Histogram) — label: method, path
- ``http_requests_in_progress`` (Gauge) — label: method

These complement the existing task-level metrics (TASK_LAT, TASK_CNT,
BUDGET_GA) and give operators a complete picture of API health.
"""

from __future__ import annotations

import os
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_DISABLE = os.getenv("DISABLE_METRICS") == "1"

if not _DISABLE:
    from prometheus_client import Counter, Gauge, Histogram

    HTTP_REQUESTS_TOTAL = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path_template", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path_template"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    )
    HTTP_IN_PROGRESS = Gauge(
        "http_requests_in_progress",
        "HTTP requests currently being processed",
        ["method"],
    )
else:
    from prometheus_client import Counter, Gauge, Histogram

    HTTP_REQUESTS_TOTAL = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path_template", "status"],
        registry=None,
    )
    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path_template"],
        registry=None,
    )
    HTTP_IN_PROGRESS = Gauge(
        "http_requests_in_progress",
        "HTTP requests currently being processed",
        ["method"],
        registry=None,
    )

# Paths to exclude from metrics (avoid cardinality explosion)
_SKIP_PATHS = frozenset({"/metrics", "/health", "/healthz", "/livez", "/readyz"})


def _normalize_path(request: Request) -> str:
    """Collapse path parameters to reduce cardinality.

    Uses the matched route's path template when available, otherwise
    falls back to the raw path but truncates long segments.
    """
    # FastAPI populates scope["route"] for matched routes
    route = request.scope.get("route")
    if route and hasattr(route, "path"):
        return route.path
    # Fallback: return raw path capped at depth 3
    parts = request.url.path.strip("/").split("/")[:3]
    return "/" + "/".join(parts) if parts else "/"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record per-request HTTP metrics for Prometheus."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        method = request.method
        HTTP_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path_template=_normalize_path(request),
                status="500",
            ).inc()
            raise
        finally:
            duration = time.perf_counter() - start
            path_tpl = _normalize_path(request)
            HTTP_IN_PROGRESS.labels(method=method).dec()
            HTTP_REQUEST_DURATION.labels(method=method, path_template=path_tpl).observe(duration)

        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            path_template=path_tpl,
            status=str(response.status_code),
        ).inc()
        return response
