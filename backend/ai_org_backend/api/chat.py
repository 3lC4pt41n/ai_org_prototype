import logging
from datetime import datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session, delete, select
from starlette.concurrency import run_in_threadpool

from ai_org_backend.agents import product_owner
from ai_org_backend.agents.utils import load_template
from ai_org_backend.api.auth import ALGORITHM, SECRET_KEY
from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, ChatThreadContext, Purpose, Task, Tenant
from ai_org_backend.models.chat import (
    ChatIntent,
    ChatMessage,
    ChatMessageArtifact,
    ChatRole,
    ChatScope,
)
from ai_org_backend.redis_client import pool
from ai_org_backend.services.storage import resolve_for_read, save_artefact
from ai_org_backend.services.vector_store import VectorStore
from ai_org_backend.utils import llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])
PROMPT_TEMPLATE = load_template("aimar.j2")
ws_router = APIRouter(prefix="/ws")


@router.get("/messages")
def get_chat_messages(
    purpose_id: str,
    artifact_id: list[str] | None = Query(None),
    scope: ChatScope | None = None,
    session: Session = Depends(get_session),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Retrieve chat messages for a given purpose with optional filtering."""

    tenant_id = current_tenant.id
    purpose = session.get(Purpose, purpose_id)
    if not purpose or purpose.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Purpose not found")

    messages_query = select(ChatMessage).where(
        ChatMessage.tenant_id == tenant_id, ChatMessage.purpose_id == purpose_id
    )
    if artifact_id:
        messages_query = (
            messages_query.join(ChatMessageArtifact)
            .where(ChatMessageArtifact.artifact_id.in_(artifact_id))
            .distinct()
        )
    elif scope:
        if scope == ChatScope.GLOBAL:
            subq = select(ChatMessageArtifact.chat_message_id)
            messages_query = messages_query.where(ChatMessage.id.not_in(subq))
        elif scope == ChatScope.ARTIFACT:
            messages_query = messages_query.join(ChatMessageArtifact).distinct()
        elif scope == ChatScope.MIXED:
            messages_query = messages_query.where(ChatMessage.scope == ChatScope.MIXED)

    messages = session.exec(messages_query.order_by(ChatMessage.created_at)).all()
    history: list[dict] = []
    msg_ids = [m.id for m in messages]
    link_map: dict[str, list[str]] = {}
    if msg_ids:
        links = session.exec(
            select(ChatMessageArtifact.chat_message_id, ChatMessageArtifact.artifact_id).where(
                ChatMessageArtifact.chat_message_id.in_(msg_ids)
            )
        ).all()
        for msg_id, art_id in links:
            link_map.setdefault(msg_id, []).append(art_id)

    for m in messages:
        role = m.role.value if hasattr(m, "role") else str(m.role)
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
                "artifact_ids": link_map.get(m.id, []),
            }
        )
    return history


@router.post("/messages")
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

    artifact_ids = payload.get("artifact_ids") or []
    if not isinstance(artifact_ids, list):
        artifact_ids = [artifact_ids] if artifact_ids else []
    scope_input = payload.get("scope")
    intent_input = payload.get("intent") or "question"
    artifact_id = artifact_ids[0] if artifact_ids else None

    task_id = None
    if artifact_ids:
        for aid in artifact_ids:
            artifact = session.get(Artifact, aid)
            if not artifact:
                raise HTTPException(status_code=404, detail="Artifact not found")
            task = session.get(Task, artifact.task_id)
            if not task or task.tenant_id != tenant_id or task.purpose_id != purpose_id:
                raise HTTPException(status_code=403, detail="Artifact not in specified purpose")
        if len(artifact_ids) == 1:
            task_id = task.id  # use last fetched task

    if artifact_ids:
        final_scope = ChatScope.MIXED if len(artifact_ids) > 1 else ChatScope.ARTIFACT
    elif scope_input and scope_input in ChatScope._value2member_map_:
        final_scope = ChatScope(scope_input)
    else:
        final_scope = ChatScope.GLOBAL

    intent_enum = (
        ChatIntent(intent_input)
        if intent_input in ChatIntent._value2member_map_
        else ChatIntent.QUESTION
    )

    user_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        artifact_id=artifact_ids[0] if artifact_ids else None,
        task_id=task_id,
        role=ChatRole.USER.value,
        content=text,
        scope=final_scope,
        intent=intent_enum,
    )
    session.add(user_msg)
    for aid in artifact_ids:
        session.add(ChatMessageArtifact(chat_message_id=user_msg.id, artifact_id=aid))
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Failed to save user chat message: %s", e)
        raise HTTPException(status_code=500, detail="Could not save message")

    if user_msg.intent == ChatIntent.APPROVAL:
        for aid in artifact_ids:
            artifact = session.get(Artifact, aid)
            if artifact:
                task = session.get(Task, artifact.task_id)
                if task and task.status != "done":
                    task.status = "done"
                    if task.notes:
                        task.notes = task.notes.replace("awaiting_approval", "approved")
                    else:
                        task.notes = "approved via chat"
                    session.add(task)
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to approve tasks: %s", e)
        try:
            pool.delete(f"pause:{tenant_id}:{purpose_id}")
        except Exception as e:
            logger.error("Failed to clear pause flag: %s", e)
        assistant_content = "Approval confirmed. Continuing with implementation."
    else:
        try:
            paused = bool(pool.get(f"pause:{tenant_id}:{purpose_id}"))
        except Exception as e:  # pragma: no cover - Redis failure
            logger.error("Redis get failed: %s", e)
            paused = False

        assistant_content: str | None = None
        if paused:
            trivial_responses = {"ok", "fine", "okay", "thanks", "passt", "danke"}
            if text.lower() in trivial_responses:
                assistant_content = "Understood, will apply."
            else:
                try:
                    prd_artifact = session.exec(
                        select(Artifact)
                        .where(Artifact.task.has(purpose_id=purpose_id))
                        .where(Artifact.repo_path.ilike("%product_requirements.md"))
                        .order_by(Artifact.created_at.desc())
                    ).first()
                except Exception:
                    prd_artifact = None
                current_prd = ""
                if prd_artifact and prd_artifact.blob:
                    current_prd = prd_artifact.blob.decode("utf-8", errors="ignore")
                updated_prd_md = current_prd + "\n" + text
                target_task_id = None
                if prd_artifact:
                    target_task_id = prd_artifact.task_id
                else:
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
                assistant_content = "Ich arbeite das ein."
                agent_content = (
                    "Hinweis: Überprüfe auch Architektur, Tests und UI-Dokumentation auf "
                    "Konsistenz mit den aktualisierten Anforderungen."
                )
                agent_msg = ChatMessage(
                    tenant_id=tenant_id,
                    purpose_id=purpose_id,
                    artifact_id=artifact_ids[0] if artifact_ids else None,
                    role=ChatRole.AGENT.value,
                    content=agent_content,
                    metadata={"note": "feedback integrated"},
                    scope=ChatScope.ARTIFACT if artifact_ids else ChatScope.GLOBAL,
                    intent=ChatIntent.NOTE,
                )
                session.add(agent_msg)
                for aid in artifact_ids:
                    session.add(ChatMessageArtifact(chat_message_id=agent_msg.id, artifact_id=aid))
        if assistant_content is None:
            messages: list[dict] = []
            sys_content = PROMPT_TEMPLATE.render(project=purpose.name, paused=paused)
            messages.append({"role": "system", "content": sys_content})

            conv_query = select(ChatMessage).where(
                ChatMessage.tenant_id == tenant_id, ChatMessage.purpose_id == purpose_id
            )
            if artifact_ids:
                conv_query = (
                    conv_query.join(ChatMessageArtifact)
                    .where(ChatMessageArtifact.artifact_id.in_(artifact_ids))
                    .distinct()
                )
            else:
                conv_query = conv_query.where(ChatMessage.artifact_id.is_(None))
            conv_history = session.exec(conv_query.order_by(ChatMessage.created_at)).all()
            if not artifact_ids:
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
                if role not in (ChatRole.USER.value, ChatRole.ASSISTANT.value):
                    role = ChatRole.ASSISTANT.value
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
        scope=ChatScope.ARTIFACT if artifact_ids else ChatScope.GLOBAL,
        intent=ChatIntent.NOTE,
    )
    session.add(assistant_msg)
    for aid in artifact_ids:
        session.add(ChatMessageArtifact(chat_message_id=assistant_msg.id, artifact_id=aid))
    try:
        session.commit()
    except Exception as e:  # pragma: no cover - DB failure
        session.rollback()
        logger.error("Failed to save assistant chat message: %s", e)
        raise HTTPException(status_code=500, detail="Could not save response")

    if not artifact_ids:
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
                        if role == ChatRole.USER.value
                        else ("AImar" if role == ChatRole.ASSISTANT.value else "Agent")
                    )
                    conv_text += f"{author}: {m.content}\n"
                prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                try:
                    resp_summary = llm.chat(
                        model="gpt-3.5-turbo",
                        messages=[{"role": ChatRole.USER.value, "content": prompt}],
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
                        if role == ChatRole.USER.value
                        else ("AImar" if role == ChatRole.ASSISTANT.value else "Agent")
                    )
                    conv_text += f"{author}: {m.content}\n"
                prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                try:
                    resp_summary = llm.chat(
                        model="gpt-3.5-turbo",
                        messages=[{"role": ChatRole.USER.value, "content": prompt}],
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

    response = {
        "id": assistant_msg.id,
        "role": assistant_msg.role.value,
        "content": assistant_msg.content,
        "created_at": assistant_msg.created_at.isoformat(),
    }

    suggested_artifact_ids: list[str] = []
    if scope_input == "auto":
        try:
            vector_store = VectorStore()
            results = vector_store.query_vectors(tenant_id, text, top_k=5)
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            results = []
        assigned_ids: list[str] = []
        if results:
            high_thresh = 0.85
            med_thresh = 0.6
            for point in results:
                art_id = getattr(point, "id", None) or (
                    point.payload.get("artifact_id") if hasattr(point, "payload") else None
                )
                if not art_id:
                    continue
                art = session.get(Artifact, art_id)
                if not art or session.get(Task, art.task_id).purpose_id != purpose_id:
                    continue
                score = getattr(point, "score", None) or 0
                if score >= high_thresh:
                    assigned_ids.append(art_id)
                elif score >= med_thresh:
                    suggested_artifact_ids.append(art_id)
            suggested_artifact_ids = [
                aid for aid in suggested_artifact_ids if aid not in assigned_ids
            ]
            if assigned_ids:
                for aid in assigned_ids:
                    session.add(ChatMessageArtifact(chat_message_id=user_msg.id, artifact_id=aid))
                user_msg.scope = ChatScope.MIXED if len(assigned_ids) > 1 else ChatScope.ARTIFACT
                if user_msg.artifact_id is None:
                    user_msg.artifact_id = assigned_ids[0]
                try:
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logger.error("Failed to auto-assign artifacts to message: %s", e)
    if suggested_artifact_ids:
        response["suggested_artifact_ids"] = suggested_artifact_ids
        response["user_message_id"] = user_msg.id

    return response


@router.patch("/messages/{message_id}/tags")
def update_message_tags(
    message_id: str,
    payload: dict,
    session: Session = Depends(get_session),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Update artifact tags for a chat message."""

    msg = session.get(ChatMessage, message_id)
    if not msg or msg.tenant_id != current_tenant.id:
        raise HTTPException(status_code=404, detail="Message not found")

    artifact_ids = payload.get("artifact_ids") or []
    if not isinstance(artifact_ids, list):
        artifact_ids = [artifact_ids] if artifact_ids else []

    session.exec(
        delete(ChatMessageArtifact).where(ChatMessageArtifact.chat_message_id == message_id)
    )
    for aid in artifact_ids:
        session.add(ChatMessageArtifact(chat_message_id=message_id, artifact_id=aid))

    msg.artifact_id = artifact_ids[0] if artifact_ids else None
    msg.scope = (
        ChatScope.MIXED
        if len(artifact_ids) > 1
        else ChatScope.ARTIFACT if artifact_ids else ChatScope.GLOBAL
    )
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Failed to update message tags: %s", e)
        raise HTTPException(status_code=500, detail="Could not update tags")

    return {"status": "ok"}


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
                artifact_ids = msg.get("artifact_ids") or []
                if not isinstance(artifact_ids, list):
                    artifact_ids = [artifact_ids] if artifact_ids else []
                _scope_input = msg.get("scope")
                intent_input = msg.get("intent") or "question"
            except Exception:
                user_text = data.strip()
                artifact_ids = []
                _scope_input = None
                intent_input = "question"
            if not user_text:
                continue

            artifact_id = artifact_ids[0] if artifact_ids else None
            with Session(engine) as session:
                user_msg = ChatMessage(
                    tenant_id=tenant_id,
                    purpose_id=purpose_id,
                    artifact_id=artifact_id,
                    task_id=None,
                    role=ChatRole.USER.value,
                    content=user_text,
                    scope=ChatScope.GLOBAL,
                    intent=(
                        ChatIntent(intent_input)
                        if intent_input in ChatIntent._value2member_map_
                        else ChatIntent.QUESTION
                    ),
                )
                session.add(user_msg)
                for aid in artifact_ids:
                    session.add(ChatMessageArtifact(chat_message_id=user_msg.id, artifact_id=aid))
                try:
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logger.error("Failed to save user chat message: %s", e)
                    await websocket.send_json({"error": "Could not save message"})
                    continue

                if user_msg.intent == ChatIntent.APPROVAL:
                    for aid in artifact_ids:
                        artifact = session.get(Artifact, aid)
                        if artifact:
                            task = session.get(Task, artifact.task_id)
                            if task and task.status != "done":
                                task.status = "done"
                                if task.notes:
                                    task.notes = task.notes.replace("awaiting_approval", "approved")
                                else:
                                    task.notes = "approved via chat"
                                session.add(task)
                    try:
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        logger.error("Failed to approve tasks: %s", e)
                    try:
                        pool.delete(f"pause:{tenant_id}:{purpose_id}")
                    except Exception as e:
                        logger.error("Failed to clear pause flag: %s", e)
                    assistant_msg = ChatMessage(
                        tenant_id=tenant_id,
                        purpose_id=purpose_id,
                        artifact_id=artifact_ids[0] if artifact_ids else None,
                        role=ChatRole.ASSISTANT.value,
                        content="Approval confirmed. Continuing with implementation.",
                        scope=ChatScope.ARTIFACT if artifact_ids else ChatScope.GLOBAL,
                        intent=ChatIntent.NOTE,
                    )
                    session.add(assistant_msg)
                    for aid in artifact_ids:
                        session.add(
                            ChatMessageArtifact(chat_message_id=assistant_msg.id, artifact_id=aid)
                        )
                    try:
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        logger.error("Failed to save approval response message: %s", e)
                    await websocket.send_json(
                        {"role": "assistant", "content": assistant_msg.content}
                    )
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
                        assistant_content = "Understood, will apply."
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
                    if artifact_ids:
                        conv_query = (
                            conv_query.join(ChatMessageArtifact)
                            .where(ChatMessageArtifact.artifact_id.in_(artifact_ids))
                            .distinct()
                        )
                    else:
                        conv_query = conv_query.where(ChatMessage.artifact_id.is_(None))
                    conv_history = session.exec(conv_query.order_by(ChatMessage.created_at)).all()
                    if not artifact_ids:
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
                        if role not in (ChatRole.USER.value, ChatRole.ASSISTANT.value):
                            role = ChatRole.ASSISTANT.value
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
                    scope=ChatScope.ARTIFACT if artifact_ids else ChatScope.GLOBAL,
                    intent=ChatIntent.NOTE,
                )
                session.add(assistant_msg)
                for aid in artifact_ids:
                    session.add(
                        ChatMessageArtifact(chat_message_id=assistant_msg.id, artifact_id=aid)
                    )
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

                if not artifact_ids:
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
                                    if role == ChatRole.USER.value
                                    else ("AImar" if role == ChatRole.ASSISTANT.value else "Agent")
                                )
                                conv_text += f"{author}: {m.content}\n"
                            prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                            try:
                                resp_summary = await run_in_threadpool(
                                    llm.chat,
                                    model="gpt-3.5-turbo",
                                    messages=[{"role": ChatRole.USER.value, "content": prompt}],
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
                                    if role == ChatRole.USER.value
                                    else ("AImar" if role == ChatRole.ASSISTANT.value else "Agent")
                                )
                                conv_text += f"{author}: {m.content}\n"
                            prompt = f"Fasse die folgende Unterhaltung zusammen:\n{conv_text}"
                            try:
                                resp_summary = await run_in_threadpool(
                                    llm.chat,
                                    model="gpt-3.5-turbo",
                                    messages=[{"role": ChatRole.USER.value, "content": prompt}],
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
