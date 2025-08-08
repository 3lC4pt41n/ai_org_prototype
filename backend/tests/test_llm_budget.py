import os
import types

from ai_org_backend.services import billing, llm_client


class _DummyResp:
    def __init__(self):
        self._data = {
            "choices": [{"message": {"content": "Test-Antwort"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 150, "total_tokens": 200},
        }

    def to_dict(self):
        return self._data


class _DummyCompletions:
    def create(self, *args, **kwargs):
        return _DummyResp()


class _DummyChat:
    completions = _DummyCompletions()


dummy_client = types.SimpleNamespace(chat=_DummyChat())


def _reset_budget(tid: str, amount: float):
    billing.credit(tid, -billing.balance(tid))
    billing.credit(tid, amount)


def test_llm_budget_deduction(monkeypatch):
    os.environ["USD_PER_1K_TOKENS"] = "0.002"
    tenant = "tenant-test"
    _reset_budget(tenant, 1.0)
    monkeypatch.setattr(llm_client, "_client", dummy_client)

    resp = llm_client.chat_with_tools(
        messages=[{"role": "user", "content": "Hallo"}], tenant=tenant
    )
    assert resp["choices"][0]["message"]["content"] == "Test-Antwort"
    expected_cost = (200 / 1000.0) * 0.002
    assert abs(billing.balance(tenant) - (1.0 - expected_cost)) < 1e-9

    _reset_budget(tenant, 0.0001)
    resp2 = llm_client.chat_with_tools(
        messages=[{"role": "user", "content": "Hallo"}], tenant=tenant
    )
    assert resp2 is None
    assert billing.balance(tenant) < 0
