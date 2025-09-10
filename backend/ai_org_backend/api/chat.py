import logging
from datetime import datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from ai_org_backend.agents import product_owner
from ai_org_backend.agents.utils import load_template
from ai_org_backend.api.auth import ALGORITHM, SECRET_KEY
from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, ChatThreadContext, Purpose, Task, Tenant
from ai_org_backend.models.chat import ChatMessage, ChatRole
from ai_org_backend.redis_client import pool
from ai_org_backend.services.storage import resolve_for_read, save_artefact
from ai_org_backend.utils import llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])
PROMPT_TEMPLATE = load_template("aimar.j2")
ws_router = APIRouter(prefix="/ws")


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

    user_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        artifact_id=artifact_id,
        task_id=task_id,
        role=ChatRole.USER.value,
        content=text,
    )
    session.add(user_msg)
    try:
        session.commit()
    except Exception as e:  # pragma: no cover - DB failure
        session.rollback()
        logger.error("Failed to save user chat message: %s", e)
        raise HTTPException(status_code=500, detail="Could not save message")

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
            agent_content = (
                "Hinweis: Überprüfe auch Architektur, Tests und UI-Dokumentation auf "
                "Konsistenz mit den aktualisierten Anforderungen."
            )
            agent_msg = ChatMessage(
                tenant_id=tenant_id,
                purpose_id=purpose_id,
                artifact_id=artifact_id,
                role=ChatRole.AGENT.value,
                content=agent_content,
                metadata={"betroffene_artefakte": []},
            )
            session.add(agent_msg)

    if assistant_content is None:
        messages: list[dict] = []
        sys_content = PROMPT_TEMPLATE.render(project=purpose.name, paused=paused)
        messages.append({"role": "system", "content": sys_content})

        conv_query = select(ChatMessage).where(
            ChatMessage.tenant_id == tenant_id, ChatMessage.purpose_id == purpose_id
        )
        conv_query = (
            conv_query.where(ChatMessage.artifact_id == artifact_id)
            if artifact_id
            else conv_query.where(ChatMessage.artifact_id.is_(None))
        )
        conv_history = session.exec(conv_query.order_by(ChatMessage.created_at)).all()
        if artifact_id is None:
            chat_context = session.get(ChatThreadContext, purpose_id)
            if chat_context:
                summary_text = chat_context.summary
                if len(conv_history) > 10:
                    conv_history = conv_history[-10:]
                messages.append(
                    {
                        "role": "system",
                        "content": f"Zusammenfassung bisheriger Unterhaltung: {summary_text}",
                    }
                )
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

    assistant_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        artifact_id=artifact_id,
        task_id=task_id,
        role=ChatRole.ASSISTANT.value,
        content=assistant_content or "",
    )
    session.add(assistant_msg)
    try:
        session.commit()
    except Exception as e:  # pragma: no cover - DB failure
        session.rollback()
        logger.error("Failed to save assistant chat message: %s", e)
        raise HTTPException(status_code=500, detail="Could not save response")

    if artifact_id is None:
        conv_all = session.exec(
            select(ChatMessage)
            .where(
                ChatMessage.tenant_id == tenant_id,
                ChatMessage.purpose_id == purpose_id,
                ChatMessage.artifact_id.is_(None),
            )
            .order_by(ChatMessage.created_at)
        ).all()
        total_messages = len(conv_all)
        chat_context = session.get(ChatThreadContext, purpose_id)
        if chat_context is None and total_messages >= 20:
            msgs_to_sum = conv_all[:-10] if len(conv_all) > 10 else []
            if msgs_to_sum:
                conv_text = ""
                for m in msgs_to_sum:
                    role = m.role.value if hasattr(m, "role") else str(m.role)
                    author = (
                        "Nutzer"
                        if role == "user"
                        else ("AImar" if role == "assistant" else "Agent")
                    )
                    conv_text += f"{author}: {m.content}\n"
                prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                try:
                    resp_summary = llm.chat(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        tenant_id=tenant_id,
                    )
                    summary_text = (
                        resp_summary["choices"][0]["message"]["content"]
                        if isinstance(resp_summary, dict)
                        else resp_summary.choices[0].message.content
                    )
                except Exception as e:
                    logger.error("Chat summary generation failed: %s", e)
                    summary_text = ""
                if summary_text:
                    chat_context = ChatThreadContext(purpose_id=purpose_id, summary=summary_text)
                    session.add(chat_context)
                    try:
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        logger.error("Failed to save chat summary: %s", e)
        elif chat_context and total_messages >= 40:
            msgs_to_sum = conv_all[:-10] if len(conv_all) > 10 else []
            if msgs_to_sum:
                conv_text = ""
                for m in msgs_to_sum:
                    role = m.role.value if hasattr(m, "role") else str(m.role)
                    author = (
                        "Nutzer"
                        if role == "user"
                        else ("AImar" if role == "assistant" else "Agent")
                    )
                    conv_text += f"{author}: {m.content}\n"
                prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                try:
                    resp_summary = llm.chat(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        tenant_id=tenant_id,
                    )
                    summary_text = (
                        resp_summary["choices"][0]["message"]["content"]
                        if isinstance(resp_summary, dict)
                        else resp_summary.choices[0].message.content
                    )
                except Exception as e:
                    logger.error("Chat summary generation failed: %s", e)
                    summary_text = ""
                if summary_text:
                    chat_context.summary = summary_text
                    chat_context.updated_at = datetime.utcnow()
                    try:
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        logger.error("Failed to update chat summary: %s", e)

    return {
        "id": assistant_msg.id,
        "role": assistant_msg.role.value,
        "content": assistant_msg.content,
        "created_at": assistant_msg.created_at.isoformat(),
    }


