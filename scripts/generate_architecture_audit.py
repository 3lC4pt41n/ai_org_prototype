#!/usr/bin/env python3
"""Generate Phase 0 architecture audit documents from the current workspace.

The generator intentionally relies on filesystem and AST scans only. It does
not import the application, so it can run without Redis, Neo4j, Postgres, or
Celery being available.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" / "ai_org_backend"
DOCS = ROOT / "docs" / "architecture"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "api_route"}
WEBSOCKET_METHODS = {"websocket", "websocket_route"}
ROUTE_METHODS = HTTP_METHODS | WEBSOCKET_METHODS
SERVICE_RESPONSIBILITY = {
    "approval": "prüft und persistiert manuelle Freigaben für Review-/Release-Gates",
    "artifact_resolver": "löst referenzierte Artefakte und deren aktuelle Versionen auf",
    "artifact_workflow": "koordiniert Artefakt-Erstellung aus Purpose-, Task- und Chat-Kontext",
    "billing": "berechnet und sammelt nutzungsbezogene Abrechnungsdaten",
    "budget": "setzt Kostenbudgets und Budgetprüfungen für Tasks durch",
    "build_validator": "validiert erzeugte Repository-Dateien vor Integration oder Release",
    "conflict_detector": "erkennt konkurrierende Datei- und API-Änderungen zwischen Tasks",
    "cumulative_context": "verdichtet Lauf- und Artefaktkontext für Folgeagenten",
    "cycle_detector": "verhindert zyklische Task-Abhängigkeiten im DAG",
    "deep_research": "führt quellenbasierte Recherche- und Syntheseabläufe aus",
    "deployment_generator": "erzeugt Deployment-Artefakte für generierte Repositories",
    "feedback_loop": "setzt bestehende Review-Fix-Rework-Schleifen um",
    "file_reservation": "reserviert Dateien zur Kollisionsvermeidung paralleler Agenten",
    "graceful_shutdown": "koordiniert Startup- und Shutdown-Hooks für Runtime-Komponenten",
    "graph_service": "liefert Graph-Sichten über Tasks, Phasen und Artefakte",
    "graph_sync": "spiegelt SQL-Task-Zustand nach Neo4j",
    "llm_client": "kapselt Provider-spezifische LLM-Aufrufe",
    "llm_errors": "normalisiert LLM-Provider-Fehler für Retry- und UI-Pfade",
    "memory": "verwaltet langlebigen Kontext und Retrieval-Daten",
    "merge_service": "integriert Agentenänderungen in das Zielrepository",
    "metrics_llm": "erfasst token- und providerbezogene LLM-Metriken",
    "peer_context": "stellt Agenten den Status paralleler Tasks bereit",
    "pipeline_templates": "verwaltet Legacy-Phasentemplates und Task-Erzeugung daraus",
    "repo": "exportiert den tenantbezogenen Repo-Adapter und Budgetfunktionen",
    "repo_snapshot": "erstellt Dateisystem-Snapshots für Analyse und Review",
    "review_gate": "entscheidet Review-Fix-Abschluss und Re-Review-Eskalation",
    "shared_contracts": "definiert geteilte JSON-Schema- und Validierungsverträge",
    "storage": "persistiert Artefakte im Workspace und in der Datenbank",
    "structured_logging": "konfiguriert strukturierte Logs für API und Worker",
    "test_exec": "führt Testbefehle für generierte oder bearbeitete Repos aus",
    "testing": "bündelt Test-Hilfslogik für Runtime- und Agentenpfade",
    "token_counter": "schätzt Tokenverbrauch für Prompts und Artefakte",
    "url_safety": "validiert externe URLs vor Tool- oder Recherchezugriffen",
    "vector_store": "verwaltet Embedding- und Vektorstore-Operationen",
}


@dataclass(frozen=True)
class Route:
    methods: str
    path: str
    module: str
    handler: str
    responsibility: str


@dataclass(frozen=True)
class CeleryTask:
    name: str
    module: str
    handler: str
    responsibility: str


@dataclass(frozen=True)
class ModuleEntry:
    path: str
    responsibility: str


def parse_python(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def first_sentence(text: str | None, fallback: str) -> str:
    if not text:
        return fallback
    line = " ".join(text.strip().split())
    if not line:
        return fallback
    for sep in (". ", "; "):
        if sep in line:
            return line.split(sep, 1)[0].rstrip(".") + "."
    return line if line.endswith(".") else f"{line}."


def humanize_identifier(name: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", name).strip()
    return cleaned or name


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def literal_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def call_keyword(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def first_path_arg(call: ast.Call) -> str | None:
    if call.args:
        value = literal_str(call.args[0])
        if value is not None:
            return value
    return literal_str(call_keyword(call, "path"))


def join_paths(prefix: str, path: str) -> str:
    if not prefix:
        return path or "/"
    if not path or path == "/":
        return prefix.rstrip("/") or "/"
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"


def router_prefixes(tree: ast.Module) -> dict[str, str]:
    prefixes: dict[str, str] = {"app": ""}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if dotted_name(node.value.func) != "APIRouter":
            continue
        prefix = literal_str(call_keyword(node.value, "prefix")) or ""
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def route_methods(method: str, call: ast.Call) -> str:
    if method in WEBSOCKET_METHODS:
        return "WEBSOCKET"
    if method != "api_route":
        return method.upper()
    methods_node = call_keyword(call, "methods")
    if isinstance(methods_node, (ast.List, ast.Tuple)):
        values = [literal_str(item) for item in methods_node.elts]
        return ",".join(sorted(value.upper() for value in values if value))
    return "ANY"


def find_routes() -> list[Route]:
    routes: list[Route] = []
    for path in sorted((BACKEND / "api").glob("*.py")) + [BACKEND / "main.py"]:
        tree = parse_python(path)
        prefixes = router_prefixes(tree)
        mod = module_name(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr
                if method not in ROUTE_METHODS:
                    continue
                owner = dotted_name(decorator.func.value)
                path_arg = first_path_arg(decorator)
                if path_arg is None:
                    continue
                prefix = prefixes.get(owner, "")
                routes.append(
                    Route(
                        methods=route_methods(method, decorator),
                        path=join_paths(prefix, path_arg),
                        module=mod,
                        handler=node.name,
                        responsibility=first_sentence(
                            ast.get_docstring(node),
                            f"{humanize_identifier(node.name)} endpoint.",
                        ),
                    )
                )
    return sorted(routes, key=lambda item: (item.path, item.methods, item.module, item.handler))


def find_celery_tasks() -> list[CeleryTask]:
    tasks: list[CeleryTask] = []
    for path in sorted(BACKEND.rglob("*.py")):
        tree = parse_python(path)
        mod = module_name(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                decorator_name = dotted_name(decorator.func)
                if not (
                    decorator_name.endswith(".task")
                    or decorator_name in {"shared_task", "celery.task"}
                ):
                    continue
                task_name = literal_str(call_keyword(decorator, "name"))
                if task_name is None and decorator.args:
                    task_name = literal_str(decorator.args[0])
                if task_name is None:
                    task_name = f"{mod}.{node.name}"
                tasks.append(
                    CeleryTask(
                        name=task_name,
                        module=mod,
                        handler=node.name,
                        responsibility=first_sentence(
                            ast.get_docstring(node),
                            f"{humanize_identifier(node.name)} worker task.",
                        ),
                    )
                )
    return sorted(tasks, key=lambda item: (item.name, item.module, item.handler))


def find_module_entries() -> list[ModuleEntry]:
    entries: list[ModuleEntry] = []
    for path in sorted(BACKEND.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = parse_python(path)
        rel = path.relative_to(ROOT).as_posix()
        name = path.stem
        responsibility = SERVICE_RESPONSIBILITY.get(name)
        if responsibility:
            responsibility = responsibility[0].upper() + responsibility[1:] + "."
        else:
            responsibility = first_sentence(
                ast.get_docstring(tree),
                f"{humanize_identifier(name).capitalize()} module.",
            )
        entries.append(ModuleEntry(path=rel, responsibility=responsibility))
    return entries


def find_services() -> list[ModuleEntry]:
    services: list[ModuleEntry] = []
    for path in sorted((BACKEND / "services").glob("*.py")):
        if path.name == "__init__.py":
            continue
        name = path.stem
        responsibility = SERVICE_RESPONSIBILITY.get(name)
        if responsibility:
            responsibility = responsibility[0].upper() + responsibility[1:] + "."
        else:
            tree = parse_python(path)
            responsibility = first_sentence(
                ast.get_docstring(tree),
                f"{humanize_identifier(name).capitalize()} service.",
            )
        services.append(ModuleEntry(path=path.relative_to(ROOT).as_posix(), responsibility=responsibility))
    return services


def find_repositories() -> list[ModuleEntry]:
    candidates = [BACKEND / "repo.py", BACKEND / "services" / "repo.py", BACKEND / "services" / "repo_snapshot.py"]
    entries: list[ModuleEntry] = []
    for path in candidates:
        if not path.exists():
            continue
        tree = parse_python(path)
        responsibility = first_sentence(ast.get_docstring(tree), f"{path.stem} repository helper.")
        entries.append(ModuleEntry(path=path.relative_to(ROOT).as_posix(), responsibility=responsibility))
    return entries


def model_inventory() -> list[ModuleEntry]:
    entries: list[ModuleEntry] = []
    for path in sorted((BACKEND / "models").glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = parse_python(path)
        classes = [
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
        ]
        label = ", ".join(classes) if classes else humanize_identifier(path.stem)
        entries.append(
            ModuleEntry(
                path=path.relative_to(ROOT).as_posix(),
                responsibility=f"Definiert persistierte Datenstruktur(en): {label}.",
            )
        )
    return entries


def table(headers: list[str], rows: list[list[str]]) -> str:
    def esc(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(esc(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def render_audit_report() -> str:
    routes = find_routes()
    celery_tasks = find_celery_tasks()
    modules = find_module_entries()
    services = find_services()
    repositories = find_repositories()
    models = model_inventory()

    route_rows = [
        [route.methods, f"`{route.path}`", f"`{route.module}.{route.handler}`", route.responsibility]
        for route in routes
    ]
    celery_rows = [
        [f"`{task.name}`", f"`{task.module}.{task.handler}`", task.responsibility]
        for task in celery_tasks
    ]
    service_rows = [[f"`{entry.path}`", entry.responsibility] for entry in services]
    repo_rows = [[f"`{entry.path}`", entry.responsibility] for entry in repositories]
    model_rows = [[f"`{entry.path}`", entry.responsibility] for entry in models]
    module_rows = [[f"`{entry.path}`", entry.responsibility] for entry in modules]

    return "\n\n".join(
        [
            "# Phase 0 Audit Report",
            (
                "Quelle: `scripts/generate_architecture_audit.py`. "
                "Der Report wird aus Dateisystem- und AST-Scans erzeugt, nicht aus README-Text."
            ),
            "## Kurzbefund",
            "\n".join(
                [
                    f"- FastAPI-Routen: {len(routes)}",
                    f"- Celery-Tasks: {len(celery_tasks)}",
                    f"- Service-Module: {len(services)}",
                    f"- Repository-Adapter: {len(repositories)}",
                    f"- Datenmodell-Dateien: {len(models)}",
                    f"- Python-Module insgesamt: {len(modules)}",
                ]
            ),
            "## FastAPI-Routen",
            table(["Methode", "Pfad", "Handler", "Verantwortung"], route_rows),
            "## Celery-Tasks",
            table(["Task", "Handler", "Verantwortung"], celery_rows),
            "## Repositories",
            table(["Datei", "Verantwortung"], repo_rows),
            "## Services",
            table(["Datei", "Verantwortung"], service_rows),
            "## Persistenzmodelle",
            table(["Datei", "Verantwortung"], model_rows),
            "## Modul-Inventar",
            table(["Datei", "Verantwortung"], module_rows),
        ]
    ) + "\n"


def render_debt_backlog() -> str:
    rows = [
        [
            "blocking",
            "Intent-Semantik ist implizit an Rollen und Agent-Queues gekoppelt.",
            "`backend/ai_org_backend/orchestrator/role_rules.py`, `tasks/celery_app.py`",
            "Für Phase 1 akzeptiert: bestehendes Role-Routing bleibt Legacy-Adapter, bis `intent/` eingeführt ist.",
        ],
        [
            "blocking",
            "Pipeline-Struktur ist als lineare Phase/Predecessor-Abfolge modelliert.",
            "`backend/ai_org_backend/models/pipeline.py`, `services/pipeline_templates.py`",
            "Für Phase 2 akzeptiert: Legacy-Phasen werden per Adapter nach `PipelineGraph` v2 migriert.",
        ],
        [
            "blocking",
            "Rework ist in Feedback-/Review-Services verteilt und nicht als bounded Loop vertraglich modelliert.",
            "`backend/ai_org_backend/services/feedback_loop.py`, `services/review_gate.py`",
            "Für Phase 4 akzeptiert: Konsolidierung in `services/rework.py` mit `RevisionLimitPolicy`.",
        ],
        [
            "blocking",
            "Graph- und Artefakt-Lineage liegen in mehreren Speichern ohne gemeinsamen Run-Trace.",
            "`services/graph_sync.py`, `services/storage.py`, `models/artifact.py`",
            "Für Phase 5 akzeptiert: OTel/OpenLineage wird als Korrelationsschicht ergänzt.",
        ],
        [
            "important",
            "FastAPI und Celery importieren Runtime-Komponenten teilweise gegenseitig.",
            "`main.py`, `tasks/celery_app.py`",
            "Bei Engine-Abstraktion zyklische Imports reduzieren.",
        ],
        [
            "important",
            "Task-Statuswerte sind Strings, obwohl ein Enum existiert.",
            "`models/task.py`",
            "Bei Graph-v2-Migration Statusübergänge zentralisieren.",
        ],
        [
            "important",
            "Budget-Gates basieren auf geplanter Tokenzahl statt knotengenauer Kostenbudgets.",
            "`tasks/celery_app.py`, `services/budget.py`",
            "In Phase 2/5 auf Node-Budget und Cost-Trace erweitern.",
        ],
        [
            "important",
            "Neo4j-Sync ist best effort und nicht vollständig replaybar.",
            "`repo.py`, `services/graph_sync.py`",
            "Für Phase 5 Run-Trace und Reconciliation dokumentieren.",
        ],
        [
            "important",
            "Review-Fix-Logik erkennt Rework über Textpräfixe.",
            "`tasks/celery_app.py`, `services/review_gate.py`",
            "In Phase 4 durch explizite Edge-/Loop-Semantik ersetzen.",
        ],
        [
            "important",
            "Template-Verträge sind Python-Objekte, nicht deklarative YAML-Artefakte.",
            "`services/pipeline_templates.py`",
            "In Phase 3 in Template-Bibliothek überführen.",
        ],
        [
            "nice-to-have",
            "Mehrere Agentenmodule haben ähnliche Fehlerbehandlungs- und Repo-Update-Muster.",
            "`backend/ai_org_backend/agents/*.py`",
            "Nach stabilen Graph-Verträgen in gemeinsame Worker-Helfer extrahieren.",
        ],
        [
            "nice-to-have",
            "Einige Verantwortungen sind nur durch Sprint-Kommentare dokumentiert.",
            "`backend/tests/test_sprint*_audit.py`",
            "Nach ADR-Updates historische Sprint-Kommentare reduzieren.",
        ],
    ]
    return "\n\n".join(
        [
            "# Phase 0 Debt Backlog",
            "Maximal 25 Einträge. Klassifikation: `blocking`, `important`, `nice-to-have`.",
            table(["Priorität", "Schuld", "Betroffene Stellen", "Akzeptanz / Maßnahme"], rows),
            (
                "## Blocking-Akzeptanz\n\n"
                "Die ersten vier Einträge sind für diesen Sprint dokumentiert akzeptiert. "
                "Sie blockieren spätere Phasen fachlich, verhindern aber Phase 0 nicht, "
                "weil jeweils eine konkrete Zielphase und Migrationsrichtung festgelegt ist."
            ),
        ]
    ) + "\n"


def render_glossary() -> str:
    rows = [
        [
            "Task",
            "Kleinste ausführbare Arbeitseinheit der heutigen Runtime.",
            "`backend/ai_org_backend/models/task.py::Task`",
            "todo -> doing -> done/failed/skipped/budget_exceeded/dead_letter.",
            "Kein Intent, kein Graph-Knotenvertrag und kein Artefakt.",
        ],
        [
            "Pipeline",
            "Geordneter Ablauf zur Erzeugung oder Überarbeitung eines Purpose-Ergebnisses.",
            "`models/pipeline.py::PipelineTemplate`, künftig `graph/schema.py::PipelineGraph`",
            "Template-Auswahl -> Task-Erzeugung -> Worker-Ausführung -> Review/Release.",
            "Keine einzelne Queue und keine lose Task-Liste ohne Abhängigkeiten.",
        ],
        [
            "Phase",
            "Legacy-Schritt innerhalb eines Pipeline-Templates.",
            "`models/pipeline.py::PipelinePhase`",
            "Template-Definition -> Task-Instanz pro Purpose -> Abschluss oder Rework.",
            "Kein frei synthetisierter Graph-Knoten und keine Runtime-Engine.",
        ],
        [
            "Purpose",
            "Tenant-gebundener Zielkontext, unter dem Tasks, Artefakte und Chat-Kontext gruppiert werden.",
            "`backend/ai_org_backend/models/purpose.py::Purpose`",
            "Anlegen -> aktivieren/starten -> pausieren/fortführen -> löschen.",
            "Kein einzelner Nutzerprompt und keine Agentenrolle.",
        ],
        [
            "Artifact",
            "Persistiertes Ergebnis eines Tasks inklusive Versionierungs- und Feedback-Kontext.",
            "`backend/ai_org_backend/models/artifact.py::Artifact`",
            "Erzeugen -> referenzieren/reviewen -> versionieren -> freigeben oder invalidieren.",
            "Kein Task-Status und kein flüchtiger Prompt.",
        ],
        [
            "Run",
            "Konkrete Ausführung eines Graphen oder Legacy-Pipeline-Ablaufs.",
            "Heute implizit über Task-Status/Heartbeat; künftig `runs` in Phase 2.",
            "Start -> Node/Task-Ausführung -> Retry/Rework -> terminaler Status.",
            "Kein Template und keine statische Architekturdefinition.",
        ],
        [
            "Node",
            "Expliziter, typisierter Ausführungspunkt im künftigen `PipelineGraph`.",
            "Künftig `backend/ai_org_backend/graph/schema.py::PipelineNode`",
            "Validierung -> Scheduling -> Ausführung -> Output/Trace -> ggf. Rework.",
            "Keine Legacy-Phase ohne Capability- und Schema-Vertrag.",
        ],
        [
            "Edge",
            "Explizite Abhängigkeits- oder Feedback-Beziehung zwischen Graph-Knoten.",
            "Heute `TaskDependency`; künftig `graph/schema.py::PipelineEdge`",
            "Definition -> Validierung -> Aktivierung nach Bedingung -> Lineage/Invalidierung.",
            "Keine Reihenfolgenummer und kein informeller Textverweis.",
        ],
    ]
    return "\n\n".join(
        [
            "# Phase 0 Glossary",
            "Einheitliche Begriffe für die folgenden Phasen.",
            table(
                ["Begriff", "Definition", "Datenstruktur-Referenz", "Lebenszyklus", "Negativbeispiele"],
                rows,
            ),
        ]
    ) + "\n"


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "00-audit-report.md").write_text(render_audit_report(), encoding="utf-8")
    (DOCS / "00-debt-backlog.md").write_text(render_debt_backlog(), encoding="utf-8")
    (DOCS / "00-glossary.md").write_text(render_glossary(), encoding="utf-8")
    print(f"Wrote Phase 0 audit docs to {DOCS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
