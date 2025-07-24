from ai_org_backend.db import engine
from sqlmodel import SQLModel
from ai_org_backend.models import Tenant, Task, Artifact, TaskDependency, Purpose

print("⚡ Dropping & recreating all tables…")
#SQLModel.metadata.drop_all(engine)
SQLModel.metadata.create_all(engine)
print("✅  Done!")
