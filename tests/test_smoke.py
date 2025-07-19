# tests/test_smoke.py
from sqlmodel import Session, select
from ai_org_prototype import TaskRepo

def test_create_task(db_session):
    repo = TaskRepo("demo-tenant")
    t = repo.add_task("Test", 10)
    assert t.description == "Test"
