import logging
from datetime import datetime
from typing import Any, Iterable, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, exists, not_, or_
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
from ai_org_backend.services.artifact_workflow import integrate_prd_feedback
from ai_org_backend.services.storage import resolve_for_read, register_artefact
from ai_org_backend.services.vector_store import VectorStore
from ai_org_backend.utils import llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])
PROMPT_TEMPLATE = load_template("aimar.j2")


def _coerce_role(role: Optional[str]) -> ChatRole:
    """Coerce any input ('USER'|'user'|None) into ChatRole (defaults to user)."""
    if not role:
        return ChatRole.USER
    try:
        return ChatRole(role.lower())
    except Exception:
        return ChatRole.USER


def _coerce_scope(scope: Optional[str], artifact_ids: Optional[Iterable[str]] = None) -> ChatScope:
    """Map scope strings to ChatScope; 'auto' becomes MIXED if >1 artefact, else ARTIFACT/ GLOBAL."""
    if not scope:
        return ChatScope.GLOBAL
    s = scope.lower()
    if s == "global":
        return ChatScope.GLOBAL
    if s == "artifact":
        return ChatScope.ARTIFACT
    if s == "mixed":
        return ChatScope.MIXED
    if s == "auto":
        count = len(list(artifact_ids or []))
        return (
            ChatScope.MIXED
            if count > 1
            else (ChatScope.ARTIFACT if count == 1 else ChatScope.GLOBAL)
        )
    # fallback
    return ChatScope.GLOBAL


def _extract_metadata_version(
    metadata: Any, artifact_id: str | None = None
) -> int | None:
    """Return an integer version from stored chat message metadata."""

    if not isinstance(metadata, dict):
        return None

    version = metadata.get("version")
    if version is None and artifact_id is not None:
        artifact_versions = metadata.get("artifact_versions")
        if isinstance(artifact_versions, dict):
            version = artifact_versions.get(artifact_id) or artifact_versions.get(
                str(artifact_id)
            )

    if version is None:
        return None

    try:
        return int(version)
    except (TypeError, ValueError):
        return None


def _load_latest_versions(
    session: Session, tenant_id: str, artifact_ids: Iterable[str]
) -> dict[str, int]:
    """Fetch the latest stored version number per artifact for the tenant."""

    latest: dict[str, int] = {}
    for artifact_id in artifact_ids:
        stmt = (
            select(ChatMessage.metadata_)
            .outerjoin(
                ChatMessageArtifact,
                ChatMessageArtifact.chat_message_id == ChatMessage.id,
            )
            .where(ChatMessage.tenant_id == tenant_id)
            .where(
                or_(
                    ChatMessage.artifact_id == artifact_id,
                    ChatMessageArtifact.artifact_id == artifact_id,
                )
            )
            .order_by(ChatMessage.created_at.desc())
        )
        for row in session.exec(stmt):
            metadata = row[0] if isinstance(row, tuple) else row
            version = _extract_metadata_version(metadata, artifact_id)
            if version is not None:
                latest[artifact_id] = version
                break
        else:
            latest.setdefault(artifact_id, 0)
    return latest


def _prepare_feedback_metadata(
    session: Session,
    tenant_id: str,
    artifact_ids: list[str],
    *,
    author: str | None = None,
) -> tuple[dict[str, int], dict[str, Any] | None]:
    """Return the next version assignments and metadata payload for feedback."""

    if not artifact_ids:
        return {}, None

    latest = _load_latest_versions(session, tenant_id, artifact_ids)
    assigned: dict[str, int] = {}
    for artifact_id in artifact_ids:
        assigned[artifact_id] = latest.get(artifact_id, 0) + 1

    metadata: dict[str, Any] = {}
    if author:
        metadata["author"] = author
    if assigned:
        metadata["artifact_versions"] = assigned
        if len(assigned) == 1:
            metadata["version"] = next(iter(assigned.values()))

    return assigned, (metadata or None)


