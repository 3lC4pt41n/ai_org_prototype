import uuid

from sqlmodel import SQLModel, select

from ai_org_backend.db import SessionLocal, engine
from ai_org_backend.models import Purpose, Task, Tenant
from ai_org_backend.services.pipeline_templates import (
    instantiate_pipeline_for_purpose,
    resolve_pipeline_template,
)


def test_default_template_instantiation_creates_tasks():
    SQLModel.metadata.create_all(engine)

    tenant_id = f"tenant-{uuid.uuid4().hex[:6]}"
    purpose_name = f"purpose-{uuid.uuid4().hex[:6]}"

    with SessionLocal() as session:
        tenant = Tenant(id=tenant_id, name="Template Test", hashed_password="pw")
        session.add(tenant)
        session.commit()

    with SessionLocal() as session:
        template = resolve_pipeline_template(session, tenant_id, None)
        assert template is not None
        phase_count = len(list(template.phases))
        phase_names = [phase.name for phase in template.phases]
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
