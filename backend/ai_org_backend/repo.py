"""
Unified Repo helper.
All Task updates go through here to keep SQL DB and Neo4j graph in sync.
"""
from __future__ import annotations

import logging
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

        # S-Sprint3 Fix #6: Deferred graph sync via Celery task (non-blocking).
        # Falls back to synchronous call if Celery is unavailable.
        try:
            from ai_org_backend.tasks.celery_app import celery as _celery
            _celery.send_task("graph.sync", args=[self.tenant_id])
        except Exception:
            # Fallback: synchronous graph sync (with retry decorator)
            try:
                graph_sync.upsert_task(
                    obj.id,
                    desc=obj.description,
                    status=str(obj.status),
                    business_value=obj.business_value,
                    tokens_plan=obj.tokens_plan,
                    tokens_actual=obj.tokens_actual,
                    purpose_relevance=obj.purpose_relevance,
                    agent_role=obj.agent_role,
                    model_name=obj.model_name,
                    prompt_template=obj.prompt_template,
                    requires_approval=obj.requires_approval,
                    pipeline_phase_id=obj.pipeline_phase_id,
                )
            except Exception as e:
                logging.error("Graph upsert failed during Task update: %s", e)

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
        pipeline_phase_id: Optional[str] = None,
        agent_role: Optional[str] = None,
        model_name: Optional[str] = None,
        prompt_template: Optional[str] = None,
        requires_approval: Optional[bool] = None,
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
                pipeline_phase_id=pipeline_phase_id,
                agent_role=agent_role,
                model_name=model_name,
                prompt_template=prompt_template,
                requires_approval=bool(requires_approval)
                if requires_approval is not None
                else False,
            )
            s.add(t)
            s.commit()
            s.refresh(t)

            # Dependencies in SQL
            if depends_on:
                for pid in depends_on:
                    s.add(TaskDependency(from_id=pid, to_id=t.id, dependency_type="FINISH_START"))
                s.commit()
                s.refresh(t)

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
                agent_role=t.agent_role,
                model_name=t.model_name,
                prompt_template=t.prompt_template,
                requires_approval=t.requires_approval,
                pipeline_phase_id=t.pipeline_phase_id,
            )
            if depends_on:
                for pid in depends_on:
                    graph_sync.upsert_task(pid)  # ensure parent node exists
                    graph_sync.upsert_dependency(pid, t.id, kind="FINISH_START")
        except Exception as e:
            logging.error("Graph upsert failed during Task creation: %s", e)

        return t

    def link(self, from_id: str, to_id: str, *, kind: str = "FINISH_START") -> None:
        """Add a dependency edge between two existing tasks (SQL + Graph).

        S-Sprint3 Fix #7: Before persisting, validates that the new edge
        does not introduce a cycle in the task dependency DAG.  Raises
        ``CyclicDependencyError`` (HTTP 409) if a cycle is detected.
        """
        from sqlmodel import select as sql_select

        with SessionLocal() as s:
            # S-Sprint3 Fix #7: Load all existing deps and check for cycles
            # before inserting the new edge.
            all_deps = s.exec(sql_select(TaskDependency)).all()
            # Build adjacency: from_id -> [to_id, ...]
            adj: dict[str, set[str]] = {}
            for dep in all_deps:
                adj.setdefault(dep.from_id, set()).add(dep.to_id)
            # Add the proposed new edge
            adj.setdefault(from_id, set()).add(to_id)

            # DFS-based reachability check: can we reach from_id starting from to_id?
            # If yes, adding from_id→to_id would create a cycle.
            visited: set[str] = set()
            stack = [to_id]
            while stack:
                node = stack.pop()
                if node == from_id:
                    from ai_org_backend.services.cycle_detector import CyclicDependencyError
                    raise CyclicDependencyError(
                        [[from_id, to_id, "...", from_id]]
                    )
                if node in visited:
                    continue
                visited.add(node)
                for neighbor in adj.get(node, set()):
                    if neighbor not in visited:
                        stack.append(neighbor)

            s.add(TaskDependency(from_id=from_id, to_id=to_id, dependency_type=kind))
            s.commit()

        try:
            graph_sync.upsert_dependency(from_id, to_id, kind=kind)
        except Exception as e:
            logging.error("Graph dependency upsert failed: %s", e)