def _metadata_from_versions(
    versions: dict[str, int], *, author: str | None = None
) -> dict[str, Any] | None:
    """Create a metadata payload from explicit version assignments."""

    if not versions:
        return None

    payload: dict[str, Any] = {"artifact_versions": versions}
    if len(versions) == 1:
        payload["version"] = next(iter(versions.values()))
    if author:
        payload["author"] = author
    return payload


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
        artifact_subquery = (
            select(ChatMessageArtifact.chat_message_id)
            .where(ChatMessageArtifact.artifact_id.in_(artifact_id))  # type: ignore[attr-defined]
        )
        messages_query = messages_query.where(ChatMessage.id.in_(artifact_subquery))
    elif scope:
        if scope == ChatScope.GLOBAL:
            subq = select(ChatMessageArtifact.chat_message_id)
            messages_query = messages_query.where(
                not_(ChatMessage.id.in_(subq))  # type: ignore[attr-defined]
            )
        elif scope == ChatScope.ARTIFACT:
            messages_query = messages_query.where(
                exists(
                    select(1).where(
                        ChatMessageArtifact.chat_message_id == ChatMessage.id
                    )
                )
            )
        elif scope == ChatScope.MIXED:
            messages_query = messages_query.where(ChatMessage.scope == ChatScope.MIXED)

    messages_query = messages_query.order_by(
        ChatMessage.created_at.asc(), ChatMessage.id.asc()
    )

    messages = session.exec(messages_query).all()
    out: list[dict] = []
    msg_ids = [m.id for m in messages]
    link_map: dict[str, list[str]] = {}
    if msg_ids:
        links = session.exec(
            select(ChatMessageArtifact.chat_message_id, ChatMessageArtifact.artifact_id).where(
                ChatMessageArtifact.chat_message_id.in_(msg_ids)  # type: ignore[attr-defined]
            )
        ).all()
        for msg_id, art_id in links:
            link_map.setdefault(msg_id, []).append(art_id)

    for m in messages:
        created_at = getattr(m, "created_at", None)
        intent = getattr(m, "intent", None)
        out.append(
            {
                "id": m.id,
                # Always serialize as lowercase string value to match UI enum
                "role": getattr(m.role, "value", str(m.role)).lower(),
                "intent": getattr(intent, "value", intent) if intent else None,
                "content": m.content,
                "author": (
                    current_tenant.name if getattr(m, "role", None) == ChatRole.USER else "AImar"
                ),
                "created_at": created_at.isoformat() if created_at else None,
                "artifact_ids": link_map.get(m.id, []),
                "metadata": getattr(m, "metadata_", None),
            }
        )
    return out


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

    final_scope = _coerce_scope(scope_input, artifact_ids)

    intent_enum = (
        ChatIntent(intent_input)
        if intent_input in ChatIntent._value2member_map_
        else ChatIntent.QUESTION
    )

    author_name = current_tenant.name
    version_state: dict[str, int] = {}
    user_metadata: dict[str, Any] | None = None
    if artifact_ids and intent_enum == ChatIntent.FEEDBACK:
        version_state, user_metadata = _prepare_feedback_metadata(
            session, tenant_id, artifact_ids, author=author_name
        )

    user_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        artifact_id=artifact_ids[0] if artifact_ids else None,
        task_id=task_id,
        role=_coerce_role("USER"),
        content=text,
        scope=final_scope,
        intent=intent_enum,
        metadata=user_metadata,
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

    assistant_content: str | None = None
    response_extras: dict[str, Any] = {}
    if user_msg.intent == ChatIntent.APPROVAL:
        # S4-01/S4-02: Delegate to central approve_artifact() service
        from ai_org_backend.services.approval import (
            AlreadyReleasedError,
            ArtifactNotFoundError,
            approve_artifact,
        )

        artifact_redirect_id: str | None = None
        artifact_redirect_url: str | None = None
        dispatched_followup = False

        # Extract idempotency token from request metadata (S4-03)
        idempotency_token = None
        if user_metadata and isinstance(user_metadata, dict):
            idempotency_token = user_metadata.get("idempotency_token")

        for aid in artifact_ids:
            try:
                result = approve_artifact(
                    aid,
                    tenant_id=tenant_id,
                    purpose_id=purpose_id,
                    idempotency_token=idempotency_token,
                    clear_pause=False,  # We handle pause clearing below
                    session=session,
                )
            except ArtifactNotFoundError:
                continue
            except AlreadyReleasedError:
                raise HTTPException(status_code=409, detail="Artifact already released")

            if result.idempotent_hit or result.previously_released:
                continue

            # ── Vision approved → dispatch PRD generation asynchronously ──
            if result.phase_hint == "vision":
                purpose_obj = session.get(Purpose, purpose_id) if purpose_id else None
                if purpose_obj:
                    existing_prd = session.exec(
                        select(Task)
                        .where(Task.purpose_id == purpose_id)
                        .where(Task.description.ilike("%Product Requirements Document%"))
                    ).first()
                    if not existing_prd:
                        try:
                            prd_task = Task(
                                tenant_id=tenant_id,
                                purpose_id=purpose_id,
                                description="Product Requirements Document",
                                business_value=0.0,
                                tokens_plan=0,
                                purpose_relevance=1.0,
                                status="doing",
                                owner="PO",
                                notes="PRD in progress",
                            )
                            session.add(prd_task)
                            session.flush()
                            session.refresh(prd_task)
                            from ai_org_backend.tasks.celery_app import celery as _celery
                            _celery.send_task(
                                "agent.po",
                                args=[tenant_id, prd_task.id, purpose_id],
                                queue=f"{tenant_id}:po",
                            )
                            dispatched_followup = True
                            logger.info(
                                "Dispatched async PRD generation for task %s (purpose %s)",
                                prd_task.id,
                                purpose_id,
                            )
                        except Exception as exc:
                            logger.error("PRD task creation after vision approval failed: %s", exc)

            elif result.phase_hint in ("prd", "architecture", "review"):
                logger.info(
                    "%s approved for purpose %s – scheduler will advance pipeline",
                    result.phase_hint.upper(),
                    purpose_id,
                )

        # Clear pause flag (unless async follow-up was dispatched)
        if not dispatched_followup:
            try:
                pool.delete(f"pause:{tenant_id}:{purpose_id}")
            except Exception as e:
                logger.error("Failed to clear pause flag: %s", e)
        assistant_content = "Freigabe bestätigt. Die nächste Phase wird vorbereitet."
        response_extras["status"] = "approved"
        if artifact_redirect_id:
            response_extras["artifact_redirect_id"] = artifact_redirect_id
        if artifact_redirect_url:
            response_extras["artifact_redirect_url"] = artifact_redirect_url
    else:
        try:
            paused = bool(pool.get(f"pause:{tenant_id}:{purpose_id}"))
        except Exception as e:  # pragma: no cover - Redis failure
            logger.error("Redis get failed: %s", e)
            paused = False
        if user_msg.intent == ChatIntent.FEEDBACK and artifact_ids:
            response_extras["status"] = "saved"
            trivial_responses = {"ok", "fine", "okay", "thanks", "passt", "danke"}
            if text.lower() in trivial_responses:
                assistant_content = "Understood, will apply."
            else:
                primary_artifact = session.get(Artifact, artifact_ids[0]) if artifact_ids else None
                purpose_obj = session.get(Purpose, purpose_id) if purpose_id else None
                if primary_artifact and purpose_obj:
                    agent_versions = {
                        aid: version_state.get(aid, 0) + 1 for aid in artifact_ids
                    }
                    agent_msg = integrate_prd_feedback(
                        session,
                        artifact=primary_artifact,
                        purpose=purpose_obj,
                        tenant_id=tenant_id,
                        feedback=text,
                        link_to_artifacts=artifact_ids,
                        versions=agent_versions,
                    )
                    if agent_msg is not None and agent_versions:
                        version_state = agent_versions
                assistant_content = assistant_content or "Ich arbeite das im Artefakt ein."
        elif paused and user_msg.intent == ChatIntent.FEEDBACK:
            response_extras["status"] = "saved"
            trivial_responses = {"ok", "fine", "okay", "thanks", "passt", "danke"}
            if text.lower() in trivial_responses:
                assistant_content = "Understood, will apply."
            else:
                assistant_content = "Ich arbeite das ein."
        elif paused:
            response_extras.setdefault("status", "ok")
        if assistant_content is None:
            messages: list[dict] = []
            # Load current artifact content so AImar can reference the document.
            _artifact_title = ""
            _artifact_content = ""
            if artifact_ids:
                _art = session.get(Artifact, artifact_ids[0])
                if _art:
                    _task = session.get(Task, _art.task_id) if _art.task_id else None
                    _artifact_title = (_task.description if _task else "") or ""
                    try:
                        from ai_org_backend.services.storage import resolve_for_read as _rfr
                        _fpath = _rfr(_art.repo_path)
                        _artifact_content = _fpath.read_text(encoding="utf-8", errors="ignore")[:8000]
                    except Exception:
                        _artifact_content = ""
            sys_content = PROMPT_TEMPLATE.render(
                project=purpose.name,
                paused=paused,
                artifact_title=_artifact_title,
                artifact_content=_artifact_content,
            )
            messages.append({"role": "system", "content": sys_content})

            conv_query = select(ChatMessage).where(
                ChatMessage.tenant_id == tenant_id, ChatMessage.purpose_id == purpose_id
            )
            if artifact_ids:
                artifact_subquery = (
                    select(ChatMessageArtifact.chat_message_id)
                    .where(
                        ChatMessageArtifact.artifact_id.in_(artifact_ids)  # type: ignore[attr-defined]
                    )
                )
                conv_query = conv_query.where(ChatMessage.id.in_(artifact_subquery))
            else:
                conv_query = conv_query.where(
                    ChatMessage.artifact_id.is_(None)  # type: ignore[union-attr]
                )
            conv_query = conv_query.order_by(
                ChatMessage.created_at.asc(), ChatMessage.id.asc()
            )
            conv_history = session.exec(conv_query).all()
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

    if user_msg.intent == ChatIntent.FEEDBACK and "status" not in response_extras:
        response_extras["status"] = "saved"
    elif "status" not in response_extras:
        response_extras["status"] = "ok"

    assistant_metadata: dict[str, Any] | None = None
    if artifact_ids and user_msg.intent == ChatIntent.FEEDBACK:
        assistant_versions = {
            aid: version_state.get(aid, 0) + 1 for aid in artifact_ids
        }
        assistant_metadata = _metadata_from_versions(
            assistant_versions, author="AImar"
        )
        version_state = assistant_versions

    assistant_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        artifact_id=artifact_id,
        task_id=task_id,
        role=ChatRole.ASSISTANT,
        content=assistant_content or "",
        scope=ChatScope.ARTIFACT if artifact_ids else ChatScope.GLOBAL,
        intent=ChatIntent.NOTE,
        metadata=assistant_metadata,
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
                ChatMessage.artifact_id.is_(None),  # type: ignore[union-attr]
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

    response: dict[str, Any] = {
        "id": assistant_msg.id,
        "role": assistant_msg.role.value,
        "content": assistant_msg.content,
        "created_at": assistant_msg.created_at.isoformat(),
        "intent": assistant_msg.intent.value,
    }

    response.update(response_extras)

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
                    role=_coerce_role("USER"),
                    content=user_text,
                    scope=_coerce_scope(_scope_input, artifact_ids),
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
                    # S-Sprint2 Fix #5: Route through centralized approve_artifact()
                    from ai_org_backend.services.approval import (
                        approve_artifact as _ws_approve,
                        ArtifactNotFoundError as _WSArtNotFound,
                        AlreadyReleasedError as _WSAlreadyReleased,
                    )
                    for aid in artifact_ids:
                        try:
                            _ws_approve(
                                aid,
                                tenant_id=tenant_id,
                                purpose_id=purpose_id,
                                session=session,
                            )
                        except (_WSArtNotFound, _WSAlreadyReleased):
                            continue
                        except Exception as exc:
                            logger.error(
                                "[S2-#5] approve_artifact failed for %s: %s", aid, exc
                            )
                            continue
                    try:
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        logger.error("Failed to commit approval: %s", e)
                    assistant_msg = ChatMessage(
                        tenant_id=tenant_id,
                        purpose_id=purpose_id,
                        artifact_id=artifact_ids[0] if artifact_ids else None,
                        role=ChatRole.ASSISTANT,
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
                        {
                            "role": ChatRole.ASSISTANT.value,
                            "content": assistant_msg.content,
                        }
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
                                .where(Artifact.repo_path.ilike("%product_requirements_document.md"))  # type: ignore[attr-defined]
                                .order_by(desc(Artifact.created_at))
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
                                        Task.description.ilike("%Product Requirements Document%")  # type: ignore[attr-defined]
                                    )
                                ).first()
                                target_task_id = prd_task.id if prd_task else None
                            if target_task_id:
                                register_artefact(
                                    target_task_id,
                                    updated_prd_md.encode("utf-8"),
                                    filename=(
                                        prd_artifact.repo_path
                                        if prd_artifact
                                        else "requirements/product_requirements_document.md"
                                    ),
                                    media_type=(
                                        prd_artifact.media_type if prd_artifact else "text/markdown"
                                    ),
                                    allow_overwrite=True,
                                )
                                # S-Sprint2 Fix #4: Invalidate & redispatch after WS feedback
                                try:
                                    from ai_org_backend.services.feedback_loop import (
                                        cascade_invalidation,
                                        redispatch_agent,
                                    )
                                    _inv = cascade_invalidation(
                                        target_task_id, purpose_id=purpose_id,
                                    )
                                    for _inv_tid in _inv.invalidated_task_ids:
                                        redispatch_agent(
                                            _inv_tid, tenant_id=tenant_id,
                                        )
                                except Exception as _inv_exc:
                                    logger.warning(
                                        "[S2-#4] WS feedback invalidation/redispatch failed: %s",
                                        _inv_exc,
                                    )
                        except Exception as e:
                            logger.error("PRD update failed: %s", e)
                        assistant_content = "Ich arbeite das ein."

                if assistant_content is None:
                    messages: list[dict] = []
                    # Load artifact content for AImar context awareness.
                    _ws_art_title = ""
                    _ws_art_content = ""
                    if artifact_ids:
                        _ws_art = session.get(Artifact, artifact_ids[0])
                        if _ws_art:
                            _ws_task = session.get(Task, _ws_art.task_id) if _ws_art.task_id else None
                            _ws_art_title = (_ws_task.description if _ws_task else "") or ""
                            try:
                                from ai_org_backend.services.storage import resolve_for_read as _rfr2
                                _ws_fpath = _rfr2(_ws_art.repo_path)
                                _ws_art_content = _ws_fpath.read_text(encoding="utf-8", errors="ignore")[:8000]
                            except Exception:
                                _ws_art_content = ""
                    sys_content = PROMPT_TEMPLATE.render(
                        project=project_name,
                        paused=paused,
                        artifact_title=_ws_art_title,
                        artifact_content=_ws_art_content,
                    )
                    messages.append({"role": "system", "content": sys_content})
                    conv_query = select(ChatMessage).where(
                        ChatMessage.tenant_id == tenant_id,
                        ChatMessage.purpose_id == purpose_id,
                    )
                    if artifact_ids:
                        artifact_subquery = (
                            select(ChatMessageArtifact.chat_message_id)
                            .where(
                                ChatMessageArtifact.artifact_id.in_(artifact_ids)  # type: ignore[attr-defined]
                            )
                        )
                        conv_query = conv_query.where(ChatMessage.id.in_(artifact_subquery))
                    else:
                        conv_query = conv_query.where(
                            ChatMessage.artifact_id.is_(None)  # type: ignore[union-attr]
                        )
                    conv_query = conv_query.order_by(
                        ChatMessage.created_at.asc(), ChatMessage.id.asc()
                    )
                    conv_history = session.exec(conv_query).all()
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
                    role=ChatRole.ASSISTANT,
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
                        "role": ChatRole.ASSISTANT.value,
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
                            ChatMessage.artifact_id.is_(None),  # type: ignore[union-attr]
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


