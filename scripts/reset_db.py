from ai_org_backend.db import engine
from sqlmodel import SQLModel

print("⚡ Dropping & recreating all tables…")
SQLModel.metadata.drop_all(engine)
SQLModel.metadata.create_all(engine)
print("✅  Done!")
