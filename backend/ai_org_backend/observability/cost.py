from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from pydantic import BaseModel, Field


class CostRecord(BaseModel):
    run_id: str
    node_id: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class CostTracker:
    def __init__(self) -> None:
        self.records: list[CostRecord] = []

    def record(self, record: CostRecord) -> None:
        self.records.append(record)

    def total_for_run(self, run_id: str) -> float:
        return round(sum(record.cost_eur for record in self.records if record.run_id == run_id), 6)

    def by_node(self, run_id: str) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for record in self.records:
            if record.run_id == run_id:
                totals[record.node_id] += record.cost_eur
        return {node_id: round(value, 6) for node_id, value in sorted(totals.items())}
