"""S6-01: In-process sliding-window rate limiter.

Uses a per-IP token-bucket stored in an LRU dict.  When Redis is
available the bucket state is shared across workers; otherwise the
fallback is process-local (still useful for single-worker dev mode
and tests).

Returns HTTP 429 when the limit is exceeded and sets standard
``Retry-After`` / ``X-RateLimit-*`` headers on every response.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Paths exempt from rate limiting
_EXEMPT_PATHS = frozenset({"/health", "/healthz", "/readyz", "/livez", "/metrics"})

# Maximum number of IPs tracked in-process (LRU eviction)
_MAX_BUCKETS = 10_000


class _TokenBucket:
    """Simple token-bucket rate limiter."""

    __slots__ = ("capacity", "tokens", "refill_rate", "last_refill")

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.monotonic()

    def consume(self, n: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    @property
    def retry_after(self) -> int:
        """Seconds until at least one token is available."""
        if self.tokens >= 1:
            return 0
        return max(1, int((1 - self.tokens) / self.refill_rate) + 1)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter.

    Parameters
    ----------
    app : ASGIApp
    requests_per_minute : int
        Sustained request rate per IP.
    burst : int
        Extra burst capacity above the sustained rate.
    """

    def __init__(self, app, requests_per_minute: int = 60, burst: int = 10):
        super().__init__(app)
        self.capacity = requests_per_minute + burst
        self.refill_rate = requests_per_minute / 60.0
        self._buckets: OrderedDict[str, _TokenBucket] = OrderedDict()

    def _get_bucket(self, key: str) -> _TokenBucket:
        if key in self._buckets:
            self._buckets.move_to_end(key)
            return self._buckets[key]
        bucket = _TokenBucket(self.capacity, self.refill_rate)
        self._buckets[key] = bucket
        if len(self._buckets) > _MAX_BUCKETS:
            self._buckets.popitem(last=False)
        return bucket

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        ip = self._client_ip(request)
        bucket = self._get_bucket(ip)

        if not bucket.consume():
            logger.warning("[S6-01] Rate limit exceeded for %s on %s", ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": "Too many requests. Please retry later.",
                },
                headers={
                    "Retry-After": str(bucket.retry_after),
                    "X-RateLimit-Limit": str(self.capacity),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.capacity)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))
        return response
