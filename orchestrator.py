# orchestrator.py – v2.5  · LLM-aware router, auto-seed, insights
# ---------------------------------------------------------------
import asyncio, json, os, re, time
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from neo4j import GraphDatabase
from prometheus_client import Counter, Gauge
from sqlmodel import Session, select
from jinja2 import Template

from ai_org_prototype import (
    engine, Task, Repo, AGENTS,           # core objects
    default_budget, pool,                 # budget helpers
)
from llm import chat_completion           # thin wrapper around OpenAI (any SDK)

# ╭───────────────────────── ENV ────────────────────────╮
load_dotenv()

TENANT      = os.getenv("TENANT", "demo")
PROMPT_DIR  = Path(__file__).parent / "prompts"

NEO4J_URL   = os.getenv("NEO4J_URL",  "bolt://localhost:7687")
driver      = GraphDatabase.driver(
    NEO4J_URL,
    auth=(
        os.getenv("NEO4J_USER", "neo4j"),
        os.getenv("NEO4J_PASS", "s3cr3tP@ss"),
    ),
)

# ╭───────────────── Prometheus metrics ────────────────╮
PROM_ALERT_CNT     = Counter("ai_alerts_total",   "Alerts triggered", ["type"])
PROM_TASK_BLOCKED  = Gauge  ("ai_tasks_blocked",  "Number of blocked tasks")
PROM_CRIT_PATH_LEN = Gauge  ("ai_critical_path",  "Length of critical path")

# ╭───────────────── Neo4j queries ─────────────────────╮
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
RETURN length(p) AS l
       , [n IN nodes(p)|n.id] AS ids
ORDER BY l DESC LIMIT 1
"""

def cypher(query: str) -> List[Dict[str, Any]]:
    with driver.session() as g:
        return g.run(query).data()

# ╭───────────────── helpers ───────────────────────────╮
def todo_count() -> int:
    with Session(engine) as s:
        return s.exec(
            select(Task).where(Task.tenant_id == TENANT, Task.status == "todo")
        ).count()

def budget_left() -> float:
    return float(pool.hget("budget", TENANT) or default_budget)

def alert(msg: str, kind: str = "orch"):
    print(f"⚠️  [{kind.upper()}] {msg}")
    PROM_ALERT_CNT.labels(kind).inc()

# ╭───────────────── Prompt loader ─────────────────────╮
def _load_tmpl(name: str) -> Template:
    path = PROMPT_DIR / name
    return Template(path.read_text(encoding="utf-8", errors="replace"))

TMPL_ARCH = _load_tmpl("architect.j2")
TMPL_PLAN = _load_tmpl("planner.j2")

MD_JSON_RX = re.compile(r"```json([\s\S]+?)```", re.I)

def _extract_tasks(txt: str) -> List[Dict[str, Any]]:
    """
    * fenced ```json``` → parse
    * first [...] array → parse
    * markdown table fallback
    """
    m = MD_JSON_RX.search(txt)
    if m:
        return json.loads(m.group(1).strip())

    try:
        lo, hi = txt.index("["), txt.rindex("]")
        return json.loads(txt[lo : hi + 1])
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
                purpose_relevance=50,
            )
        )
    return tasks

# ╭───────────────── Auto-Seed ─────────────────────────╮
def seed_if_empty():
    if todo_count() > 0:
        return

    arch = chat_completion(TMPL_ARCH.render(purpose="bootstrap", task="bootstrap"))
    plan = chat_completion(TMPL_PLAN.render(task=arch))
    tasks = _extract_tasks(plan)

    if not tasks:
        alert("Seed LLM returned no tasks", "seed")
        return

    repo, id_map = Repo(TENANT), {}

    # pass-1  create nodes
    for t in tasks:
        node = repo.add(
            description=t["description"],
            business_value=t.get("business_value", 1.0),
            tokens_plan=t.get("tokens_plan", 0),
            purpose_relevance=t.get("purpose_relevance", 0),
        )
        id_map[t["id"]] = node.id

    # pass-2  dependencies
    for t in tasks:
        dep = t.get("depends_on")
        if dep and dep in id_map:
            repo.update(id_map[t["id"]], depends_on=id_map[dep])

    print(f"📥  Auto-seeded {len(tasks)} tasks.")

# ╭───────────────── Role routing ──────────────────────╮
AGENT_ROLES = list(AGENTS.keys())

def classify_role(desc: str) -> str:
    d = desc.lower()
    if any(k in d for k in ("ui", "ux", "design")):   return "ux_ui"
    if any(k in d for k in ("qa", "test", "review")): return "qa"
    if "metric" in d:                                 return "telemetry"

    prompt = f"Roles: {', '.join(AGENT_ROLES)}\nTask: \"{desc}\"\nRole:"
    try:
        role = chat_completion(prompt, max_tokens=4).strip().lower().split()[0]
        return role if role in AGENT_ROLES else "dev"
    except Exception as e:
        alert(str(e), "llm"); return "dev"

# ╭───────────────── Main loop ─────────────────────────╮
async def orchestrator():
    last = time.time()
    while True:
        seed_if_empty()

        # dispatch leaves
        for rec in cypher(LEAF_Q):
            role = classify_role(rec["d"])
            AGENTS[role].apply_async(
                args=[TENANT, rec["id"]],
                queue=f"{TENANT}:{role}",
            )

        # telemetry each 10 s
        if time.time() - last > 10:
            blocked = cypher(BLOCKED_Q)[0]["blocked"]
            crit = cypher(CRIT_Q)
            PROM_TASK_BLOCKED.set(blocked)
            if crit:
                PROM_CRIT_PATH_LEN.set(crit[0]["l"])

            print(
                f"ℹ️ todo:{todo_count():>3} "
                f"blocked:{blocked:<2} "
                f"budget:{budget_left():.2f}$"
            )
            last = time.time()

        if budget_left() < 1:
            alert("Budget exhausted", "budget")

        await asyncio.sleep(2)

# ╭───────────────── Entrypoint ────────────────────────╮
if __name__ == "__main__":
    print("⇢ Orchestrator v2.5 running …")
    asyncio.run(orchestrator())
