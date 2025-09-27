"""Helpers for resolving and instantiating pipeline blueprints from the DB."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Dict, Iterable, Mapping, MutableMapping, Optional

from sqlalchemy import or_, update
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.exc import DetachedInstanceError
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import (
    PipelinePhase,
    PipelineTemplate,
    Purpose,
    Task,
    TenantPromptAssignment,
)
from ai_org_backend.repo import Repo


DEFAULT_TEMPLATE_NAME = "Standard Pipeline"
DEFAULT_TEMPLATE_DESCRIPTION = (
    "Default end-to-end pipeline covering vision, requirements, architecture "
    "and implementation planning."
)
DEFAULT_PHASES: list[dict[str, object]] = [
    {
        "slug": "vision",
        "name": "Vision Document",
        "prompt_template": "vision.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 2000,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
    },
    {
        "slug": "prd",
        "name": "Product Requirements Document",
        "agent_role": "po",
        "prompt_template": "requirements.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 3500,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
        "depends_on": "vision",
    },
    {
        "slug": "architecture",
        "name": "Architecture Blueprint",
        "prompt_template": "architect.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 4000,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
        "depends_on": "prd",
    },
    {
        "slug": "architecture_review",
        "name": "Architecture & Domain Review",
        "agent_role": "reviewer",
        "prompt_template": "review.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 1500,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
        "requires_approval": True,
        "depends_on": "architecture",
    },
    {
        "slug": "implementation",
        "name": "Implementation Plan",
        "agent_role": "planner",
        "prompt_template": "planner.j2",
        "model_name": "gpt-4",
        "tokens_plan_default": 3000,
        "business_value_default": 1.0,
        "purpose_relevance_default": 1.0,
        "depends_on": "architecture_review",
    },
]


def _slugify(value: str) -> str:
    """Convert a human readable phase name into a slug identifier."""

    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "phase"


def _phase_to_dict(phase: PipelinePhase) -> dict[str, object]:
    return {
        "id": phase.id,
        "name": phase.name,
        "slug": getattr(phase, "slug", None),
        "position": phase.position,
        "predecessor_id": phase.predecessor_id,
        "agent_role": phase.agent_role,
        "prompt_template": phase.prompt_template,
        "model_name": phase.model_name,
        "tokens_plan_default": phase.tokens_plan_default,
        "business_value_default": phase.business_value_default,
        "purpose_relevance_default": phase.purpose_relevance_default,
        "requires_approval": phase.requires_approval,
        "created_at": phase.created_at.isoformat() if phase.created_at else None,
        "updated_at": phase.updated_at.isoformat() if phase.updated_at else None,
    }


def template_to_dict(template: PipelineTemplate) -> dict[str, object]:
    """Serialize a template with its phases into primitive types for JSON."""

    try:
        phases = list(template.phases)  # type: ignore[attr-defined]
    except DetachedInstanceError:
        phases = []

    phases_sorted = sorted(
        phases,
        key=lambda phase: (phase.position, phase.created_at or datetime.min),
    )
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "tenant_id": template.tenant_id,
        "is_default": template.is_default,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        "phases": [_phase_to_dict(phase) for phase in phases_sorted],
    }


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
        needs_slug_update = False
        for phase in template.phases:
            if not getattr(phase, "slug", None):
                phase.slug = _slugify(phase.name)
                needs_slug_update = True
        if needs_slug_update:
            session.add(template)
            session.commit()
            session.refresh(template)
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
        created: Dict[str, PipelinePhase] = {}
        for position, phase_def in enumerate(DEFAULT_PHASES, start=1):
            slug = str(phase_def.get("slug") or _slugify(str(phase_def["name"])))
            depends_on = str(phase_def.get("depends_on") or "") or None
            predecessor_id = (
                created[depends_on].id if depends_on and depends_on in created else None
            )
            phase = PipelinePhase(
                pipeline_template_id=template.id,
                name=str(phase_def["name"]),
                slug=slug,
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
            created[slug] = phase

    session.commit()
    session.refresh(template)
    template.phases  # trigger load before leaving session scope
    return template


def list_templates_for_tenant(session: Session, tenant_id: str) -> list[PipelineTemplate]:
    """Return all templates visible for a tenant including the global default."""

    _ensure_default_template(session)

    templates = session.exec(
        select(PipelineTemplate)
        .options(selectinload(PipelineTemplate.phases))
        .where(
            or_(
                PipelineTemplate.tenant_id == tenant_id,
                PipelineTemplate.tenant_id.is_(None),
            )
        )
        .order_by(
            PipelineTemplate.tenant_id.is_(None).desc(),
            PipelineTemplate.is_default.desc(),
            PipelineTemplate.created_at,
        )
    ).all()
    for template in templates:
        template.phases  # eagerly load for callers outside of session scope
    return templates


def _load_template(session: Session, template_id: str) -> Optional[PipelineTemplate]:
    if not template_id:
        return None
    template = session.exec(
        select(PipelineTemplate)
        .options(selectinload(PipelineTemplate.phases))
        .where(PipelineTemplate.id == template_id)
    ).first()
    if template:
        template.phases
    return template


def clone_template(
    session: Session,
    template: PipelineTemplate,
    *,
    tenant_id: Optional[str],
    is_default: bool = False,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> PipelineTemplate:
    """Duplicate a template including its phases."""

    new_template = PipelineTemplate(
        name=name or template.name,
        description=description or template.description,
        tenant_id=tenant_id,
        is_default=is_default,
    )
    session.add(new_template)
    session.flush()

    try:
        phases = list(template.phases)  # type: ignore[attr-defined]
    except DetachedInstanceError:
        phases = []

    old_to_new: Dict[str, PipelinePhase] = {}
    for position, old_phase in enumerate(
        sorted(phases, key=lambda ph: (ph.position, ph.created_at or datetime.min)),
        start=1,
    ):
        slug = getattr(old_phase, "slug", None) or _slugify(old_phase.name)
        new_phase = PipelinePhase(
            pipeline_template_id=new_template.id,
            name=old_phase.name,
            slug=slug,
            position=position,
            agent_role=old_phase.agent_role,
            prompt_template=old_phase.prompt_template,
            model_name=old_phase.model_name,
            tokens_plan_default=old_phase.tokens_plan_default,
            business_value_default=old_phase.business_value_default,
            purpose_relevance_default=old_phase.purpose_relevance_default,
            requires_approval=old_phase.requires_approval,
        )
        session.add(new_phase)
        session.flush()
        old_to_new[old_phase.id] = new_phase

    for old_phase in phases:
        if old_phase.predecessor_id and old_phase.predecessor_id in old_to_new:
            cloned = old_to_new[old_phase.id]
            cloned.predecessor_id = old_to_new[old_phase.predecessor_id].id
            session.add(cloned)

    session.flush()
    return _load_template(session, new_template.id) or new_template


def ensure_template_for_purpose(session: Session, purpose: Purpose) -> PipelineTemplate:
    """Resolve and attach a template for the purpose if missing."""

    template = _load_template(session, purpose.pipeline_template_id or "")
    if template:
        return template

    template = resolve_pipeline_template(session, purpose.tenant_id, purpose.pipeline_template_id)
    if not template:
        template = _ensure_default_template(session)
    if purpose.pipeline_template_id != template.id:
        purpose.pipeline_template_id = template.id
        session.add(purpose)
        session.commit()
        session.refresh(purpose)
    return template


def update_phase_configuration(
    session: Session,
    *,
    purpose: Purpose,
    phase_identifier: str,
    updates: Mapping[str, object],
    scope: str = "purpose",
) -> PipelineTemplate:
    """Apply configuration changes to a pipeline phase and return resulting template."""

    template = ensure_template_for_purpose(session, purpose)
    if not template:
        raise ValueError("No pipeline template available")

    try:
        source_phase = next(
            phase
            for phase in template.phases  # type: ignore[attr-defined]
            if phase.id == phase_identifier or getattr(phase, "slug", None) == phase_identifier
        )
    except (StopIteration, DetachedInstanceError):
        raise ValueError("Requested pipeline phase not found")

    phase_slug = getattr(source_phase, "slug", None) or _slugify(source_phase.name)

    target_template = template
    scope_normalized = (scope or "purpose").lower()

    def _needs_clone(current_template: PipelineTemplate) -> bool:
        if current_template.tenant_id is None:
            return True
        if scope_normalized == "purpose":
            return True
        if scope_normalized == "tenant_default" and not current_template.is_default:
            return True
        return False

    if _needs_clone(template):
        target_template = clone_template(
            session,
            template,
            tenant_id=purpose.tenant_id,
            is_default=scope_normalized == "tenant_default",
        )
        purpose.pipeline_template_id = target_template.id
        session.add(purpose)
        session.flush()
    elif scope_normalized == "tenant_default":
        # Ensure flag is set when updating an existing tenant template.
        target_template.is_default = True
        session.add(target_template)

    if scope_normalized == "tenant_default":
        session.execute(
            update(PipelineTemplate)
            .where(
                PipelineTemplate.tenant_id == purpose.tenant_id,
                PipelineTemplate.id != target_template.id,
            )
            .values(is_default=False)
        )

    target_phase = next(
        phase
        for phase in target_template.phases  # type: ignore[attr-defined]
        if phase.id == phase_identifier or getattr(phase, "slug", None) == phase_slug
    )

    if "model_name" in updates:
        target_phase.model_name = str(updates["model_name"] or "") or None
    if "tokens_plan_default" in updates:
        target_phase.tokens_plan_default = int(updates["tokens_plan_default"] or 0)
    if "prompt_template" in updates:
        target_phase.prompt_template = str(updates["prompt_template"] or "") or None
    if "agent_role" in updates:
        target_phase.agent_role = str(updates["agent_role"] or "") or None
    if "requires_approval" in updates:
        target_phase.requires_approval = bool(updates["requires_approval"])

    target_phase.updated_at = datetime.utcnow()
    session.add(target_phase)
    session.commit()

    refreshed = _load_template(session, target_template.id)
    return refreshed or target_template


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

    assignment_prompts: Dict[str, str] = {}

    with Session(engine) as session:
        existing_tasks = session.exec(
            select(Task).where(Task.purpose_id == purpose.id)
        ).all()
        if purpose.tenant_id:
            assignments = session.exec(
                select(TenantPromptAssignment).where(
                    TenantPromptAssignment.tenant_id == purpose.tenant_id
                )
            ).all()
            assignment_prompts = {
                assignment.phase_slug: assignment.prompt_template_id
                for assignment in assignments
                if assignment.prompt_template_id
            }

    tasks_by_phase: MutableMapping[str, Task] = {
        t.pipeline_phase_id: t for t in existing_tasks if t.pipeline_phase_id
    }
    desc_lookup: Dict[str, Task] = {
        (t.description or "").lower(): t for t in existing_tasks
    }
    slug_lookup: Dict[str, Task] = {}
    for task in existing_tasks:
        if task.description:
            slug_lookup[_slugify(task.description)] = task

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
        phase_slug = getattr(phase, "slug", None) or _slugify(phase.name)
        task = (
            tasks_by_phase.get(phase.id)
            or desc_lookup.get(phase.name.lower())
            or slug_lookup.get(phase_slug)
        )
        override = (
            overrides.get(phase.id)
            or overrides.get(phase_slug)
            or overrides.get(phase.name)
        )

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
        assignment_prompt = assignment_prompts.get(phase_slug)
        desired_prompt = phase.prompt_template
        if override and "prompt_template" in override:
            desired_prompt = str(override.get("prompt_template") or "") or None
        elif assignment_prompt is not None:
            desired_prompt = assignment_prompt or None
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
            if phase_slug and task:
                slug_lookup[phase_slug] = task
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
        if phase_slug:
            slug_lookup[phase_slug] = task
        created.append(task)

    return created

