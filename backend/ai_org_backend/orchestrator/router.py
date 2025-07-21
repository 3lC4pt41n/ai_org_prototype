from __future__ import annotations

from llm import chat_completion

from ai_org_backend.main import AGENTS

AGENT_ROLES = list(AGENTS.keys())


def classify_role(desc: str) -> str:
    d = desc.lower()
    if not d.strip():
        return "dev"
    if any(k in d for k in ("ui", "ux", "design")):
        return "ux_ui"
    if any(k in d for k in ("qa", "test", "review")):
        return "qa"
    if "metric" in d:
        return "telemetry"
    prompt = f"Roles: {', '.join(AGENT_ROLES)}\nTask: \"{desc}\"\nRole:"
    try:
        role = chat_completion(prompt, max_tokens=4).strip().lower().split()[0]
        return role if role in AGENT_ROLES else "dev"
    except Exception as e:  # pragma: no cover - network
        from ai_org_backend.orchestrator.inspector import alert

        alert(str(e), "llm")
        return "dev"

