import importlib
import os
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, select

from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _reload_modules():
    import ai_org_backend.api.dependencies as dependencies
    import ai_org_backend.db as db
    import ai_org_backend.api.purposes as purposes_module
    import ai_org_backend.settings as settings_module

    importlib.reload(db)
    importlib.reload(dependencies)
    importlib.reload(settings_module)
    importlib.reload(purposes_module)
    return db, dependencies, purposes_module, settings_module


def _create_app(purposes_module):
    app = FastAPI()
    app.include_router(purposes_module.router)
    return app


def _override_tenant(app, tenant, dependencies):
    app.dependency_overrides[dependencies.get_current_tenant] = lambda: tenant


def _prepare_data(engine, *, include_feedback: bool = True):
    from ai_org_backend.models import (
        Artifact,
        ArtifactFeedback,
        Feedback,
        FeedbackType,
        Purpose,
        Task,
        TaskDependency,
        Tenant,
    )
    from ai_org_backend.models.chat import (
        ChatIntent,
        ChatMessage,
        ChatMessageArtifact,
        ChatRole,
        ChatScope,
        ChatThreadContext,
    )

    tenant = Tenant(id="tenant1", name="Tenant", hashed_password="x")
    purpose = Purpose(id="purpose1", tenant_id=tenant.id, name="Purpose")

    task1 = Task(
        id="task1",
        tenant_id=tenant.id,
        purpose_id=purpose.id,
        description="Task One",
        status="todo",
    )
    task2 = Task(
        id="task2",
        tenant_id=tenant.id,
        purpose_id=purpose.id,
        description="Task Two",
        status="doing",
    )
    dependency = TaskDependency(from_id=task1.id, to_id=task2.id, dependency_type="FINISH_START")

    artifact = Artifact(
        id="artifact1",
        task_id=task1.id,
        repo_path="requirements/doc.md",
        media_type="text/markdown",
        size=0,
        sha256="0" * 64,
    )
    artifact_feedback = ArtifactFeedback(
        id="fb1",
        artifact_id=artifact.id,
        tenant_id=tenant.id,
        content="Looks good",
    )

    chat_message = ChatMessage(
        id="chat1",
        tenant_id=tenant.id,
        purpose_id=purpose.id,
        task_id=task1.id,
        artifact_id=artifact.id,
        role=ChatRole.USER,
        scope=ChatScope.GLOBAL,
        intent=ChatIntent.NOTE,
        content="Hello",
    )
    chat_link = ChatMessageArtifact(chat_message_id=chat_message.id, artifact_id=artifact.id)
    thread_context = ChatThreadContext(purpose_id=purpose.id, summary="Summary")
    feedback = None
    if include_feedback:
        feedback = Feedback(
            tenant_id=tenant.id,
            purpose_id=purpose.id,
            type=FeedbackType.PRD,
            text="Feedback",
        )

    with Session(engine, expire_on_commit=False) as session:
        session.add(tenant)
        session.add(purpose)
        session.add(task1)
        session.add(task2)
        session.add(dependency)
        session.add(artifact)
        session.add(artifact_feedback)
        session.add(chat_message)
        session.add(chat_link)
        session.add(thread_context)
        if feedback is not None:
            session.add(feedback)
        session.commit()

    return tenant, purpose, artifact, [task1.id, task2.id]


def test_delete_purpose_removes_related_records(monkeypatch, tmp_path):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    monkeypatch.setitem(os.environ, "REDIS_URL", "redis://localhost:6379/0")

    db_file = tmp_path / "test.db"
    monkeypatch.setitem(os.environ, "DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setitem(os.environ, "WORKSPACE_DIR", str(tmp_path / "workspace"))

    db, dependencies, purposes_module, settings_module = _reload_modules()

    SQLModel.metadata.create_all(db.engine)

    tenant, purpose, artifact, task_ids = _prepare_data(db.engine, include_feedback=False)

    removed_from_graph: dict[str, list[str]] = {}
    monkeypatch.setattr(
        purposes_module.graph_sync,
        "remove_tasks",
        lambda ids: removed_from_graph.setdefault("ids", list(ids)),
    )

    removed_purposes: list[str] = []
    monkeypatch.setattr(
        purposes_module.graph_sync,
        "remove_purpose",
        lambda pid: removed_purposes.append(pid),
    )

    retracted: list[str] = []

    def _retract(artifact_id: str, remove_from_neo4j: bool = False):
        retracted.append(artifact_id)

    monkeypatch.setattr(purposes_module, "retract_artifact", _retract)

    dummy_pool = SimpleNamespace(deleted_keys=[])

    def _delete_key(key: str):
        dummy_pool.deleted_keys.append(key)

    dummy_pool.delete = _delete_key
    monkeypatch.setattr(purposes_module, "pool", dummy_pool)

    workspace_root = settings_module.settings.workspace_dir
    target_dir = workspace_root / tenant.id / purpose.id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "dummy.txt").write_text("data")

    app = _create_app(purposes_module)
    _override_tenant(app, tenant, dependencies)

    client = TestClient(app)

    response = client.delete(f"/api/purposes/{purpose.id}")
    assert response.status_code == 204

    with Session(db.engine) as session:
        from ai_org_backend.models import (
            Artifact,
            ArtifactFeedback,
            ChatMessage,
            ChatMessageArtifact,
            ChatThreadContext,
            Feedback,
            Purpose,
            Task,
            TaskDependency,
        )

        assert session.exec(select(Purpose).where(Purpose.id == purpose.id)).first() is None
        assert session.exec(select(Task).where(Task.purpose_id == purpose.id)).all() == []
        assert session.exec(select(TaskDependency)).all() == []
        assert session.exec(select(Artifact).where(Artifact.task_id.in_(task_ids))).all() == []
        assert session.exec(select(ArtifactFeedback)).all() == []
        assert session.exec(select(ChatMessage)).all() == []
        assert session.exec(select(ChatMessageArtifact)).all() == []
        assert session.exec(select(ChatThreadContext)).all() == []
        assert session.exec(select(Feedback)).all() == []

    assert retracted == [artifact.id]
    assert removed_from_graph.get("ids") == task_ids
    assert removed_purposes == [purpose.id]
    assert sorted(dummy_pool.deleted_keys) == [
        f"budget:{tenant.id}:{purpose.id}",
        f"pause:{tenant.id}:{purpose.id}",
        f"tokens:{tenant.id}:{purpose.id}",
    ]

    assert not target_dir.exists()


