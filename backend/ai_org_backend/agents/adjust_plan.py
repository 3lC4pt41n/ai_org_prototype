from ai_org_backend.db import SessionLocal
from ai_org_backend.main import TASK_CNT, Repo
from ai_org_backend.models import Task, TaskOwner
from ai_org_backend.tasks.celery_app import celery
from sqlmodel import func, select


@celery.task(name="agent.adjust_plan")
def agent_adjust_plan(tenant_id: str) -> None:
    """Periodic planning adjuster – adds tasks for emerging risks and logs a summary."""
    high_fail_module = None
    high_retry_module = None
    fail_count = retry_count = 0
    with SessionLocal() as session:
        for owner in (TaskOwner.DEV, TaskOwner.UX_UI, TaskOwner.QA):
            f_cnt = session.exec(
                select(func.count(Task.id)).where(
                    Task.tenant_id == tenant_id,
                    Task.owner == owner,
                    Task.status == "failed",
                )
            ).one()
            r_cnt = session.exec(
                select(func.count(Task.id)).where(
                    Task.tenant_id == tenant_id,
                    Task.owner == owner,
                    Task.retries > 0,
                    Task.status == "done",
                )
            ).one()
            if f_cnt >= 3 and f_cnt > fail_count:
                fail_count, high_fail_module = f_cnt, owner
            if r_cnt >= 3 and r_cnt > retry_count:
                retry_count, high_retry_module = r_cnt, owner
    new_tasks: list[str] = []
    purpose_id = None
    with SessionLocal() as session:
        any_task = session.query(Task).filter_by(tenant_id=tenant_id).first()
        purpose_id = any_task.purpose_id if any_task else None
    if high_fail_module:
        owner_label = high_fail_module.value.replace("_", " ")
        desc = f"Investigate recurring failures in {owner_label} tasks"
        with SessionLocal() as session:
            exists = (
                session.query(Task)
                .filter_by(tenant_id=tenant_id, description=desc, status="todo")
                .first()
            )
        if not exists:
            t = Repo(tenant_id).add_task(
                purpose_id=purpose_id,
                description=desc,
                business_value=0.5,
                tokens_plan=0,
                purpose_relevance=0.0,
                notes="added by adjuster",
            )
            new_tasks.append(f"– {desc} (Task ID: {t.id})")
    elif high_retry_module:
        owner_label = high_retry_module.value.replace("_", " ")
        desc = f"Improve success rate of {owner_label} agent (frequent retries)"
        with SessionLocal() as session:
            exists = (
                session.query(Task)
                .filter_by(tenant_id=tenant_id, description=desc, status="todo")
                .first()
            )
        if not exists:
            t = Repo(tenant_id).add_task(
                purpose_id=purpose_id,
                description=desc,
                business_value=0.5,
                tokens_plan=0,
                purpose_relevance=0.0,
                notes="added by adjuster",
            )
            new_tasks.append(f"– {desc} (Task ID: {t.id})")
    from ai_org_backend.services.storage import register_artefact

    summary_lines = (
        ["No plan changes were necessary."]
        if not new_tasks
        else ["New tasks added to address project risks:"] + new_tasks
    )
    content = "# Plan Adjustment Summary\n" + "\n".join(summary_lines)
    task = Repo(tenant_id).add_task(
        purpose_id=purpose_id,
        description="Planning Adjustment",
        business_value=0.0,
        tokens_plan=0,
        purpose_relevance=0.0,
        notes="",
    )
    register_artefact(task.id, content.encode("utf-8"), filename="planning-adjustment.md")
    Repo(tenant_id).update(
        task.id,
        status="done",
        owner=TaskOwner.PM,
        notes="adjustment OK",
    )
    TASK_CNT.labels(tenant_id, "pm", "done").inc()
    from ai_org_backend.orchestrator.inspector import alert

    alert("Project plan adjusted based on recent task outcomes", kind="info")
