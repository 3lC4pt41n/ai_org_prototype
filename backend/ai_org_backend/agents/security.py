"""
Security Agent
--------------
Runs Bandit (Python static analysis) and pip-audit (deps). Summarizes results,
creates fix tasks on critical findings.
"""

from __future__ import annotations

import json
import os

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Task
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.services.test_exec import run_bandit, run_pip_audit
from ai_org_backend.tasks.celery_app import celery

RUNS = prom_counter("ai_security_runs_total", "Security agent executions")
LAT = prom_hist("ai_security_latency_seconds", "Security agent latency")


@celery.task(name="agent.security")
def security_task(tenant_id: str, task_id: str) -> None:
    import time

    start = time.time()
    # Run bandit
    b_rc, b_out, b_err = run_bandit(target_dir="backend")
    # Run pip-audit (try root requirements fallback)
    req = "backend/requirements.txt" if os.path.exists("backend/requirements.txt") else None
    a_rc, a_out, a_err = run_pip_audit(requirements_file=req)

    report = {
        "bandit": json.loads(b_out or "{}"),
        "pip_audit": json.loads(a_out or "{}"),
        "stderr": {"bandit": b_err, "pip_audit": a_err},
    }
    md = []
    md.append("# Security Report")
    issues = report.get("bandit", {}).get("results", [])
    vulns = report.get("pip_audit", {}).get(
        "vulnerabilities", report.get("pip_audit", {}).get("vulns", [])
    )
    md.append(f"- Bandit issues: {len(issues)}")
    md.append(f"- Dependency vulnerabilities: {len(vulns) if isinstance(vulns, list) else 'n/a'}")
    if issues:
        md.append("\n## Bandit Findings (first 10)")
        for i, it in enumerate(issues[:10]):
            md.append(f"- **{it.get('issue_severity','?')}** {it.get('issue_text','')[:140]}")
    if isinstance(vulns, list) and vulns:
        md.append("\n## Dependency Vulnerabilities (first 10)")
        for i, v in enumerate(vulns[:10]):
            pkg = v.get("dependency", {}).get("name") or v.get("name")
            desc = v.get("id") or v.get("advisory", "")
            md.append(f"- {pkg}: {desc}")
    md_text = "\n".join(md)

    save_artefact(
        task_id,
        json.dumps(report, indent=2).encode("utf-8"),
        filename="reports/security_report.json",
        allow_overwrite=True,
    )
    save_artefact(
        task_id,
        md_text.encode("utf-8"),
        filename="reports/security_report.md",
        allow_overwrite=True,
    )
    RUNS.inc()
    LAT.observe(time.time() - start)

    critical = any((it.get("issue_severity") == "HIGH") for it in (issues or []))
    has_vulns = isinstance(vulns, list) and len(vulns) > 0

    with SessionLocal() as s:
        t = s.get(Task, task_id)
        if critical or has_vulns:
            t.status = "failed"
            t.owner = "QA-Sec"
            t.notes = "security findings"
            s.add(t)
            s.commit()
            fix = Task(
                tenant_id=tenant_id,
                purpose_id=t.purpose_id,
                description="Fix security findings",
                business_value=1.0,
                tokens_plan=800,
                purpose_relevance=1.0,
                notes="See reports/security_report.md",
            )
            s.add(fix)
            s.commit()
        else:
            t.status = "done"
            t.owner = "QA-Sec"
            t.notes = "security clean"
            s.add(t)
            s.commit()
