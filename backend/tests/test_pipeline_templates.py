import uuid

from sqlmodel import SQLModel, select

from ai_org_backend.db import SessionLocal, engine
from ai_org_backend.models import PipelineTemplate, Purpose, Task, Tenant
from ai_org_backend.services.pipeline_templates import (
    instantiate_pipeline_for_purpose,
    resolve_pipeline_template,
    update_phase_configuration,
)


def test_default_template_instantiation_creates_tasks():
    SQLModel.metadata.create_all(engine)

    tenant_id = f"tenant-{uuid.uuid4().hex[:6]}"
    purpose_name = f"purpose-{uuid.uuid4().hex[:6]}"

    with SessionLocal() as session:
        tenant = Tenant(id=tenant_id, name="Template Test", hashed_password="pw")
        session.add(tenant)
        session.commit()

    phase_slugs: list[str | None] = []
    with SessionLocal() as session:
        template = resolve_pipeline_template(session, tenant_id, None)
        assert template is not None
        phase_count = len(list(template.phases))
        phase_names = [phase.name for phase in template.phases]
        phase_slugs = [getattr(phase, "slug", None) for phase in template.phases]
        purpose = Purpose(
            name=purpose_name,
            tenant_id=tenant_id,
            pipeline_template_id=template.id,
        )
        session.add(purpose)
        session.commit()
        session.refresh(purpose)

    instantiate_pipeline_for_purpose(purpose, template)

    with SessionLocal() as session:
        tasks = session.exec(
            select(Task).where(Task.purpose_id == purpose.id).order_by(Task.created_at)
        ).all()

    assert len(tasks) == phase_count
    descriptions = [t.description for t in tasks]
    for expected in ("Vision Document", "Architecture & Domain Review"):
        assert expected in phase_names
        assert expected in descriptions
    assert "vision" in phase_slugs


def test_update_phase_configuration_clones_for_project_scope():
    SQLModel.metadata.create_all(engine)

    tenant_id = f"tenant-{uuid.uuid4().hex[:6]}"
    purpose_name = f"purpose-{uuid.uuid4().hex[:6]}"

    with SessionLocal() as session:
        tenant = Tenant(id=tenant_id, name="Template Update", hashed_password="pw")
        session.add(tenant)
        session.commit()

    updated_template: PipelineTemplate | None = None
    with SessionLocal() as session:
        template = resolve_pipeline_template(session, tenant_id, None)
        purpose = Purpose(
            name=purpose_name,
            tenant_id=tenant_id,
            pipeline_template_id=template.id if template else None,
        )
        session.add(purpose)
        session.commit()
        session.refresh(purpose)

        assert template is not None
        prd_phase = next(
            phase for phase in template.phases if getattr(phase, "slug", None) == "prd"
        )
        updated_template = update_phase_configuration(
            session,
            purpose=purpose,
            phase_identifier=prd_phase.id,
            updates={"model_name": "gpt-3.5-turbo"},
            scope="purpose",
        )
        session.refresh(purpose)
        assert updated_template.id != template.id
        assert purpose.pipeline_template_id == updated_template.id
        assert any(
            getattr(p, "slug", None) == "prd" and p.model_name == "gpt-3.5-turbo"
            for p in updated_template.phases
        )

    instantiate_pipeline_for_purpose(purpose, updated_template)

