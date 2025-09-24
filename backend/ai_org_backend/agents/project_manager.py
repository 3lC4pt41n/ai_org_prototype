from ai_org_backend.db import SessionLocal
from ai_org_backend.main import DEFAULT_BUDGET, TASK_CNT, Repo, budget_left
from ai_org_backend.models import Task, TaskOwner
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.tasks.celery_app import celery
from sqlmodel import func, select


@celery.task(name="agent.project_manager")
def agent_project_manager(tenant_id: str) -> None:
    """Periodic Project Management summary – generates a standup report and triggers alerts."""
    with SessionLocal() as session:
        total_tasks = session.exec(
            select(func.count(Task.id)).where(Task.tenant_id == tenant_id)
        ).one()
        done_tasks = session.exec(
            select(func.count(Task.id)).where(Task.tenant_id == tenant_id, Task.status == "done")
        ).one()
        failed_tasks = session.exec(
            select(func.count(Task.id)).where(Task.tenant_id == tenant_id, Task.status == "failed")
        ).one()
        pending_tasks = session.exec(
            select(func.count(Task.id)).where(Task.tenant_id == tenant_id, Task.status == "todo")
        ).one()
    completion_rate = (done_tasks / total_tasks * 100) if total_tasks else 0
    budget_remaining = budget_left(tenant_id)
    report_lines = [
        f"**Tasks Completed:** {done_tasks} / {total_tasks} ({completion_rate:.0f}%)",
        f"**Tasks Pending:** {pending_tasks}",
        f"**Failed Tasks:** {failed_tasks}",
        f"**Budget Remaining:** ${budget_remaining:.2f} / ${DEFAULT_BUDGET:.2f}",
    ]
    if failed_tasks > 0:
        report_lines.append("⚠️ Several tasks have failed. Investigations may be needed.")
    if budget_remaining < DEFAULT_BUDGET * 0.1:
        report_lines.append("⚠️ Budget is running low. Consider scope adjustments.")
    content = "## Project Standup Report\n" + "\n".join("- " + ln for ln in report_lines)
    purpose_id = None
    with SessionLocal() as session:
        any_task = session.query(Task).filter_by(tenant_id=tenant_id).first()
        purpose_id = any_task.purpose_id if any_task else None
    report_task = Repo(tenant_id).add_task(
        purpose_id=purpose_id,
        description="Standup Report",
        business_value=0.0,
        tokens_plan=0,
        purpose_relevance=0.0,
        notes="",
    )
    save_artefact(report_task.id, content.encode("utf-8"), filename="standup.md")
    Repo(tenant_id).update(
        report_task.id,
        status="done",
        owner=TaskOwner.PM,
        notes="standup OK",
    )
    TASK_CNT.labels(tenant_id, "pm", "done").inc()
    from ai_org_backend.orchestrator.inspector import alert

    alert("Standup report generated for project status", kind="info")
