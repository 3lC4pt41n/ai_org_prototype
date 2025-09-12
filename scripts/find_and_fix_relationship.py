from __future__ import annotations

import pathlib
import re
import site
import sys

PROJECT_ROOT = pathlib.Path.cwd()  # started here
SEARCH_PATHS = [
    PROJECT_ROOT,
    pathlib.Path(site.getsitepackages()[0]),
]  # project + venv site-packages
PATTERN = re.compile(r'relationship\(["\']List\[[\'\"]Task[\'\"]\]["\']\)')

AUTO_FIX = False  # set to True to apply fixes automatically

hits = []
for root in SEARCH_PATHS:
    for path in root.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for lineno, line in enumerate(source.splitlines(), 1):
            if PATTERN.search(line):
                hits.append((path, lineno, line.strip()))

# 1) Output matches
if hits:
    print("\n🛑  Invalid relationship() calls found:\n")
    for p, n, line_text in hits:
        rel_path = p.relative_to(PROJECT_ROOT)
        print(f"{rel_path}:{n}: {line_text}")
else:
    print("✅  No invalid relationship() calls found.")
    sys.exit(0)

# 2) Apply automatic fix?
if AUTO_FIX:
    print("\n🔧  Running AUTO-FIX …\n")
    for p, *_ in hits:
        text = p.read_text(encoding="utf-8")
        fixed = PATTERN.sub('Relationship(back_populates="tenant")', text)
        p.write_text(fixed, encoding="utf-8")
        print(f"→ fixed: {p.relative_to(PROJECT_ROOT)}")
    print(
        "\n✅  Replaced all occurrences – please verify models manually to ensure "
        'a matching type annotation (tasks: List["Task"]) exists.'
    )
else:
    print(
        "\nℹ️  Set AUTO_FIX = True (line 13) to replace them automatically, then run "
        "the script again."
    )
# -----------------------------------------------
