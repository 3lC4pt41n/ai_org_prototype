"""
Unified Repo helper.
All Task updates go through here to keep SQL DB and Neo4j graph in sync.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Task, TaskDependency
from ai_org_backend.services import graph_sync


class Repo:
    """
    Simple repository wrapper for a given tenant.
    Right now tenant_id is informational (available for future multi-tenant partitioning).
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    # ---------- read helpers ----------
    def get(self, task_id: str) -> Optional[Task]:
        with SessionLocal() as s:
            return s.get(Task, task_id)

    # ---------- write helpers ----------
    def update(self, task_id: str, **fields: Any) -> Task:
        """
        Update Task in SQL and mirror important props into Neo4j.
        Allowed fields: any Task ORM attribute (status, owner, notes, business_value,
        tokens_plan, tokens_actual, purpose_relevance, description, ...)
        """
        with SessionLocal() as s:
            obj = s.get(Task, task_id)
            if not obj:
                raise ValueError(f"Task {task_id} not found")
            # Apply field changes
            for k, v in fields.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            s.add(obj)
            s.commit()
            s.refresh(obj)

        # Mirror to graph (best-effort; never break request on graph failure)
        try:
            graph_sync.upsert_task(
                obj.id,
                desc=obj.description,
                status=str(obj.status),
                business_value=obj.business_value,
                tokens_plan=obj.tokens_plan,
                tokens_actual=obj.tokens_actual,
                purpose_relevance=obj.purpose_relevance,
            )
        except Exception as e:
            # Intentionally swallow to not block the pipeline; logs are handled by caller/logger
            pass

        return obj

    def add_task(
        self,
        *,
        purpose_id: str,
        description: str,
        business_value: float = 1.0,
        tokens_plan: int = 1000,
        purpose_relevance: float = 1.0,
        notes: str = "",
        depends_on: Optional[Iterable[str]] = None,
    ) -> Task:
        """
        Create a new Task and (optionally) dependencies to parent tasks.
        Returns the persisted ORM object.
        """
        with SessionLocal() as s:
            t = Task(
                tenant_id=self.tenant_id,
                purpose_id=purpose_id,
                description=description,
                business_value=business_value,
                tokens_plan=tokens_plan,
                purpose_relevance=purpose_relevance,
                notes=notes or "",
            )
            s.add(t)
            s.commit()
            s.refresh(t)

            # Dependencies in SQL
            if depends_on:
                for pid in depends_on:
                    s.add(TaskDependency(from_id=pid, to_id=t.id, dependency_type="FINISH_START"))
                s.commit()

        # Graph upserts (best-effort)
        try:
            graph_sync.upsert_task(
                t.id,
                desc=t.description,
                status=str(t.status),
                business_value=t.business_value,
                tokens_plan=t.tokens_plan,
                tokens_actual=t.tokens_actual,
                purpose_relevance=t.purpose_relevance,
            )
            if depends_on:
                for pid in depends_on:
                    graph_sync.upsert_task(pid)  # ensure parent node exists
                    graph_sync.upsert_dependency(pid, t.id, kind="FINISH_START")
        except Exception:
            pass

        return t

    def link(self, from_id: str, to_id: str, *, kind: str = "FINISH_START") -> None:
        """
        Add a dependency edge between two existing tasks (SQL + Graph).
        """
        with SessionLocal() as s:
            s.add(TaskDependency(from_id=from_id, to_id=to_id, dependency_type=kind))
            s.commit()
        try:
            graph_sync.upsert_dependency(from_id, to_id, kind=kind)
        except Exception:
            pass
