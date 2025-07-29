from __future__ import annotations

import json
from pathlib import Path
from jinja2 import Template
from ai_org_backend.orchestrator.inspector import alert
from ai_org_backend.utils.llm import chat_completion
from ai_org_backend.main import AGENTS

AGENT_ROLES = list(AGENTS.keys())


def classify_role(desc: str) -> str:
    # Return "dev" by default if description is empty or whitespace
    if not desc or not desc.strip():
        return "dev"

    # Prepare LLM prompt using Jinja2 template with all available roles
    tmpl_path = Path(__file__).resolve().parents[3] / "prompts" / "orchestrator.j2"
    prompt = Template(tmpl_path.read_text(encoding="utf-8")).render(
        roles=AGENT_ROLES, description=desc
    )

    try:
        # Get LLM classification (expecting a JSON with {"role": "..."} or a single role string)
        result = chat_completion(prompt, max_tokens=10)
    except Exception as e:
        alert(str(e), "llm")
        return "dev"

    # Robust extraction of role from LLM output
    role = ""
    if result:
        result_str = str(result).strip()
        if result_str.startswith("{"):
            try:
                data = json.loads(result_str)
                if isinstance(data, dict) and "role" in data:
                    role = str(data["role"]).strip()
            except json.JSONDecodeError:
                role = ""
        if not role:
            # Fallback: take the first word from the first line of the response
            first_line = result_str.splitlines()[0]
            if first_line:
                role = first_line.strip().split()[0]
    role = role.lower()
    if role not in AGENT_ROLES:
        alert(f"Unknown role '{role}', defaulting to dev", "router")
        return "dev"
    return role

