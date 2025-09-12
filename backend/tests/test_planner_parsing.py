"""
Goal of this test:
- Ensure the planner produces stable results even when the first LLM response is
  malformed (Markdown-JSON, missing fields).
- Mock the chat() function to generate deterministic responses without real API
  calls. This keeps tests fast and reproducible.
"""

from types import SimpleNamespace

# IMPORTANT: set PYTHONPATH=backend (see Makefile/CI)
# so that 'ai_org_backend...' can be imported.
import ai_org_backend.agents.planner as planner


def _mk_resp(text: str):
    """Helper: build a fake response similar to the LLM client library."""
    # choices[0].message.content soll 'text' enthalten
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def test_run_planner_parsing_fallback(monkeypatch):
    # 1st response: JSON in Markdown code block + missing fields (schema fail)
    bad = """```json
    [ { "id": "T1", "description": "Do something" } ]
    ```"""
    # 2nd response: valid JSON array according to schema
    good = """[
      { "id": "T1", "description": "Do something",
        "depends_on": null, "business_value": 1.0,
        "tokens_plan": 300, "purpose_relevance": 0.8 }
    ]"""
    calls = {"n": 0}

    def fake_chat(model: str, messages, **kwargs):
        # Return 'bad' on first call, 'good' on second
        text = bad if calls["n"] == 0 else good
        calls["n"] += 1
        return _mk_resp(text)

    # Temporarily replace chat() in planner with fake_chat
    monkeypatch.setattr(planner, "chat", fake_chat)

    tasks = planner.run_planner("Any blueprint")
    # Expectation: after fallback/retry there is a valid task list
    assert isinstance(tasks, list) and len(tasks) == 1
    assert tasks[0]["id"] == "T1"
    assert calls["n"] == 2  # 1 failed, 1 successful retry
