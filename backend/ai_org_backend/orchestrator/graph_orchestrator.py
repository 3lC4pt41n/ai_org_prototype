from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from networkx import DiGraph

from dotenv import load_dotenv
from jinja2 import Template
from neo4j import GraphDatabase

from ai_org_backend.orchestrator.inspector import alert, todo_count
from ai_org_backend.models import Task, TaskDependency
from sqlmodel import select, Session
from ai_org_backend.db import engine


load_dotenv()

TENANT = os.getenv("TENANT", "demo")
PURPOSE = os.getenv("PURPOSE", "bootstrap")
PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"

NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
driver = GraphDatabase.driver(
    NEO4J_URL,
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "s3cr3tP@ss")),
)

LEAF_Q = """
MATCH (t:Task {status:'todo'})
WHERE NOT (t)<-[:DEPENDS_ON]-(:Task {status:'todo'})
RETURN t.id AS id, t.desc AS d LIMIT 10
"""
BLOCKED_Q = """
MATCH (t:Task {status:'todo'})
WHERE (t)<-[:DEPENDS_ON]-(:Task {status:'todo'})
  AND NOT (t)<-[:DEPENDS_ON]-(:Task {status:'doing'})
RETURN count(t) AS blocked
"""
CRIT_Q = """
MATCH p=(s:Task)-[:DEPENDS_ON*]->(e:Task)
WHERE s.status='todo' AND e.status='todo'
RETURN length(p) AS l, [n IN nodes(p)|n.id] AS ids
ORDER BY l DESC LIMIT 1
"""

def cypher(query: str) -> List[Dict[str, Any]]:
    with driver.session() as g:
        return g.run(query).data()


def _load_tmpl(name: str) -> Template:
    path = PROMPT_DIR / name
    return Template(path.read_text(encoding="utf-8", errors="replace"))

TMPL_ARCH = _load_tmpl("architect.j2")
TMPL_PLAN = _load_tmpl("planner.j2")

MD_JSON_RX = re.compile(r"```json([\s\S]+?)```", re.I)


def _extract_tasks(txt: str) -> List[Dict[str, Any]]:
    m = MD_JSON_RX.search(txt)
    if m:
        return json.loads(m.group(1).strip())
    try:
        lo, hi = txt.index("["), txt.rindex("]")
        return json.loads(txt[lo: hi + 1])
    except Exception:
        pass
    rows = [ln for ln in txt.splitlines() if ln.lstrip().startswith("|")]
    tasks = []
    for r in rows[2:]:
        cols = [c.strip() for c in r.strip("|").split("|")]
        if len(cols) < 2:
            continue
        tasks.append(
            dict(
                id=re.sub(r"\s+", "_", cols[0].lower())[:8] or f"task{len(tasks)+1}",
                description=cols[0],
                depends_on=cols[1] or None,
                business_value=1.0,
                tokens_plan=1_000,
                purpose_relevance=0.5,
            )
        )
    return tasks


def seed_if_empty(purpose_name: str = PURPOSE) -> None:
    if todo_count(TENANT) > 0:
        return
    # Backlog is empty, initiate seeding
    print(f"[SEED] Seeding started for purpose '{purpose_name}' (tenant '{TENANT}')")
    # Determine or create Purpose for seeding
    from ai_org_backend.models import Purpose
    with Session(engine) as session:
        purpose = session.exec(
            select(Purpose).where(Purpose.name == purpose_name, Purpose.tenant_id == TENANT)
        ).first()
        if not purpose:
            purpose = Purpose(name=purpose_name, tenant_id=TENANT)
            session.add(purpose)
            session.commit()
            session.refresh(purpose)

    # Generate tasks via LLM agents
    from ai_org_backend.agents.architect import run_architect
    from ai_org_backend.agents.planner import run_planner
    try:
        blueprint = run_architect(purpose)
        plan = run_planner(blueprint)
    except Exception as e:
        alert(f"Seed run failed: {e}", "seed")
        return
    tasks = plan if isinstance(plan, list) else []
    if not tasks:
        alert("Seed LLM returned no tasks", "seed")
        return
    from ai_org_backend.main import Repo
    # Avoid duplicate tasks (idempotent seeding)
    with Session(engine) as session:
        existing_tasks = session.exec(
            select(Task).where(Task.tenant_id == TENANT, Task.purpose_id == purpose.id)
        ).all()
        existing_id_map = {t.description: t.id for t in existing_tasks}
    id_map = {}
    new_tasks = []
    for t in tasks:
        desc = t["description"]
        if desc in existing_id_map:
            id_map[t["id"]] = existing_id_map[desc]
            continue
        new_tasks.append(t)
    if not new_tasks:
        print(f"No new tasks to seed for purpose '{purpose.name}'.")
        return
    tasks = new_tasks
    repo = Repo(TENANT)
    for t in tasks:
        node = repo.add(
            description=t["description"],
            business_value=t.get("business_value", 1.0),
            tokens_plan=t.get("tokens_plan", 0),
            purpose_relevance=t.get("purpose_relevance", 0.0),
            purpose_id=purpose.id,
        )
        id_map[t["id"]] = node.id
    with Session(engine) as s:
        for t in tasks:
            dep = t.get("depends_on") or t.get("depends_on_id")
            if dep and dep in id_map:
                s.add(TaskDependency(from_id=id_map[dep], to_id=id_map[t["id"]]))
        s.commit()
    from ai_org_backend.scripts.seed_graph import ingest
    ingest(TENANT)
    print(
        f"[SEED] Seeding completed: added {len(tasks)} tasks for purpose '{purpose.name}'."
    )


def _build_graph(session, tenant_id: str) -> DiGraph:
    """Return dependency graph for tenant."""
    g = DiGraph()
    tasks = session.exec(select(Task).where(Task.tenant_id == tenant_id)).all()
    for t in tasks:
        g.add_node(t.id, obj=t)

    deps = session.exec(
        select(TaskDependency).where(
            TaskDependency.from_task.has(tenant_id=tenant_id)
        )
    ).all()
    for dep in deps:
        g.add_edge(dep.from_id, dep.to_id, kind=dep.dependency_type)

    return g

