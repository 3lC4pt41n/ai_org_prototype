import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ai_org_backend.agents import product_owner
from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.models import Artifact, Purpose, Task, Tenant
from ai_org_backend.models.chat import ChatMessage, ChatRole
from ai_org_backend.redis_client import pool
from ai_org_backend.services.storage import resolve_for_read, save_artefact
from ai_org_backend.utils import llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/history")
def get_chat_history(
    purpose_id: str,
    artifact_id: str | None = None,
    session: Session = Depends(get_session),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Retrieve chat message history for a given purpose (and optional artifact context)."""

    tenant_id = current_tenant.id
    purpose = session.get(Purpose, purpose_id)
    if not purpose or purpose.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Purpose not found")

    query = select(ChatMessage).where(
        ChatMessage.tenant_id == tenant_id, ChatMessage.purpose_id == purpose_id
    )
    if artifact_id:
        query = query.where(ChatMessage.artifact_id == artifact_id)
    else:
        query = query.where(ChatMessage.artifact_id.is_(None))

    messages = session.exec(query.order_by(ChatMessage.created_at)).all()
    history: list[dict] = []
    for m in messages:
        role = m.role.value if hasattr(m, "role") else str(m.role)
        author: str | None
        if role == ChatRole.USER.value:
            author = current_tenant.name
        elif role == ChatRole.ASSISTANT.value:
            author = "AImar"
        else:
            author = "Agent"
        history.append(
            {
                "id": m.id,
                "role": role,
                "content": m.content,
                "author": author,
                "created_at": m.created_at.isoformat() if getattr(m, "created_at", None) else None,
            }
        )
    return history


@router.post("")
def post_chat(
    payload: dict,
    session: Session = Depends(get_session),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Send a message in the chat and get a response."""

    tenant_id = current_tenant.id
    text = (payload.get("message") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message content required")

    purpose_id = payload.get("purpose_id")
    if not purpose_id:
        raise HTTPException(status_code=400, detail="Purpose ID required")

    purpose = session.get(Purpose, purpose_id)
    if not purpose or purpose.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Purpose not found or forbidden")

    artifact_id = payload.get("artifact_id")
    task_id = None
    if artifact_id:
        artifact = session.get(Artifact, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        task = session.get(Task, artifact.task_id)
        if not task or task.tenant_id != tenant_id or task.purpose_id != purpose_id:
            raise HTTPException(status_code=403, detail="Artifact not in specified purpose")
        task_id = task.id

    # Save user message
    user_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        artifact_id=artifact_id,
        task_id=task_id,
        role=ChatRole.USER,
        content=text,
    )
    session.add(user_msg)
    try:
        session.commit()
    except Exception as e:  # pragma: no cover - DB failure
        session.rollback()
        logger.error("Failed to save user chat message: %s", e)
        raise HTTPException(status_code=500, detail="Could not save message")

    # Determine if pipeline is paused (waiting for feedback)
    try:
        paused = bool(pool.get(f"pause:{tenant_id}:{purpose_id}"))
    except Exception as e:  # pragma: no cover - Redis failure
        logger.error("Redis get failed: %s", e)
        paused = False

    assistant_content: str | None = None
    if paused:
        trivial_responses = {"ok", "fine", "okay", "thanks", "passt", "danke"}
        if text.lower() in trivial_responses:
            assistant_content = "Verstanden, wird übernommen."
        else:
            # Update PRD based on feedback
            current_prd = ""
            try:
                prd_artifact = session.exec(
                    select(Artifact)
                    .where(Artifact.task.has(purpose_id=purpose_id))
                    .where(Artifact.repo_path.ilike("%product_requirements.md"))
                    .order_by(Artifact.created_at.desc())
                ).first()
            except Exception:
                prd_artifact = None

            if prd_artifact:
                try:
                    file_path = resolve_for_read(prd_artifact.repo_path)
                    current_prd = file_path.read_text(encoding="utf-8")
                except Exception:  # pragma: no cover - file read failure
                    current_prd = ""
            try:
                updated_prd_md = product_owner.run_requirements_feedback(
                    purpose, feedback=text, current_prd=current_prd
                )
                target_task_id = prd_artifact.task_id if prd_artifact else None
                if not target_task_id:
                    prd_task = session.exec(
                        select(Task)
                        .where(Task.purpose_id == purpose_id)
                        .where(Task.description.ilike("%Product Requirements Document%"))
                    ).first()
                    target_task_id = prd_task.id if prd_task else None
                if target_task_id:
                    save_artefact(
                        target_task_id,
                        updated_prd_md.encode("utf-8"),
                        filename=(
                            prd_artifact.repo_path
                            if prd_artifact
                            else "requirements/product_requirements.md"
                        ),
                        media_type=prd_artifact.media_type if prd_artifact else "text/markdown",
                        allow_overwrite=True,
                    )
            except Exception as e:  # pragma: no cover - PRD update failure
                logger.error("PRD update failed: %s", e)
            assistant_content = "Ich arbeite das ein."

    if assistant_content is None:
        # Normal interactive Q/A via LLM
        messages: list[dict] = []
        sys_msg = f"Du bist AImar, ein KI-Produkt Owner Assistent. Projekt: {purpose.name}. "
        if paused:
            sys_msg += "Der Entwicklungsprozess ist pausiert und wartet auf Feedback zum PRD. "
        messages.append({"role": "system", "content": sys_msg})

        conv_query = select(ChatMessage).where(
            ChatMessage.tenant_id == tenant_id, ChatMessage.purpose_id == purpose_id
        )
        conv_query = (
            conv_query.where(ChatMessage.artifact_id == artifact_id)
            if artifact_id
            else conv_query.where(ChatMessage.artifact_id.is_(None))
        )
        conv_history = session.exec(conv_query.order_by(ChatMessage.created_at)).all()
        for m in conv_history:
            role = m.role.value if hasattr(m, "role") else str(m.role)
            if role not in ("user", "assistant"):
                role = "assistant"
            messages.append({"role": role, "content": m.content})

        try:
            resp = llm.chat(model="gpt-3.5-turbo", messages=messages, tenant_id=tenant_id)
            assistant_content = (
                resp["choices"][0]["message"]["content"]
                if isinstance(resp, dict)
                else resp.choices[0].message.content
            )
        except Exception as e:  # pragma: no cover - LLM failure
            logger.error("LLM chat completion failed: %s", e)
            raise HTTPException(status_code=500, detail="AI response generation failed")

    # Save assistant message
    assistant_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        artifact_id=artifact_id,
        task_id=task_id,
        role=ChatRole.ASSISTANT,
        content=assistant_content or "",
    )
    session.add(assistant_msg)
    try:
        session.commit()
    except Exception as e:  # pragma: no cover - DB failure
        session.rollback()
        logger.error("Failed to save assistant chat message: %s", e)
        raise HTTPException(status_code=500, detail="Could not save response")

    return {
        "id": assistant_msg.id,
        "role": assistant_msg.role.value,
        "content": assistant_msg.content,
        "created_at": assistant_msg.created_at.isoformat(),
    }
