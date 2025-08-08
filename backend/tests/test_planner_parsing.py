"""
Ziel dieses Tests:
- Sicherstellen, dass der Planner auch dann stabile Ergebnisse liefert,
  wenn die erste LLM-Antwort fehlerhaft formatiert ist (Markdown-JSON, fehlende Felder).
- Wir "mocken" die chat()-Funktion, um deterministische Antworten zu erzeugen,
  ohne echte API-Calls zu machen. So laufen Tests schnell und reproduzierbar.
"""

from types import SimpleNamespace

# WICHTIG: Wir setzen PYTHONPATH=backend (siehe Makefile/CI),
# damit 'ai_org_backend...' importierbar ist.
import ai_org_backend.agents.planner as planner


def _mk_resp(text: str):
    """Hilfsfunktion: baut eine fake-Response wie die LLM-Client-Library."""
    # choices[0].message.content soll 'text' enthalten
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def test_run_planner_parsing_fallback(monkeypatch):
    # 1. Antwort: JSON in Markdown-Codeblock + fehlende Felder (Schemafail)
    bad = """```json
    [ { "id": "T1", "description": "Do something" } ]
    ```"""
    # 2. Antwort: Korrektes JSON-Array gemäß Schema
    good = """[
      { "id": "T1", "description": "Do something",
        "depends_on": null, "business_value": 1.0,
        "tokens_plan": 300, "purpose_relevance": 0.8 }
    ]"""
    calls = {"n": 0}

    def fake_chat(model: str, messages, **kwargs):
        # Beim ersten Aufruf gib 'bad', beim zweiten 'good' zurück
        text = bad if calls["n"] == 0 else good
        calls["n"] += 1
        return _mk_resp(text)

    # chat() im Planner temporär durch fake_chat ersetzen
    monkeypatch.setattr(planner, "chat", fake_chat)

    tasks = planner.run_planner("Any blueprint")
    # Erwartung: Nach Fallback/Retry existiert eine gültige Task-Liste
    assert isinstance(tasks, list) and len(tasks) == 1
    assert tasks[0]["id"] == "T1"
    assert calls["n"] == 2  # 1x fehlerhaft, 1x erfolgreicher Retry
