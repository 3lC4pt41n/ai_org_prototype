from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def ingest(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """
    Placeholder graph seeding function.

    Keeps the app bootable even if a real seeder hasn't been wired yet.
    Returns a lightweight summary so the API can respond usefully.

    Args:
        *args: Ignored.
        **kwargs: Ignored.

    Returns:
        dict: Summary payload.
    """

    logger.info("scripts.seed_graph.ingest invoked (placeholder).")
    return {
        "status": "ok",
        "ingested_nodes": 0,
        "ingested_edges": 0,
        "detail": "No-op seeder (placeholder). Replace with real ingestion logic as needed.",
    }

