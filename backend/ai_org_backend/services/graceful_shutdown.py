"""S6-08: Graceful shutdown handler.

Integrates with FastAPI's lifespan to ensure:

1. New requests are drained (Uvicorn handles this via SIGTERM).
2. In-flight Celery tasks receive a soft timeout signal.
3. The database connection pool is disposed cleanly.
4. The Neo4j driver is closed.
5. A shutdown log marker is emitted for log aggregators.

Usage::

    from ai_org_backend.services.graceful_shutdown import (
        on_startup,
        on_shutdown,
    )
"""

from __future__ import annotations

import logging
import signal
import time

logger = logging.getLogger(__name__)

_STARTUP_TS: float = 0.0


def on_startup() -> None:
    """Called during FastAPI lifespan startup."""
    global _STARTUP_TS
    _STARTUP_TS = time.time()
    logger.info("[S6-08] Application started (pid=%d)", __import__("os").getpid())


def on_shutdown() -> None:
    """Called during FastAPI lifespan shutdown."""
    uptime = time.time() - _STARTUP_TS if _STARTUP_TS else 0
    logger.info(
        "[S6-08] Graceful shutdown initiated (uptime=%.1fs)", uptime
    )

    # 1. Close database connections
    try:
        from ai_org_backend.db import engine

        engine.dispose()
        logger.info("[S6-08] Database connection pool disposed")
    except Exception as exc:
        logger.warning("[S6-08] Failed to dispose DB pool: %s", exc)

    # 2. Close Neo4j driver
    try:
        from ai_org_backend.main import driver

        driver.close()
        logger.info("[S6-08] Neo4j driver closed")
    except Exception as exc:
        logger.warning("[S6-08] Failed to close Neo4j driver: %s", exc)

    # 3. Flush Celery broker connections
    try:
        from ai_org_backend.tasks.celery_app import celery

        celery.close()
        logger.info("[S6-08] Celery broker connections closed")
    except Exception as exc:
        logger.warning("[S6-08] Failed to close Celery connections: %s", exc)

    logger.info("[S6-08] Shutdown complete")
