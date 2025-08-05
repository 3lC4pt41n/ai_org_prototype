#!/usr/bin/env python
"""Usage: python scripts/test_retrieval.py --tenant demo --task <TASK_ID>"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from ai_org_backend.db import SessionLocal  # noqa: E402
from ai_org_backend.models import Task  # noqa: E402
from ai_org_backend.services import memory  # noqa: E402


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Test memory snippet retrieval")
    ap.add_argument("--tenant", default="demo")
    ap.add_argument("--task", help="Task ID for context retrieval")
    ap.add_argument("--query", help="Custom query text (overrides task description)")
    args = ap.parse_args()

    query_text = args.query
    if not query_text:
        if not args.task:
            ap.error("Either --task or --query is required")
        with SessionLocal() as session:
            task = session.get(Task, args.task)
            if not task:
                ap.error(f"Task {args.task} not found")
            query_text = task.description

    snippets = memory.get_relevant_snippets(args.tenant, None, query_text, top_k=5)
    print(f"Retrieved {len(snippets)} snippets for query: '{query_text}'")
    for sn in snippets:
        cat = sn.get("category") or "-"
        print(f"[{cat}] {sn['source']}: {sn['chunk']}")