# ──────────────────────────────────────────────────────────────────────
# S6-#10.2: WebSocket endpoint for real-time status updates
# ──────────────────────────────────────────────────────────────────────

@ws_router.websocket("/status/{purpose_id}")
async def websocket_status(websocket: WebSocket, purpose_id: str):
    """S6-#10.2: Real-time status push for a purpose.

    Sends task/phase status updates every 2 seconds to the frontend,
    replacing the 6-second HTTP polling pattern.

    Protocol:
    - Client connects with ?token=<jwt>
    - Server pushes JSON status frames: {tasks: [...], paused, budget_left}
    - Client can send {"action": "ping"} to keep alive
    """
    import asyncio

    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        from ai_org_backend.api.dependencies import decode_token
        payload = decode_token(token)
        tenant_id = payload.get("tenant_id") or payload.get("sub")
    except Exception:
        await websocket.close(code=1008)
        return

    if not tenant_id:
        await websocket.close(code=1008)
        return

    logger.info("[S6-#10.2] Status WS connected: purpose=%s tenant=%s", purpose_id, tenant_id)

    try:
        while True:
            # Build status snapshot
            try:
                with Session(engine) as session:
                    tasks = session.exec(
                        select(Task).where(
                            Task.purpose_id == purpose_id,
                            Task.tenant_id == tenant_id,
                        )
                    ).all()
                    tasks_data = [
                        {
                            "id": t.id,
                            "status": t.status,
                            "description": t.description[:100] if t.description else "",
                            "owner": t.owner,
                            "agent_role": t.agent_role,
                            "pipeline_phase_id": t.pipeline_phase_id if hasattr(t, "pipeline_phase_id") else None,
                        }
                        for t in tasks
                    ]

                paused = False
                budget_left = 500.0
                try:
                    from ai_org_backend.redis_client import DEFAULT_BUDGET, pool as redis_pool
                    paused = bool(redis_pool.get(f"pause:{tenant_id}:{purpose_id}"))
                    budget_left = float(redis_pool.get(f"budget:{tenant_id}:{purpose_id}") or DEFAULT_BUDGET)
                except Exception:
                    pass

                await websocket.send_json({
                    "type": "status_update",
                    "purpose_id": purpose_id,
                    "tasks": tasks_data,
                    "paused": paused,
                    "budget_left": budget_left,
                })

            except Exception as exc:
                logger.warning("[S6-#10.2] Status push error: %s", exc)

            # Wait 2 seconds or receive a client message
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                # Client can send ping to keep alive
                if msg:
                    import json as _json
                    try:
                        data = _json.loads(msg)
                        if data.get("action") == "close":
                            break
                    except Exception:
                        pass
            except asyncio.TimeoutError:
                pass  # normal — push next status frame

    except WebSocketDisconnect:
        logger.info("[S6-#10.2] Status WS disconnected: purpose=%s", purpose_id)
    except Exception as exc:
        logger.error("[S6-#10.2] Status WS error: %s", exc)
