"""S6-06: Structured JSON logging setup.

Replaces the default Python logging format with a JSON-lines formatter
so that log aggregators (ELK, Datadog, CloudWatch) can index fields
natively.  Every log record includes:

- ``timestamp`` (ISO-8601)
- ``level``
- ``logger`` name
- ``message``
- ``request_id`` (from the S6-03 correlation middleware)
- ``module``, ``funcName``, ``lineno``

Call ``setup_logging()`` once at application startup (before any
routers are loaded) to configure the root logger.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        # Import lazily to avoid circular deps during startup
        try:
            from ai_org_backend.middleware.request_id import get_request_id

            rid = get_request_id()
        except Exception:
            rid = ""

        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }
        if rid:
            log_entry["request_id"] = rid
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"

    def __init__(self) -> None:
        super().__init__(self.FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure the root logger.

    Parameters
    ----------
    level : str
        Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    fmt : str
        ``"json"`` for structured JSON output, ``"text"`` for human-readable.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers to avoid duplicate output
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())
    root.addHandler(handler)

    # Silence overly chatty third-party loggers
    for noisy in ("uvicorn.access", "urllib3", "httpcore", "neo4j"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info("[S6-06] Structured logging initialised (level=%s, format=%s)", level, fmt)
