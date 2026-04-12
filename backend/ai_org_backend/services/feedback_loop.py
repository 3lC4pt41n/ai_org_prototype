"""S4-08 / S4-09 / S4-10: Feedback-loop services.

Provides:

- ``invalidate_downstream()``: S4-08 – After feedback is integrated on a
  phase artifact, all downstream artifacts (children in the version chain
  and dependents) are marked as stale/un-released.
- ``cascade_invalidation()``: S4-10 – Walks the artifact parent-chain and
  task dependency graph to recursively invalidate all affected artifacts.
- ``redispatch_agent()``: S4-09 – Re-dispatches the agent for a task whose
  artifact was invalidated, so it regenerates with updated context.
- ``load_feedback_context()``: S4-11 – Loads feedback messages linked to a
  task/artifact for injection into agent prompts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import desc
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task, TaskDependency, TaskStatus
from ai_org_backend.models.chat import ChatIntent, ChatMessage, ChatMessageArtifact

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# S4-08: Downstream invalidation after feedback
# ──────────────────────────────────────────────────────────────────────

@dataclass
class InvalidationResult:
    """Summary of what was invalidated."""
    invalidated_artifact_ids: list[str] = field(default_factory=list)
    invalidated_task_ids: list[str] = field(default_factory=list)
    redispatched_task_ids: list[str] = field(default_factory=list)


def invalidate_downstream(
    task_id: str,
    *,
    purpose_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> InvalidationResult:
    """S4-08: Invalidate all downstream artifacts after feedback on a task.

    When feedback is applied to a phase artifact (e.g. PRD), all tasks that
    depend on that task — and their artifacts — must be invalidated so they
    can be regenerated with the updated context.

    Parameters
    ----------
    task_id : str
        The task whose artifact received feedback.
    purpose_id : str, optional
        Limit invalidation to a specific purpose.
    session : Session, optional
        Existing DB session.  If None, creates a new one.
    """
    result = InvalidationResult()
    owns_session = session is None
    if owns_session:
        session = Session(engine)

    try:
        # Find all tasks that directly depend on this task
        downstream_deps = session.exec(
            select(TaskDependency).where(TaskDependency.from_id == task_id)
        ).all()

        for dep in downstream_deps:
            downstream_task = session.get(Task, dep.to_id)
            if not downstream_task:
                continue

            if purpose_id and downstream_task.purpose_id != purpose_id:
                continue

            # Invalidate all artifacts of the downstream task
            artifacts = session.exec(
                select(Artifact)
                .where(Artifact.task_id == downstream_task.id)
                .order_by(desc(Artifact.created_at))
            ).all()

            for art in artifacts:
                if art.released:
                    art.released = False
                    session.add(art)
                    result.invalidated_artifact_ids.append(art.id)
                    logger.info(
                        "[S4-08] Invalidated artifact %s (task=%s) after feedback on %s",
                        art.id,
                        downstream_task.id,
                        task_id,
                    )

            # Mark downstream task for re-execution if it was done
            if downstream_task.status == TaskStatus.DONE:
                downstream_task.status = TaskStatus.TODO
                downstream_task.notes = (
                    f"{downstream_task.notes} | invalidated: upstream feedback"
                    if downstream_task.notes
                    else "invalidated: upstream feedback"
                )
                session.add(downstream_task)
                result.invalidated_task_ids.append(downstream_task.id)

        if owns_session:
            session.commit()

    except Exception as exc:
        logger.error("[S4-08] Downstream invalidation failed: %s", exc)
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()

    return result


# ──────────────────────────────────────────────────────────────────────
# S4-10: Cascading invalidation (artifact chain)
# ──────────────────────────────────────────────────────────────────────

def cascade_invalidation(
    task_id: str,
    *,
    purpose_id: Optional[str] = None,
    max_depth: int = 10,
) -> InvalidationResult:
    """S4-10: Recursively invalidate the full downstream artifact chain.

    Unlike ``invalidate_downstream()`` which only handles direct dependents,
    this walks the full dependency graph transitively: if task A → B → C,
    feedback on A invalidates both B and C.

    Also walks the artifact parent chain (S3-12 versioning): if an artifact
    has children (newer versions), those are invalidated too.
    """
    result = InvalidationResult()
    visited: set[str] = set()

    def _walk(tid: str, depth: int = 0) -> None:
        if tid in visited or depth > max_depth:
            return
        visited.add(tid)

        with Session(engine) as session:
            # Invalidate direct downstream tasks
            downstream_deps = session.exec(
                select(TaskDependency).where(TaskDependency.from_id == tid)
            ).all()

            for dep in downstream_deps:
                downstream_task = session.get(Task, dep.to_id)
                if not downstream_task:
                    continue
                if purpose_id and downstream_task.purpose_id != purpose_id:
                    continue

                # Invalidate artifacts
                artifacts = session.exec(
                    select(Artifact)
                    .where(Artifact.task_id == downstream_task.id)
                ).all()

                for art in artifacts:
                    if art.released and art.id not in result.invalidated_artifact_ids:
                        art.released = False
                        session.add(art)
                        result.invalidated_artifact_ids.append(art.id)

                    # S4-10: Walk artifact version chain (children)
                    _invalidate_artifact_children(session, art.id, result)

                if (
                    downstream_task.status == TaskStatus.DONE
                    and downstream_task.id not in result.invalidated_task_ids
                ):
                    downstream_task.status = TaskStatus.TODO
                    downstream_task.notes = (
                        f"{downstream_task.notes} | cascade-invalidated"
                        if downstream_task.notes
                        else "cascade-invalidated"
                    )
                    session.add(downstream_task)
                    result.invalidated_task_ids.append(downstream_task.id)

                session.commit()
                # Recurse into the downstream task
                _walk(dep.to_id, depth + 1)

    _walk(task_id)
    logger.info(
        "[S4-10] Cascade invalidation from task %s: %d artifacts, %d tasks invalidated",
        task_id,
        len(result.invalidated_artifact_ids),
        len(result.invalidated_task_ids),
    )
    return result


def _invalidate_artifact_children(
    session: Session,
    parent_artifact_id: str,
    result: InvalidationResult,
) -> None:
    """Invalidate child artifacts in the version chain (S3-12 parent_id)."""
    children = session.exec(
        select(Artifact).where(Artifact.parent_id == parent_artifact_id)
    ).all()
    for child in children:
        if child.released and child.id not in result.invalidated_artifact_ids:
            child.released = False
            session.add(child)
            result.invalidated_artifact_ids.append(child.id)
        # Recurse to grandchildren
        _invalidate_artifact_children(session, child.id, result)


# ──────────────────────────────────────────────────────────────────────
# S4-09: Agent re-dispatch after feedback integration
# ──────────────────────────────────────────────────────────────────────

def redispatch_agent(
    task_id: str,
    *,
    tenant_id: Optional[str] = None,
) -> bool:
    """S4-09: Re-dispatch the agent for a task after feedback invalidation.

    The task is reset to "doing" and the appropriate agent is dispatched
    via Celery to regenerate the artifact with the updated context.

    Returns True if the agent was successfully dispatched.
    """
    from ai_org_backend.tasks.celery_app import celery

    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            logger.warning("[S4-09] Task %s not found for re-dispatch", task_id)
            return False

        resolved_tenant = tenant_id or task.tenant_id
        role = task.agent_role or task.owner
        if not role:
            logger.warning("[S4-09] No agent role for task %s – cannot redispatch", task_id)
            return False

        # Normalize role
        role = role.lower().replace("_", "").strip()
        # Map known owner names to agent role names
        role_map = {
            "architect": "architect",
            "dev": "dev",
            "po": "po",
            "productowner": "po",
            "product_owner": "po",
            "qa": "qa",
            "review": "reviewer",
            "reviewer": "reviewer",
            "ux_ui": "ux_ui",
            "uxui": "ux_ui",
            "vision_agent": "vision",
            "visionagent": "vision",
        }
        role = role_map.get(role, role)

        task.status = TaskStatus.DOING
        task.notes = (
            f"{task.notes} | re-dispatched after feedback"
            if task.notes
            else "re-dispatched after feedback"
        )
        session.add(task)
        session.commit()

        # Capture purpose_id before session closes (S-Sprint2 fix)
        task_purpose_id = task.purpose_id

    try:
        celery.send_task(
            f"agent.{role}",
            args=[resolved_tenant, task_id, task_purpose_id],
            queue=f"{resolved_tenant}:{role}",
        )
        logger.info(
            "[S4-09] Re-dispatched agent %s for task %s (tenant=%s)",
            role,
            task_id,
            resolved_tenant,
        )
        return True
    except Exception as exc:
        logger.error("[S4-09] Failed to redispatch agent for task %s: %s", task_id, exc)
        return False


# ──────────────────────────────────────────────────────────────────────
# S4-11: Feedback as context in agent prompt
# ──────────────────────────────────────────────────────────────────────

def load_feedback_context(
    task_id: str,
    *,
    purpose_id: Optional[str] = None,
    max_messages: int = 10,
    max_chars: int = 5000,
) -> str:
    """S4-11: Load feedback messages for a task to inject into agent prompts.

    Returns a formatted string of feedback messages that can be included
    in the agent's prompt context, giving the agent awareness of user
    feedback on previous iterations.
    """
    with Session(engine) as session:
        # First find all artifacts for this task
        artifacts = session.exec(
            select(Artifact).where(Artifact.task_id == task_id)
        ).all()
        artifact_ids = [a.id for a in artifacts]

        if not artifact_ids:
            # Fallback: check for feedback messages directly linked to the task
            task_messages = session.exec(
                select(ChatMessage)
                .where(
                    ChatMessage.task_id == task_id,
                    ChatMessage.intent == ChatIntent.FEEDBACK,
                )
                .order_by(desc(ChatMessage.created_at))
                .limit(max_messages)
            ).all()
        else:
            # Find feedback messages linked to any of the task's artifacts
            linked_msg_ids = session.exec(
                select(ChatMessageArtifact.chat_message_id).where(
                    ChatMessageArtifact.artifact_id.in_(artifact_ids)
                )
            ).all()

            if linked_msg_ids:
                task_messages = session.exec(
                    select(ChatMessage)
                    .where(
                        ChatMessage.id.in_(linked_msg_ids),
                        ChatMessage.intent == ChatIntent.FEEDBACK,
                    )
                    .order_by(desc(ChatMessage.created_at))
                    .limit(max_messages)
                ).all()
            else:
                task_messages = []

        if not task_messages:
            return ""

        # Also include purpose-level feedback if purpose_id is given
        if purpose_id and not task_messages:
            task_messages = session.exec(
                select(ChatMessage)
                .where(
                    ChatMessage.purpose_id == purpose_id,
                    ChatMessage.intent == ChatIntent.FEEDBACK,
                )
                .order_by(desc(ChatMessage.created_at))
                .limit(max_messages)
            ).all()

    # Format feedback into a readable context block
    lines: list[str] = []
    total_chars = 0
    for msg in reversed(task_messages):  # chronological order
        role = getattr(msg, "role", "user")
        content = (msg.content or "").strip()
        if not content:
            continue

        line = f"[{role}] {content}"
        if total_chars + len(line) > max_chars:
            lines.append("... (earlier feedback truncated)")
            break
        lines.append(line)
        total_chars += len(line)

    if not lines:
        return ""

    return "### Previous Feedback\n" + "\n".join(lines)
