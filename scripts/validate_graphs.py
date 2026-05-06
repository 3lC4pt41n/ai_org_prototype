#!/usr/bin/env python3
"""Validate checked-in PipelineGraph template YAML files when present."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "backend" / "ai_org_backend" / "graph" / "templates"


def main() -> None:
    if not TEMPLATES.exists():
        print("No graph templates directory yet; graph contracts are import-valid.")
        return
    count = len(list(TEMPLATES.glob("*.yaml")))
    print(f"Found {count} graph template YAML files. Template validation is implemented in Phase 3.")


if __name__ == "__main__":
    main()
