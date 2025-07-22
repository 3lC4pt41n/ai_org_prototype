from __future__ import annotations

from sqlmodel import Session, select

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Task, Purpose
from ai_org_backend.agents.planner import plan_tasks
from ai_org_backend.agents.architect import seed_graph as architect_seed


def get_backlog(tid: str):
    """Return todo tasks for tenant."""
    with SessionLocal() as db:
        return db.exec(
            select(Task).where(Task.tenant_id == tid, Task.status == "todo")
        ).all()


def get_first_purpose(tid: str) -> Purpose | None:
    with SessionLocal() as db:
        return db.exec(select(Purpose).where(Purpose.tenant_id == tid)).first()


def orchestrate(tenant_id: str) -> None:
    backlog = get_backlog(tenant_id)
    if not backlog:
        purpose = get_first_purpose(tenant_id)
        if purpose:
            architect_seed.delay(tenant_id, purpose.id)
        return
    plan_tasks.delay(tenant_id)


if __name__ == "__main__":
    orchestrate("demo")

