import logging
from typing import Any, Dict

log = logging.getLogger("uvicorn.error")


def ingest(*, dry_run: bool = True, **kwargs: Any) -> Dict[str, Any]:
    """
    Minimaler Platzhalter für das Pipeline-Import:
    Wird vom API-Router importiert, darf beim App-Start aber nichts Schweres tun.
    In echter Nutzung hier eure Graph-/Qdrant-Ingestion aufrufen.
    """
    msg = "seed_graph.ingest() called (dry_run=%s) – stub is in place." % dry_run
    log.info(msg)
    return {"ok": True, "dry_run": dry_run, "message": msg}
