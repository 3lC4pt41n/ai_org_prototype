from __future__ import annotations

import pathlib
import re
import site
import sys

PROJECT_ROOT = pathlib.Path.cwd()                     # hier gestartet
SEARCH_PATHS = [PROJECT_ROOT, pathlib.Path(site.getsitepackages()[0])]  # Projekt + venv-site‑packages
PATTERN      = re.compile(r'relationship\(["\']List\[[\'\"]Task[\'\"]\]["\']\)')

AUTO_FIX     = False   # << auf True setzen, wenn du gleich korrigieren willst

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

# 1) Treffer ausgeben
if hits:
    print("\n🛑  FEHLERHAFTE Relationship-Aufrufe gefunden:\n")
    for p, n, line_text in hits:
        rel_path = p.relative_to(PROJECT_ROOT)
        print(f"{rel_path}:{n}: {line_text}")
else:
    print("✅  Keine fehlerhaften Relationship-Aufrufe mehr gefunden.")
    sys.exit(0)

# 2) Automatisch korrigieren?
if AUTO_FIX:
    print("\n🔧  AUTO‑FIX wird ausgeführt …\n")
    for p, *_ in hits:
        text = p.read_text(encoding="utf-8")
        fixed = PATTERN.sub('Relationship(back_populates="tenant")', text)
        p.write_text(fixed, encoding="utf-8")
        print(f"→ korrigiert: {p.relative_to(PROJECT_ROOT)}")
    print("\n✅  Alle Fundstellen ersetzt – bitte Modelle manuell prüfen,\n"
          "   ob eine passende Typ‑Annotation (tasks: List[\"Task\"]) vorhanden ist.")
else:
    print("\nℹ️  Setze AUTO_FIX = True (Zeile 13), wenn du die Stellen automatisch\n"
          "   ersetzen lassen möchtest. Danach Skript erneut ausführen.")
# -----------------------------------------------
