from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from jinja2 import Template
from neo4j import GraphDatabase

from ai_org_backend.orchestrator.inspector import alert, todo_count
from llm import chat_completion

load_dotenv()

TENANT = os.getenv("TENANT", "demo")
PROMPT_DIR = Path(__file__).parent / "prompts"

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
                purpose_relevance=50,
            )
        )
    return tasks


def seed_if_empty() -> None:
    if todo_count(TENANT) > 0:
        return
    arch = chat_completion(TMPL_ARCH.render(purpose="bootstrap", task="bootstrap"))
    plan = chat_completion(TMPL_PLAN.render(task=arch))
    tasks = _extract_tasks(plan)
    if not tasks:
        alert("Seed LLM returned no tasks", "seed")
        return
    from ai_org_backend.main import Repo

    repo, id_map = Repo(TENANT), {}
    for t in tasks:
        node = repo.add(
            description=t["description"],
            business_value=t.get("business_value", 1.0),
            tokens_plan=t.get("tokens_plan", 0),
            purpose_relevance=t.get("purpose_relevance", 0),
        )
        id_map[t["id"]] = node.id
    for t in tasks:
        dep = t.get("depends_on")
        if dep and dep in id_map:
            repo.update(id_map[t["id"]], depends_on=id_map[dep])
    print(f"📥  Auto-seeded {len(tasks)} tasks.")

