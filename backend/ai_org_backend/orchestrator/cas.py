"""S2-03: Compare-And-Swap helpers for optimistic locking on Task status.

``cas_update_status()`` ensures that a status transition only succeeds when
the in-memory ``version`` matches the database row.  If another writer has
incremented the version in the meantime, a ``StaleTaskError`` is raised.
"""

from __future__ import annotations

import logging
from datetime import datetime as dt
from typing import Optional

from sqlalchemy import update
from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.models import Task

logger = logging.getLogger(__name__)


class StaleTaskError(Exception):
    """Raised when the task version in the DB does not match the expected version."""


def cas_update_status(
    task_id: str,
    expected_version: int,
    new_status: str,
    *,
    notes: Optional[str] = None,
    owner: Optional[str] = None,
) -> int:
    """Atomically update a task's status if the version matches.

    Returns the new version on success.
    Raises ``StaleTaskError`` if the row has been modified by another writer.
    """
    values: dict = {
        "status": new_status,
        "version": expected_version + 1,
        "last_heartbeat_at": dt.utcnow(),
    }
    if notes is not None:
        values["notes"] = notes
    if owner is not None:
        values["owner"] = owner

    with Session(engine) as session:
        result = session.exec(  # type: ignore[call-overload]
            update(Task)
            .where(Task.id == task_id, Task.version == expected_version)
            .values(**values)
        )
        row_count = result.rowcount  # type: ignore[union-attr]
        session.commit()

    if row_count == 0:
        raise StaleTaskError(
            f"Task {task_id} version mismatch: expected {expected_version}"
        )

    logger.debug(
        "CAS update task %s: %s → %s (v%d → v%d)",
        task_id, "?", new_status, expected_version, expected_version + 1,
    )
    return expected_version + 1
