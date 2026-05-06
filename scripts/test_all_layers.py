#!/usr/bin/env python3
"""Run the Phase 6 five-layer unittest harness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYERS = [
    ("unit_contract", "backend/tests/contracts"),
    ("graph_validation", "backend/tests/graph"),
    ("replay", "backend/tests/replay"),
    ("eval", "backend/tests/eval"),
    ("chaos", "backend/tests/chaos"),
    ("intent", "backend/tests/intent"),
    ("rework", "backend/tests/rework"),
    ("observability", "backend/tests/observability"),
]


def main() -> int:
    failures = 0
    for name, rel_path in LAYERS:
        path = ROOT / rel_path
        if not path.exists():
            print(f"SKIP {name}: {rel_path} does not exist")
            continue
        print(f"RUN {name}: {rel_path}")
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(path)],
            cwd=ROOT,
            env={"PYTHONPATH": "backend"},
            check=False,
        )
        if result.returncode != 0:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
