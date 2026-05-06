from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .replay import ReplaySnapshot, ReplayStore


FailureKind = Literal["provider_outage", "timeout", "duplicate_event", "lost_heartbeat"]


class FailureInjection(BaseModel):
    kind: FailureKind
    at_node: str
    recover_after_attempts: int = 1


class ChaosHarness:
    def __init__(self, replay_store: ReplayStore | None = None):
        self.replay_store = replay_store or ReplayStore()

    def provider_outage_resume_is_idempotent(
        self,
        *,
        run_id: str,
        checkpoint_id: str,
        payload: dict,
    ) -> bool:
        before = ReplaySnapshot(run_id=run_id, checkpoint_id=checkpoint_id, payload=payload)
        after = ReplaySnapshot(run_id=run_id, checkpoint_id=checkpoint_id, payload=dict(payload))
        self.replay_store.save(before)
        return self.replay_store.is_idempotent_resume(before, after)
