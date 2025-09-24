"""Prometheus metrics helpers and shared collectors."""

from __future__ import annotations

import os

from prometheus_client import Counter, Gauge, Histogram, REGISTRY

__all__ = [
    "prom_counter",
    "prom_hist",
    "TASK_LAT",
    "TASK_CNT",
    "BUDGET_GA",
]


def prom_counter(name: str, desc: str, labels: tuple[str, ...] = ()) -> Counter:
    """Return a Prometheus Counter.

    If *labels* are provided, a labelled counter is created accordingly.
    """

    try:
        return Counter(name, desc, labels) if labels else Counter(name, desc)
    except ValueError:
        # Metric already registered - return existing collector
        return REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]


def prom_hist(name: str, desc: str) -> Histogram:
    """Return a Prometheus Histogram."""
    return Histogram(name, desc)


_DISABLE_METRICS = os.getenv("DISABLE_METRICS") == "1"

if not _DISABLE_METRICS:
    TASK_LAT = Histogram("ai_task_latency_sec", "Task latency", ["role", "tenant"])
    TASK_CNT = Counter("ai_tasks_total", "Tasks done", ["tenant", "role", "status"])
    BUDGET_GA = Gauge("ai_budget_left_usd", "Budget left", ["tenant"])
else:  # pragma: no cover - best effort fallback when metrics are disabled
    TASK_LAT = Histogram(
        "ai_task_latency_sec", "Task latency", ["role", "tenant"], registry=None
    )
    TASK_CNT = Counter(
        "ai_tasks_total", "Tasks done", ["tenant", "role", "status"], registry=None
    )
    BUDGET_GA = Gauge("ai_budget_left_usd", "Budget left", ["tenant"], registry=None)

