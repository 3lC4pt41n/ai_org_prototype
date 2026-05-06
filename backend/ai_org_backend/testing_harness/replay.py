from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


VOLATILE_KEYS = {"timestamp", "created_at", "updated_at", "started_at", "ended_at"}


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable(val) for key, val in sorted(value.items()) if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


class ReplaySnapshot(BaseModel):
    run_id: str
    checkpoint_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

    def digest(self) -> str:
        stable = json.dumps(_stable(self.payload), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()


class ReplayStore:
    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str], ReplaySnapshot] = {}

    def save(self, snapshot: ReplaySnapshot) -> None:
        self._snapshots[(snapshot.run_id, snapshot.checkpoint_id)] = snapshot

    def load(self, run_id: str, checkpoint_id: str) -> ReplaySnapshot:
        return self._snapshots[(run_id, checkpoint_id)]

    def is_idempotent_resume(self, before: ReplaySnapshot, after: ReplaySnapshot) -> bool:
        return before.digest() == after.digest()
