"""S6-05: Health / Readiness / Liveness probe endpoints.

Three standard Kubernetes-style probes:

- ``GET /health`` / ``GET /healthz`` — **Liveness**: returns 200 if the
  process is alive.  Used by orchestrators to decide whether to restart.
- ``GET /readyz`` — **Readiness**: returns 200 only when the database
  and Redis are reachable.  Used by load-balancers to decide whether to
  route traffic.
- ``GET /livez`` — Alias for liveness (some orchestrators prefer this
  path).

All probes return a JSON body with component-level status detail so
operators can quickly identify which dependency is degraded.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_STARTUP_TIME = time.time()


def _check_db() -> dict:
    """Ping the database and return status dict."""
    try:
        from ai_org_backend.db import engine

        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("[S6-05] DB health check failed: %s", exc)
        return {"status": "degraded", "error": str(exc)[:200]}


def _check_redis() -> dict:
    """Ping Redis and return status dict."""
    try:
        import redis as _redis

        from ai_org_backend.settings import settings

        r = _redis.Redis.from_url(settings.redis_url, socket_timeout=2)
        r.ping()
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("[S6-05] Redis health check failed: %s", exc)
        return {"status": "degraded", "error": str(exc)[:200]}


@router.get("/health")
@router.get("/healthz")
@router.get("/livez")
async def liveness():
    """Liveness probe — always 200 if the process is running."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _STARTUP_TIME, 1),
    }


@router.get("/readyz")
async def readiness():
    """Readiness probe — 200 only when all dependencies are reachable."""
    db = _check_db()
    redis = _check_redis()

    all_ok = db["status"] == "ok" and redis["status"] == "ok"
    status_code = 200 if all_ok else 503

    from starlette.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "components": {
                "database": db,
                "redis": redis,
            },
            "uptime_seconds": round(time.time() - _STARTUP_TIME, 1),
        },
    )
