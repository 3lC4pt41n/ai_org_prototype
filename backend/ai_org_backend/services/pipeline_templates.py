"""Helpers for resolving and instantiating pipeline blueprints from the DB."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, Mapping, MutableMapping, Optional

from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import DetachedInstanceError
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import PipelinePhase, PipelineTemplate, Purpose, Task
from ai_org_backend.repo import Repo


DEFAULT_TEMPLATE_NAME = "Standard Pipeline"
DEFAULT_TEMPLATE_DESCRIPTION = (
    "Default end-to-end pipeline covering vision, requirements, architecture "
    "and implementation planning."
)
DEFAULT_PHASES: list[dict[str, object]] = [
    {
        "name": "Vision Document",
        "prompt_template": "vision.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 2000,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
    },
    {
        "name": "Product Requirements Document",
        "prompt_template": "requirements.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 3500,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
    },
    {
        "name": "Architecture Blueprint",
        "prompt_template": "architect.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 4000,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
    },
    {
        "name": "Architecture & Domain Review",
        "agent_role": "reviewer",
        "prompt_template": "review.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 1500,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
        "requires_approval": True,
    },
    {
        "name": "Implementation Plan",
        "agent_role": "planner",
        "prompt_template": "planner.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 3000,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
    },
]


def _safe_task_id(task: Optional[Task]) -> Optional[str]:
    """Return the identifier for a potentially detached task instance."""

    if not task:
        return None
    task_id = task.__dict__.get("id")
    if task_id:
        return str(task_id)
    try:
        return task.id  # type: ignore[attr-defined]
    except DetachedInstanceError:
        return None


def _ensure_default_template(session: Session) -> PipelineTemplate:
    """Create the global default template if it does not yet exist."""

    template = session.exec(
        select(PipelineTemplate)
        .where(
            PipelineTemplate.tenant_id.is_(None),
            PipelineTemplate.is_default.is_(True),
        )
        .options(selectinload(PipelineTemplate.phases))
    ).first()

    if template and template.phases:
        template.phases  # ensure relationship is loaded
        return template

    if not template:
        template = PipelineTemplate(
            name=DEFAULT_TEMPLATE_NAME,
            description=DEFAULT_TEMPLATE_DESCRIPTION,
            tenant_id=None,
            is_default=True,
        )
        session.add(template)
        session.flush()

    if not template.phases:
        predecessor_id: Optional[str] = None
        for position, phase_def in enumerate(DEFAULT_PHASES, start=1):
            phase = PipelinePhase(
                pipeline_template_id=template.id,
                name=str(phase_def["name"]),
                position=position,
                predecessor_id=predecessor_id,
                agent_role=str(phase_def.get("agent_role", "") or "") or None,
                prompt_template=str(phase_def.get("prompt_template", "") or "")
                or None,
                model_name=str(phase_def.get("model_name", "") or "") or None,
                tokens_plan_default=int(phase_def.get("tokens_plan_default", 0)),
                business_value_default=float(
                    phase_def.get("business_value_default", 1.0)
                ),
                purpose_relevance_default=float(
                    phase_def.get("purpose_relevance_default", 1.0)
                ),
                requires_approval=bool(phase_def.get("requires_approval", False)),
            )
            session.add(phase)
            session.flush()
            predecessor_id = phase.id

    session.commit()
    session.refresh(template)
    template.phases  # trigger load before leaving session scope
    return template


def resolve_pipeline_template(
    session: Session, tenant_id: str, template_id: Optional[str] = None
) -> Optional[PipelineTemplate]:
    """Return the pipeline template selected by the tenant or fall back to default."""

    _ensure_default_template(session)

    query = (
        select(PipelineTemplate)
        .options(selectinload(PipelineTemplate.phases))
        .order_by(PipelineTemplate.created_at)
    )

    if template_id:
        template = session.exec(
            query.where(
                PipelineTemplate.id == template_id,
                or_(
                    PipelineTemplate.tenant_id == tenant_id,
                    PipelineTemplate.tenant_id.is_(None),
                ),
            )
        ).first()
        if template:
            template.phases
            return template

    template = session.exec(
        query.where(
            PipelineTemplate.tenant_id == tenant_id,
            PipelineTemplate.is_default.is_(True),
        )
    ).first()
    if template:
        template.phases
        return template

    template = session.exec(
        query.where(
            PipelineTemplate.tenant_id.is_(None),
            PipelineTemplate.is_default.is_(True),
        )
    ).first()
    if template:
        template.phases
        return template

    template = session.exec(query.where(PipelineTemplate.tenant_id.is_(None))).first()
    if template:
        template.phases
    return template


def instantiate_pipeline_for_purpose(
    purpose: Purpose,
    template: Optional[PipelineTemplate],
    overrides: Optional[Mapping[str, Mapping[str, object]]] = None,
) -> list[Task]:
    """Create or update tasks for the provided purpose from the template blueprint."""

    if not template:
        return []

    overrides = overrides or {}
    repo = Repo(purpose.tenant_id)

    with Session(engine) as session:
        existing_tasks = session.exec(
            select(Task).where(Task.purpose_id == purpose.id)
        ).all()

    tasks_by_phase: MutableMapping[str, Task] = {
        t.pipeline_phase_id: t for t in existing_tasks if t.pipeline_phase_id
    }
    desc_lookup: Dict[str, Task] = {
        (t.description or "").lower(): t for t in existing_tasks
    }

    created: list[Task] = []
    template_id: Optional[str] = None
    if template is not None:
        template_id = template.__dict__.get("id")
        if not template_id:
            try:
                template_id = template.id  # type: ignore[attr-defined]
            except DetachedInstanceError:
                template_id = None

    if not template_id:
        template_id = purpose.pipeline_template_id

    loaded_template = template
    if template_id:
        with Session(engine) as session:
            loaded_template = session.exec(
                select(PipelineTemplate)
                .where(PipelineTemplate.id == template_id)
                .options(selectinload(PipelineTemplate.phases))
            ).first() or loaded_template

    if not loaded_template:
        return []

    try:
        phase_iterable = list(loaded_template.phases)  # type: ignore[attr-defined]
    except DetachedInstanceError:
        phase_iterable = []

    sorted_phases = sorted(
        phase_iterable,
        key=lambda ph: (ph.position, ph.created_at or datetime.min),
    )

    for phase in sorted_phases:
        task = tasks_by_phase.get(phase.id) or desc_lookup.get(phase.name.lower())
        override = overrides.get(phase.id) or overrides.get(phase.name)

        desired_tokens = int(
            override.get("tokens_plan", phase.tokens_plan_default)
            if override
            else phase.tokens_plan_default
        )
        desired_bv = float(
            override.get("business_value", phase.business_value_default)
            if override
            else phase.business_value_default
        )
        desired_relevance = float(
            override.get("purpose_relevance", phase.purpose_relevance_default)
            if override
            else phase.purpose_relevance_default
        )
        desired_model = (
            override.get("model_name", phase.model_name) if override else phase.model_name
        )
        desired_prompt = (
            override.get("prompt_template", phase.prompt_template)
            if override
            else phase.prompt_template
        )
        desired_role = (
            override.get("agent_role", phase.agent_role) if override else phase.agent_role
        )
        desired_requires_approval = bool(
            override.get("requires_approval", phase.requires_approval)
            if override
            else phase.requires_approval
        )

        if task:
            update_fields: Dict[str, object] = {}
            if task.pipeline_phase_id != phase.id:
                update_fields["pipeline_phase_id"] = phase.id
            if task.tokens_plan != desired_tokens:
                update_fields["tokens_plan"] = desired_tokens
            if task.business_value != desired_bv:
                update_fields["business_value"] = desired_bv
            if task.purpose_relevance != desired_relevance:
                update_fields["purpose_relevance"] = desired_relevance
            if task.agent_role != desired_role:
                update_fields["agent_role"] = desired_role
            if task.model_name != desired_model:
                update_fields["model_name"] = desired_model
            if task.prompt_template != desired_prompt:
                update_fields["prompt_template"] = desired_prompt
            if task.requires_approval != desired_requires_approval:
                update_fields["requires_approval"] = desired_requires_approval
            if update_fields:
                task_id = _safe_task_id(task)
                if task_id:
                    task = repo.update(task_id, **update_fields)
            tasks_by_phase[phase.id] = task
            continue

        depends: Iterable[str] | None = None
        if phase.predecessor_id:
            predecessor_task = tasks_by_phase.get(phase.predecessor_id)
            predecessor_task_id = _safe_task_id(predecessor_task)
            if predecessor_task_id:
                depends = [predecessor_task_id]

        task = repo.add_task(
            purpose_id=purpose.id,
            description=phase.name,
            business_value=desired_bv,
            tokens_plan=desired_tokens,
            purpose_relevance=desired_relevance,
            depends_on=depends,
            pipeline_phase_id=phase.id,
            agent_role=desired_role if desired_role else None,
            model_name=desired_model if desired_model else None,
            prompt_template=desired_prompt if desired_prompt else None,
            requires_approval=desired_requires_approval,
        )
        tasks_by_phase[phase.id] = task
        created.append(task)

    return created

