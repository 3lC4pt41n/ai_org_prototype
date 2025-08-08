"""Tests for planner parsing fallbacks and retries."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_run_planner_parsing_fallback(monkeypatch):
    """Ensure the planner retries and parses JSON from code blocks."""

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    spec = importlib.util.spec_from_file_location(
        "planner",
        Path(__file__).resolve().parents[1]
        / "ai_org_backend"
        / "agents"
        / "planner.py",
    )
    planner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(planner)

    responses = [
        # Erste Antwort: JSON im Markdown-Block und mit fehlenden Feldern
        "```json\n[{\"id\": \"T1\", \"description\": \"Testtask\"}]\n```",
        # Zweite Antwort: gültige Taskliste
        "[{\"id\": \"T1\", \"description\": \"Testtask\", \"depends_on\": null, \"business_value\": 1.0, \"tokens_plan\": 500, \"purpose_relevance\": 0.5}]",
    ]
    call_count = {"n": 0}

    def dummy_chat(model: str, messages: list[dict], **kwargs):
        content = responses[call_count["n"]]
        call_count["n"] += 1

        class _Msg:
            def __init__(self, c: str):
                self.content = c

        class _Choice:
            def __init__(self, c: str):
                self.message = _Msg(c)

        class _Resp:
            def __init__(self, c: str):
                self.choices = [_Choice(c)]

        return _Resp(content)

    monkeypatch.setattr(planner, "chat", dummy_chat)

    tasks = planner.run_planner("Dummy blueprint")

    assert tasks and tasks[0]["id"] == "T1"
    assert call_count["n"] == 2