@ws_router.websocket("/chat/{purpose_id}")
async def websocket_chat(websocket: WebSocket, purpose_id: str):
    # Accept WebSocket connection
    await websocket.accept()

    # Authenticate via token from query parameters
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        await websocket.close(code=1008)
        return
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        await websocket.close(code=1008)
        return

    # Verify purpose and retrieve project name
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            await websocket.close(code=1008)
            return
        project_name = purpose.name

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = __import__("json").loads(data)
                user_text = (msg.get("message") or "").strip()
                artifact_id = msg.get("artifact_id")
            except Exception:
                user_text = data.strip()
                artifact_id = None
            if not user_text:
                continue

            with Session(engine) as session:
                user_msg = ChatMessage(
                    tenant_id=tenant_id,
                    purpose_id=purpose_id,
                    artifact_id=artifact_id,
                    task_id=None,
                    role=ChatRole.USER.value,
                    content=user_text,
                )
                session.add(user_msg)
                try:
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logger.error("Failed to save user chat message: %s", e)
                    await websocket.send_json({"error": "Could not save message"})
                    continue

                try:
                    paused = bool(pool.get(f"pause:{tenant_id}:{purpose_id}"))
                except Exception as e:
                    logger.error("Redis get failed: %s", e)
                    paused = False

                assistant_content: str | None = None
                if paused:
                    trivial_responses = {"ok", "fine", "okay", "thanks", "passt", "danke"}
                    if user_text.lower() in trivial_responses:
                        assistant_content = "Verstanden, wird übernommen."
                    else:
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
                            except Exception:
                                current_prd = ""
                        try:
                            updated_prd_md = product_owner.run_requirements_feedback(
                                purpose, feedback=user_text, current_prd=current_prd
                            )
                            target_task_id = prd_artifact.task_id if prd_artifact else None
                            if not target_task_id:
                                prd_task = session.exec(
                                    select(Task)
                                    .where(Task.purpose_id == purpose_id)
                                    .where(
                                        Task.description.ilike("%Product Requirements Document%")
                                    )
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
                                    media_type=(
                                        prd_artifact.media_type if prd_artifact else "text/markdown"
                                    ),
                                    allow_overwrite=True,
                                )
                        except Exception as e:
                            logger.error("PRD update failed: %s", e)
                        assistant_content = "Ich arbeite das ein."

                if assistant_content is None:
                    messages: list[dict] = []
                    sys_content = PROMPT_TEMPLATE.render(project=project_name, paused=paused)
                    messages.append({"role": "system", "content": sys_content})
                    conv_query = select(ChatMessage).where(
                        ChatMessage.tenant_id == tenant_id,
                        ChatMessage.purpose_id == purpose_id,
                    )
                    conv_query = (
                        conv_query.where(ChatMessage.artifact_id == artifact_id)
                        if artifact_id
                        else conv_query.where(ChatMessage.artifact_id.is_(None))
                    )
                    conv_history = session.exec(conv_query.order_by(ChatMessage.created_at)).all()
                    if artifact_id is None:
                        chat_context = session.get(ChatThreadContext, purpose_id)
                        if chat_context:
                            summary_text = chat_context.summary
                            if len(conv_history) > 10:
                                conv_history = conv_history[-10:]
                            messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        f"Zusammenfassung bisheriger Unterhaltung: {summary_text}"
                                    ),
                                }
                            )
                    for m in conv_history:
                        role = m.role.value if hasattr(m, "role") else str(m.role)
                        if role not in ("user", "assistant"):
                            role = "assistant"
                        messages.append({"role": role, "content": m.content})
                    try:
                        resp = await run_in_threadpool(
                            llm.chat,
                            model="gpt-3.5-turbo",
                            messages=messages,
                            tenant_id=tenant_id,
                        )
                        assistant_content = (
                            resp["choices"][0]["message"]["content"]
                            if isinstance(resp, dict)
                            else resp.choices[0].message.content
                        )
                    except Exception as e:
                        logger.error("LLM chat completion failed: %s", e)
                        await websocket.send_json({"error": "AI response generation failed"})
                        continue

                assistant_msg = ChatMessage(
                    tenant_id=tenant_id,
                    purpose_id=purpose_id,
                    artifact_id=artifact_id,
                    task_id=None,
                    role=ChatRole.ASSISTANT.value,
                    content=assistant_content or "",
                )
                session.add(assistant_msg)
                try:
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logger.error("Failed to save assistant chat message: %s", e)
                    await websocket.send_json({"error": "Could not save response"})
                    continue

                await websocket.send_json(
                    {
                        "id": assistant_msg.id,
                        "role": assistant_msg.role.value,
                        "content": assistant_msg.content,
                        "created_at": assistant_msg.created_at.isoformat(),
                    }
                )

                if artifact_id is None:
                    conv_all = session.exec(
                        select(ChatMessage)
                        .where(
                            ChatMessage.tenant_id == tenant_id,
                            ChatMessage.purpose_id == purpose_id,
                            ChatMessage.artifact_id.is_(None),
                        )
                        .order_by(ChatMessage.created_at)
                    ).all()
                    total_messages = len(conv_all)
                    chat_context = session.get(ChatThreadContext, purpose_id)
                    if chat_context is None and total_messages >= 20:
                        msgs_to_sum = conv_all[:-10] if len(conv_all) > 10 else []
                        if msgs_to_sum:
                            conv_text = ""
                            for m in msgs_to_sum:
                                role = m.role.value if hasattr(m, "role") else str(m.role)
                                author = (
                                    "Nutzer"
                                    if role == "user"
                                    else ("AImar" if role == "assistant" else "Agent")
                                )
                                conv_text += f"{author}: {m.content}\n"
                            prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                            try:
                                resp_summary = await run_in_threadpool(
                                    llm.chat,
                                    model="gpt-3.5-turbo",
                                    messages=[{"role": "user", "content": prompt}],
                                    tenant_id=tenant_id,
                                )
                                summary_text = (
                                    resp_summary["choices"][0]["message"]["content"]
                                    if isinstance(resp_summary, dict)
                                    else resp_summary.choices[0].message.content
                                )
                            except Exception as e:
                                logger.error("Chat summary generation failed: %s", e)
                                summary_text = ""
                            if summary_text:
                                new_context = ChatThreadContext(
                                    purpose_id=purpose_id, summary=summary_text
                                )
                                session.add(new_context)
                                try:
                                    session.commit()
                                except Exception as e:
                                    session.rollback()
                                    logger.error("Failed to save chat summary: %s", e)
                    elif chat_context and total_messages >= 40:
                        msgs_to_sum = conv_all[:-10] if len(conv_all) > 10 else []
                        if msgs_to_sum:
                            conv_text = ""
                            for m in msgs_to_sum:
                                role = m.role.value if hasattr(m, "role") else str(m.role)
                                author = (
                                    "Nutzer"
                                    if role == "user"
                                    else ("AImar" if role == "assistant" else "Agent")
                                )
                                conv_text += f"{author}: {m.content}\n"
                            prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                            try:
                                resp_summary = await run_in_threadpool(
                                    llm.chat,
                                    model="gpt-3.5-turbo",
                                    messages=[{"role": "user", "content": prompt}],
                                    tenant_id=tenant_id,
                                )
                                summary_text = (
                                    resp_summary["choices"][0]["message"]["content"]
                                    if isinstance(resp_summary, dict)
                                    else resp_summary.choices[0].message.content
                                )
                            except Exception as e:
                                logger.error("Chat summary generation failed: %s", e)
                                summary_text = ""
                            if summary_text:
                                chat_context.summary = summary_text
                                chat_context.updated_at = datetime.utcnow()
                                try:
                                    session.commit()
                                except Exception as e:
                                    session.rollback()
                                    logger.error("Failed to update chat summary: %s", e)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for purpose %s", purpose_id)
        return
