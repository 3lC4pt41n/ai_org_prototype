#!/usr/bin/env python3
"""Validate checked-in PipelineGraph template YAML files."""

from __future__ import annotations

from pathlib import Path

from ai_org_backend.graph.template_matcher import TemplateCandidate, instantiate_template, load_template_file
from ai_org_backend.intent.schema import UserIntent


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "backend" / "ai_org_backend" / "graph" / "templates"


def main() -> None:
    if not TEMPLATES.exists():
        print("No graph templates directory yet; graph contracts are import-valid.")
        return
    count = 0
    for path in sorted(TEMPLATES.glob("*.yaml")):
        template = load_template_file(path)
        matches = template.get("matches", {})
        intent = UserIntent(
            domain=(matches.get("domain")[0] if isinstance(matches.get("domain"), list) else matches.get("domain")),
            action=(matches.get("action")[0] if isinstance(matches.get("action"), list) else matches.get("action")),
            deliverable_type=(
                matches.get("deliverable_type")[0]
                if isinstance(matches.get("deliverable_type"), list)
                else matches.get("deliverable_type")
            ),
            scale="medium",
            interaction_mode="hybrid",
            risk="medium",
            confidence=0.95,
            rationale=f"template validation for {path.name}",
            raw_request=f"validate {path.name}",
        )
        candidate = TemplateCandidate(
            template_id=template["id"],
            family=template.get("family", path.stem),
            confidence=1.0,
            path=path,
            template=template,
        )
        instantiate_template(intent, candidate)
        count += 1
    print(f"Validated {count} graph template YAML files.")


if __name__ == "__main__":
    main()
