"""S-Sprint4 Fix #8: File-Ownership Reservation Service.

Prevents multiple agents from writing to the same files simultaneously
by providing claim/release primitives.

Usage::

    from ai_org_backend.services.file_reservation import claim_files, release_files

    ok = claim_files("task-123", ["src/app.py", "src/db.py"], "purpose-abc")
    if not ok:
        # Conflict – another task owns one of these files
        ...

    release_files("task-123")
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models.file_reservation import FileReservation

logger = logging.getLogger(__name__)


class FileConflictError(Exception):
    """Raised when a file is already claimed by another task."""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        files = [c["file_path"] for c in conflicts[:5]]
        super().__init__(f"File conflict: {', '.join(files)}")


def claim_files(
    task_id: str,
    file_paths: list[str],
    purpose_id: str,
    *,
    session: Optional[Session] = None,
) -> bool:
    """Claim ownership of files for a task.

    Returns True if all files were successfully claimed.
    Returns False if any file is already claimed by a different task.
    """
    if not file_paths:
        return True

    owns_session = session is None
    if owns_session:
        session = Session(engine)

    try:
        conflicts: list[dict] = []
        for fp in file_paths:
            existing = session.exec(
                select(FileReservation).where(
                    FileReservation.file_path == fp,
                    FileReservation.purpose_id == purpose_id,
                    FileReservation.task_id != task_id,
                )
            ).first()

            if existing:
                conflicts.append({
                    "file_path": fp,
                    "claimed_by": existing.task_id,
                })

        if conflicts:
            logger.warning(
                "[S4-#8] File conflict for task %s: %s",
                task_id,
                [c["file_path"] for c in conflicts],
            )
            return False

        # Claim all files (upsert: skip if already owned by this task)
        for fp in file_paths:
            already_claimed = session.exec(
                select(FileReservation).where(
                    FileReservation.file_path == fp,
                    FileReservation.purpose_id == purpose_id,
                    FileReservation.task_id == task_id,
                )
            ).first()
            if not already_claimed:
                session.add(FileReservation(
                    task_id=task_id,
                    purpose_id=purpose_id,
                    file_path=fp,
                ))

        if owns_session:
            session.commit()

        logger.info(
            "[S4-#8] Task %s claimed %d files in purpose %s",
            task_id, len(file_paths), purpose_id,
        )
        return True

    except Exception as exc:
        if owns_session:
            session.rollback()
        logger.error("[S4-#8] claim_files failed: %s", exc)
        raise
    finally:
        if owns_session:
            session.close()


def release_files(
    task_id: str,
    *,
    session: Optional[Session] = None,
) -> int:
    """Release all file reservations for a task.

    Returns the number of reservations released.
    """
    owns_session = session is None
    if owns_session:
        session = Session(engine)

    try:
        reservations = session.exec(
            select(FileReservation).where(FileReservation.task_id == task_id)
        ).all()

        count = len(reservations)
        for res in reservations:
            session.delete(res)

        if owns_session:
            session.commit()

        if count:
            logger.info("[S4-#8] Released %d file reservations for task %s", count, task_id)
        return count

    except Exception as exc:
        if owns_session:
            session.rollback()
        logger.error("[S4-#8] release_files failed: %s", exc)
        raise
    finally:
        if owns_session:
            session.close()


def get_claimed_files(
    purpose_id: str,
    *,
    exclude_task_id: Optional[str] = None,
) -> list[dict]:
    """Get all currently claimed files for a purpose.

    Returns list of dicts with file_path and task_id.
    """
    with Session(engine) as session:
        query = select(FileReservation).where(
            FileReservation.purpose_id == purpose_id,
        )
        if exclude_task_id:
            query = query.where(FileReservation.task_id != exclude_task_id)

        reservations = session.exec(query).all()
        return [
            {"file_path": r.file_path, "task_id": r.task_id}
            for r in reservations
        ]