def test_delete_purpose_handles_missing_feedback_table(monkeypatch, tmp_path):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    monkeypatch.setitem(os.environ, "REDIS_URL", "redis://localhost:6379/0")

    db_file = tmp_path / "test.db"
    monkeypatch.setitem(os.environ, "DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setitem(os.environ, "WORKSPACE_DIR", str(tmp_path / "workspace"))

    db, dependencies, purposes_module, settings_module = _reload_modules()

    SQLModel.metadata.create_all(db.engine)

    tenant, purpose, artifact, task_ids = _prepare_data(db.engine)

    original_exec = purposes_module.Session.exec

    def _exec_with_feedback_failure(self, statement, *args, **kwargs):
        table = getattr(getattr(statement, "table", None), "name", None)
        is_delete = getattr(statement, "is_delete", False)
        if table == "feedback" and is_delete:
            raise OperationalError(
                "DELETE FROM feedback", {}, RuntimeError("feedback table missing")
            )
        return original_exec(self, statement, *args, **kwargs)

    monkeypatch.setattr(
        purposes_module.Session,
        "exec",
        _exec_with_feedback_failure,
        raising=False,
    )

    removed_from_graph: dict[str, list[str]] = {}
    monkeypatch.setattr(
        purposes_module.graph_sync,
        "remove_tasks",
        lambda ids: removed_from_graph.setdefault("ids", list(ids)),
    )

    removed_purposes: list[str] = []
    monkeypatch.setattr(
        purposes_module.graph_sync,
        "remove_purpose",
        lambda pid: removed_purposes.append(pid),
    )

    retracted: list[str] = []

    def _retract(artifact_id: str, remove_from_neo4j: bool = False):
        retracted.append(artifact_id)

    monkeypatch.setattr(purposes_module, "retract_artifact", _retract)

    dummy_pool = SimpleNamespace(deleted_keys=[])

    def _delete_key(key: str):
        dummy_pool.deleted_keys.append(key)

    dummy_pool.delete = _delete_key
    monkeypatch.setattr(purposes_module, "pool", dummy_pool)

    workspace_root = settings_module.settings.workspace_dir
    target_dir = workspace_root / tenant.id / purpose.id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "dummy.txt").write_text("data")

    app = _create_app(purposes_module)
    _override_tenant(app, tenant, dependencies)

    client = TestClient(app)

    response = client.delete(f"/api/purposes/{purpose.id}")
    assert response.status_code == 204

    with Session(db.engine) as session:
        from ai_org_backend.models import (
            Artifact,
            ArtifactFeedback,
            ChatMessage,
            ChatMessageArtifact,
            ChatThreadContext,
            Purpose,
            Task,
            TaskDependency,
        )

        assert session.exec(select(Purpose).where(Purpose.id == purpose.id)).first() is None
        assert session.exec(select(Task).where(Task.purpose_id == purpose.id)).all() == []
        assert session.exec(select(TaskDependency)).all() == []
        assert session.exec(select(Artifact).where(Artifact.task_id.in_(task_ids))).all() == []
        assert session.exec(select(ArtifactFeedback)).all() == []
        assert session.exec(select(ChatMessage)).all() == []
        assert session.exec(select(ChatMessageArtifact)).all() == []
        assert session.exec(select(ChatThreadContext)).all() == []

    assert retracted == [artifact.id]
    assert removed_from_graph.get("ids") == task_ids
    assert removed_purposes == [purpose.id]
    assert sorted(dummy_pool.deleted_keys) == [
        f"budget:{tenant.id}:{purpose.id}",
        f"pause:{tenant.id}:{purpose.id}",
        f"tokens:{tenant.id}:{purpose.id}",
    ]

    assert not target_dir.exists()
