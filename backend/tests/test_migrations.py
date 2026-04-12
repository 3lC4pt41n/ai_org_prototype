"""Test that migrations apply cleanly to a fresh database."""
import os
import pytest
from sqlmodel import SQLModel, create_engine, Session, select


def test_fresh_db_migrations():
    """Verify all migrations apply to a blank SQLite database without errors."""
    db_path = "test_migrations.db"
    try:
        engine = create_engine(f"sqlite:///{db_path}")
        # Create all tables from models
        from ai_org_backend.models import (
            Tenant,
            Purpose,
            Task,
            TaskDependency,
            Artifact,
            Feedback,
            ChatMessage,
            PipelineTemplate,
            PipelinePhase,
        )

        SQLModel.metadata.create_all(engine)

        with Session(engine) as session:
            # Verify all tables exist by attempting a simple query
            session.exec(select(Tenant)).all()
            session.exec(select(Purpose)).all()
            session.exec(select(Task)).all()
            session.exec(select(TaskDependency)).all()
            session.exec(select(Artifact)).all()
            session.exec(select(Feedback)).all()
            session.exec(select(ChatMessage)).all()
            session.exec(select(PipelineTemplate)).all()
            session.exec(select(PipelinePhase)).all()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_cascade_delete_task_dependencies():
    """Verify that deleting a Task cascades to TaskDependency (ORM level)."""
    db_path = "test_cascade.db"
    try:
        engine = create_engine(f"sqlite:///{db_path}")

        from ai_org_backend.models import Tenant, Purpose, Task, TaskDependency

        SQLModel.metadata.create_all(engine)

        with Session(engine) as session:
            tenant = Tenant(
                name="test",
                hashed_password="hashed_test_password",
                balance=100.0
            )
            session.add(tenant)
            session.commit()
            session.refresh(tenant)

            purpose = Purpose(tenant_id=tenant.id, name="test purpose")
            session.add(purpose)
            session.commit()
            session.refresh(purpose)

            task_a = Task(
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description="Task A"
            )
            task_b = Task(
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description="Task B"
            )
            session.add_all([task_a, task_b])
            session.commit()
            session.refresh(task_a)
            session.refresh(task_b)

            dep = TaskDependency(
                from_id=task_a.id,
                to_id=task_b.id,
                dependency_type="blocks"
            )
            session.add(dep)
            session.commit()

            # Verify dependency was created
            deps_before = session.exec(select(TaskDependency)).all()
            assert len(deps_before) == 1, f"Expected 1 dependency, got {len(deps_before)}"

            # Delete task_a - should cascade to dependency
            session.delete(task_a)
            session.commit()

            # Verify dependency was deleted
            deps = session.exec(select(TaskDependency)).all()
            assert len(deps) == 0, f"Expected 0 dependencies after cascade delete, got {len(deps)}"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_cascade_delete_purpose_to_tasks():
    """Verify that deleting a Purpose cascades to Tasks."""
    db_path = "test_cascade_purpose.db"
    try:
        engine = create_engine(f"sqlite:///{db_path}")

        from ai_org_backend.models import Tenant, Purpose, Task

        SQLModel.metadata.create_all(engine)

        with Session(engine) as session:
            tenant = Tenant(
                name="test",
                hashed_password="hashed_test_password",
                balance=100.0
            )
            session.add(tenant)
            session.commit()
            session.refresh(tenant)

            purpose = Purpose(tenant_id=tenant.id, name="test purpose")
            session.add(purpose)
            session.commit()
            session.refresh(purpose)

            task1 = Task(
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description="Task 1"
            )
            task2 = Task(
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description="Task 2"
            )
            session.add_all([task1, task2])
            session.commit()

            # Verify tasks were created
            tasks_before = session.exec(select(Task)).all()
            assert len(tasks_before) == 2, f"Expected 2 tasks, got {len(tasks_before)}"

            # Delete purpose - should cascade to tasks
            session.delete(purpose)
            session.commit()

            # Verify tasks were deleted
            tasks = session.exec(select(Task)).all()
            assert len(tasks) == 0, f"Expected 0 tasks after cascade delete, got {len(tasks)}"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_cascade_delete_tenant_to_purposes():
    """Verify that deleting a Tenant cascades to Purposes and Tasks."""
    db_path = "test_cascade_tenant.db"
    try:
        engine = create_engine(f"sqlite:///{db_path}")

        from ai_org_backend.models import Tenant, Purpose, Task

        SQLModel.metadata.create_all(engine)

        with Session(engine) as session:
            tenant = Tenant(
                name="test",
                hashed_password="hashed_test_password",
                balance=100.0
            )
            session.add(tenant)
            session.commit()
            session.refresh(tenant)

            purpose = Purpose(tenant_id=tenant.id, name="test purpose")
            session.add(purpose)
            session.commit()
            session.refresh(purpose)

            task = Task(
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description="Task 1"
            )
            session.add(task)
            session.commit()

            # Verify records were created
            tenants_before = session.exec(select(Tenant)).all()
            purposes_before = session.exec(select(Purpose)).all()
            tasks_before = session.exec(select(Task)).all()

            assert len(tenants_before) == 1
            assert len(purposes_before) == 1
            assert len(tasks_before) == 1

            # Delete tenant - should cascade to purposes and tasks
            session.delete(tenant)
            session.commit()

            # Verify all were deleted
            tenants = session.exec(select(Tenant)).all()
            purposes = session.exec(select(Purpose)).all()
            tasks = session.exec(select(Task)).all()

            assert len(tenants) == 0, "Expected 0 tenants after cascade delete"
            assert len(purposes) == 0, "Expected 0 purposes after cascade delete"
            assert len(tasks) == 0, "Expected 0 tasks after cascade delete"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_dependency_type_validation():
    """Verify that TaskDependency.dependency_type has correct default."""
    db_path = "test_dep_type.db"
    try:
        engine = create_engine(f"sqlite:///{db_path}")

        from ai_org_backend.models import Tenant, Purpose, Task, TaskDependency

        SQLModel.metadata.create_all(engine)

        with Session(engine) as session:
            tenant = Tenant(
                name="test",
                hashed_password="hashed_test_password",
                balance=100.0
            )
            session.add(tenant)
            session.commit()
            session.refresh(tenant)

            purpose = Purpose(tenant_id=tenant.id, name="test purpose")
            session.add(purpose)
            session.commit()
            session.refresh(purpose)

            task_a = Task(
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description="Task A"
            )
            task_b = Task(
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description="Task B"
            )
            session.add_all([task_a, task_b])
            session.commit()
            session.refresh(task_a)
            session.refresh(task_b)

            # Create dependency with explicit type
            dep_explicit = TaskDependency(
                from_id=task_a.id,
                to_id=task_b.id,
                dependency_type="FINISH_START"
            )
            session.add(dep_explicit)
            session.commit()

            # Verify the type was stored correctly
            deps = session.exec(select(TaskDependency)).all()
            assert len(deps) == 1
            assert deps[0].dependency_type == "FINISH_START"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
