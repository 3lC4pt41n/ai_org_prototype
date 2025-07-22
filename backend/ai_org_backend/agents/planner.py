from __future__ import annotations

from celery import shared_task


@shared_task(name="planner.plan_tasks", queue="dev")
def plan_tasks(*args, **kwargs):
    """Stub planner task."""
    print("planning", args, kwargs)

