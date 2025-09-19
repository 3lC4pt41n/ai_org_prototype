import json
import logging
import os
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from neo4j import GraphDatabase
from networkx import DiGraph
from sqlmodel import Session, select

from ai_org_backend.agents.utils import load_template
from ai_org_backend.api.auth import hash_password  # import the bcrypt hash helper
from ai_org_backend.db import engine
from ai_org_backend.models import Task, TaskDependency
from ai_org_backend.orchestrator.inspector import alert
from ai_org_backend.services.storage import register_artefact

load_dotenv()

TENANT = os.getenv("TENANT", "demo")
PURPOSE = os.getenv("PURPOSE", "bootstrap")

NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
driver = GraphDatabase.driver(
    NEO4J_URL,
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS")),
)

# A task is "ready" iff it is 'todo' AND has no incoming FINISH_START
# dependency whose predecessor is NOT done.
# (Missing r.kind is treated as FINISH_START for safety.)
LEAF_Q = """
MATCH (t:Task {status:'todo'})
WHERE NOT EXISTS {
  MATCH (p:Task)-[r:DEPENDS_ON]->(t)
  WHERE coalesce(r.kind,'FINISH_START') = 'FINISH_START'
    AND p.status <> 'done'
}
RETURN t.id AS id, t.desc AS d
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


TMPL_ARCH = load_template("architect.j2")
TMPL_PLAN = load_template("planner.j2")

MD_JSON_RX = re.compile(r"```json([\s\S]+?)```", re.I)


def _extract_tasks(txt: str) -> List[Dict[str, Any]]:
    m = MD_JSON_RX.search(txt)
    if m:
        return json.loads(m.group(1).strip())
    data = None
    try:
        lo, hi = txt.index("["), txt.rindex("]")
        data = json.loads(txt[lo : hi + 1])
    except (ValueError, json.JSONDecodeError):
        data = None
    if data is not None:
        return data
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
    from ai_org_backend.models import Purpose, Tenant

    _ = purpose_name  # parameter retained for backward compatibility

    with Session(engine) as session:
        # ── Safety net: create demo tenant automatically if missing ───────────────────────────────
        tenant = session.get(Tenant, TENANT)
        if tenant is None:
            demo_pw = os.getenv("DEMO_PASSWORD", "demo")
            demo_email = os.getenv("DEMO_EMAIL", "demo@localhost")
            demo_hash = hash_password(demo_pw)  # use bcrypt to hash the demo password
            tenant = Tenant(
                id=TENANT,
                name="Demo Tenant",
                email=demo_email,
                hashed_password=demo_hash,
            )
            session.add(tenant)
            session.commit()

        # Check all active purposes for new, empty backlogs
        print(f"[SEED] Checking for new purpose to seed (tenant '{TENANT}')")
        purposes = session.exec(
            select(Purpose).where(
                Purpose.tenant_id == TENANT, Purpose.is_active == True  # noqa: E712
            )
        ).all()
        if not purposes:
            # No active purpose found; check if tenant has any tasks
            task_exists = session.exec(select(Task).where(Task.tenant_id == TENANT)).first()
            if not task_exists:
                logging.info(
                    "No active purposes or tasks found for tenant %s – idle until activity detected.",
                    TENANT,
                )
            else:
                logging.info(
                    "No active purpose found for tenant %s – initial seeding skipped (tasks present).",
                    TENANT,
                )
            return
        # Find first purpose without associated tasks
        purpose = None
        for p in purposes:
            task_exists = session.exec(
                select(Task).where(Task.tenant_id == TENANT, Task.purpose_id == p.id)
            ).first()
            if task_exists:
                continue
            purpose = p
            break
        if not purpose:
            print("[SEED] No new purposes with empty backlog found – seeding aborted.")
            return
        print(f"[SEED] Seeding started for purpose '{purpose.name}' (tenant '{TENANT}')")

    # Generate Product Requirements via Product Owner agent
    from ai_org_backend.agents.architect import run_architect
    from ai_org_backend.agents.planner import run_planner
    from ai_org_backend.agents.product_owner import run_requirements
    from ai_org_backend.main import Repo

    try:
        prd_content = run_requirements(purpose)
    except Exception as e:
        alert(f"Seed run failed (requirements): {e}", "seed")
        return

    # Persist Requirements task and artefact
    prd_task = Repo(TENANT).add_task(
        purpose_id=purpose.id,
        description="Product Requirements Document",
        business_value=0.0,
        tokens_plan=0,
        purpose_relevance=1.0,
    )
    register_artefact(
        prd_task.id,
        prd_content.encode("utf-8"),
        filename="requirements/product_requirements.md",
    )
    Repo(TENANT).update(prd_task.id, status="done", owner="ProductOwner", notes="PRD completed")

    # Generate architecture blueprint and task plan
    try:
        blueprint = run_architect(purpose)
        plan = run_planner(blueprint, tenant_id=TENANT, purpose_id=purpose.id)
    except Exception as e:
        alert(f"Seed run failed (architecture): {e}", "seed")
        return
    tasks = plan if isinstance(plan, list) else []
    if not tasks:
        alert("Seed LLM returned no tasks", "seed")
        return
    # Insert repository initialization task if not already present
    if not any(
        t
        for t in tasks
        if str(t.get("description", "")).lower().startswith("initialize repository")
    ):
        tasks.insert(
            0,
            {
                "id": "repo_init",
                "description": "Initialize repository scaffolding",
                "business_value": 1.0,
                "tokens_plan": 0,
                "purpose_relevance": 0.0,
            },
        )
    # Add tasks for the Architecture Blueprint
    tasks.append(
        {
            "id": "blueprint",
            "description": "Architecture Blueprint",
            "business_value": 0.0,
            "tokens_plan": 0,
            "purpose_relevance": 0.0,
        }
    )
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
        node = repo.add_task(
            purpose_id=purpose.id,
            description=t["description"],
            business_value=t.get("business_value", 1.0),
            tokens_plan=t.get("tokens_plan", 0),
            purpose_relevance=t.get("purpose_relevance", 0.0),
        )
        id_map[t["id"]] = node.id
    with Session(engine) as s:
        for t in tasks:
            dep = t.get("depends_on") or t.get("depends_on_id")
            if dep and dep in id_map:
                s.add(
                    TaskDependency(
                        from_id=id_map[dep],
                        to_id=id_map[t["id"]],
                        dependency_type="FINISH_START",
                    )
                )
        # Ensure all new tasks depend on the repo_init task (if present)
        repo_id = id_map.get("repo_init")
        if repo_id:
            blueprint_tid = id_map.get("blueprint")
            requirements_tid = prd_task.id
            if blueprint_tid:
                s.add(
                    TaskDependency(
                        from_id=requirements_tid,
                        to_id=blueprint_tid,
                        dependency_type="FINISH_START",
                    )
                )
                s.add(
                    TaskDependency(
                        from_id=blueprint_tid,
                        to_id=repo_id,
                        dependency_type="FINISH_START",
                    )
                )
            for slug, tid in id_map.items():
                if slug not in ("repo_init", "blueprint"):
                    s.add(
                        TaskDependency(
                            from_id=repo_id,
                            to_id=tid,
                            dependency_type="FINISH_START",
                        )
                    )
        s.commit()
    # Persist the architecture blueprint as an artifact and mark its task as done
    blueprint_id = id_map.get("blueprint")
    if blueprint_id:
        register_artefact(
            blueprint_id,
            blueprint.encode("utf-8"),
            filename="blueprints/architecture_blueprint.md",
        )
        repo.update(blueprint_id, status="done", owner="Architect")
    from ai_org_backend.scripts.seed_graph import ingest

    ingest(TENANT)
    print(f"[SEED] Seeding completed: added {len(tasks)} tasks for purpose '{purpose.name}'.")


def _build_graph(session, tenant_id: str) -> DiGraph:
    """Return dependency graph for tenant."""
    g = DiGraph()
    tasks = session.exec(select(Task).where(Task.tenant_id == tenant_id)).all()
    for t in tasks:
        g.add_node(t.id, obj=t)

    deps = session.exec(
        select(TaskDependency).where(TaskDependency.from_task.has(tenant_id=tenant_id))
    ).all()
    for dep in deps:
        g.add_edge(dep.from_id, dep.to_id, kind=dep.dependency_type)

    return g
