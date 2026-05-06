#!/usr/bin/env python3
"""Runtime smoke check for persisted PipelineGraph v2.

This is intentionally a runtime check, not part of the fast pure-Python
contract suite. It requires the backend database dependencies and a reachable
database with migrations applied.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _dependency_error(exc: ModuleNotFoundError) -> int:
    print(
        "Missing backend runtime dependency: "
        f"{exc.name}. Run `make install-dev` or install backend requirements first.",
        file=sys.stderr,
    )
    return 2


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND / "ai_org_backend" / "alembic.ini"))
    command.upgrade(config, "head")


def _assert_graph_schema(engine: Any, *, allow_sqlite: bool) -> None:
    from sqlalchemy import inspect

    url = str(engine.url)
    if url.startswith("sqlite") and not allow_sqlite:
        raise RuntimeError(
            "Database engine resolved to SQLite. Refusing to run runtime smoke "
            "against the in-memory fallback; pass --allow-sqlite for local experiments."
        )

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required_tables = {
        "tenant",
        "purpose",
        "pipeline_graphs",
        "pipeline_nodes",
        "pipeline_edges",
    }
    missing_tables = sorted(required_tables - tables)
    if missing_tables:
        raise RuntimeError(
            "Database is missing required tables: "
            f"{', '.join(missing_tables)}. Run Alembic migrations first."
        )

    graph_columns = {column["name"] for column in inspector.get_columns("pipeline_graphs")}
    required_graph_columns = {"id", "tenant_id", "purpose_id", "intent_json", "checksum"}
    missing_columns = sorted(required_graph_columns - graph_columns)
    if missing_columns:
        raise RuntimeError(
            "pipeline_graphs is missing required columns: "
            f"{', '.join(missing_columns)}. Run Alembic migrations first."
        )


def _cleanup(session: Any, *, tenant_id: str, purpose_id: str, graph_id: str | None) -> None:
    from sqlmodel import delete

    from ai_org_backend.models import (
        PipelineEdgeRecord,
        PipelineGraphRecord,
        PipelineNodeRecord,
        Purpose,
        Tenant,
    )

    if graph_id:
        session.exec(delete(PipelineEdgeRecord).where(PipelineEdgeRecord.graph_id == graph_id))
        session.exec(delete(PipelineNodeRecord).where(PipelineNodeRecord.graph_id == graph_id))
        graph = session.get(PipelineGraphRecord, graph_id)
        if graph is not None:
            session.delete(graph)
    purpose = session.get(Purpose, purpose_id)
    if purpose is not None:
        session.delete(purpose)
    tenant = session.get(Tenant, tenant_id)
    if tenant is not None:
        session.delete(tenant)
    session.commit()


def run_smoke(args: argparse.Namespace) -> int:
    try:
        from sqlmodel import Session

        from ai_org_backend.db import engine
        from ai_org_backend.graph.validator import validate_graph
        from ai_org_backend.intent import IntentCompiler
        from ai_org_backend.models import Purpose, Tenant
        from ai_org_backend.services.graph_compiler import (
            compile_pipeline_graph,
            load_latest_pipeline_graph_for_purpose,
            save_pipeline_graph,
        )
    except ModuleNotFoundError as exc:
        return _dependency_error(exc)

    if args.upgrade:
        try:
            _run_alembic_upgrade()
        except ModuleNotFoundError as exc:
            return _dependency_error(exc)

    _assert_graph_schema(engine, allow_sqlite=args.allow_sqlite)

    suffix = uuid.uuid4().hex[:10]
    tenant_id = args.tenant_id or f"graph-v2-smoke-{suffix}"
    purpose_id = args.purpose_id or f"g2{suffix[:6]}"
    graph_id: str | None = None

    with Session(engine) as session:
        try:
            session.add(Tenant(id=tenant_id, name="Graph v2 smoke", hashed_password="smoke"))
            session.add(Purpose(id=purpose_id, tenant_id=tenant_id, name=args.raw_request))
            session.commit()

            compiled = IntentCompiler(tenant_id=tenant_id).compile(args.raw_request)
            if compiled.requires_clarification:
                raise RuntimeError(f"Intent requires clarification: {compiled.clarification_reason}")

            graph = compile_pipeline_graph(
                compiled.intent,
                use_workflow_search=args.use_workflow_search,
            )
            graph = graph.model_copy(update={"id": f"smoke.{purpose_id}.{graph.id}"}).with_checksum()
            validation = validate_graph(graph)
            if not validation.valid:
                raise RuntimeError(
                    "Compiled graph failed validation: "
                    + "; ".join(validation.errors)
                )

            save_pipeline_graph(
                session,
                graph,
                tenant_id=tenant_id,
                purpose_id=purpose_id,
            )
            graph_id = graph.id

            loaded = load_latest_pipeline_graph_for_purpose(
                session,
                purpose_id,
                tenant_id=tenant_id,
            )
            if loaded is None:
                raise RuntimeError("Saved graph could not be loaded by purpose scope")
            if loaded.id != graph.id:
                raise RuntimeError(f"Loaded graph mismatch: expected {graph.id}, got {loaded.id}")
            if loaded.checksum != graph.checksum:
                raise RuntimeError("Loaded graph checksum mismatch")
            if load_latest_pipeline_graph_for_purpose(
                session,
                purpose_id,
                tenant_id=f"{tenant_id}-other",
            ) is not None:
                raise RuntimeError("Tenant scope leak: graph was visible to another tenant")

            print(
                "Graph v2 runtime smoke PASS "
                f"graph_id={graph.id} nodes={len(graph.nodes)} edges={len(graph.edges)}"
            )
            return 0
        finally:
            if not args.keep_data:
                session.rollback()
                _cleanup(session, tenant_id=tenant_id, purpose_id=purpose_id, graph_id=graph_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-request",
        default="Create a small FastAPI endpoint and tests for a software product",
        help="Request text compiled into a graph v2 intent.",
    )
    parser.add_argument("--tenant-id", help="Existing or disposable tenant id to use.")
    parser.add_argument("--purpose-id", help="Existing or disposable purpose id to use.")
    parser.add_argument("--use-workflow-search", action="store_true")
    parser.add_argument("--upgrade", action="store_true", help="Run Alembic upgrade head first.")
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Allow running against the SQLite fallback for local experiments.",
    )
    parser.add_argument("--keep-data", action="store_true", help="Keep inserted smoke rows.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_smoke(args)
    except Exception as exc:
        print(f"Graph v2 runtime smoke FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
