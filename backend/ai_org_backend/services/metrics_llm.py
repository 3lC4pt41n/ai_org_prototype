"""
Prometheus-Metriken für LLM-Verbrauch & Kosten.
Eigene Datei, um Kollisionen mit bestehenden Metrik-Namen zu vermeiden.
"""
from prometheus_client import Counter, Gauge

LLM_CALLS = Counter(
    "ai_llm_calls_total",
    "Count of LLM calls",
    ["tenant", "model", "label", "status"],  # status: ok|error|blocked
)
LLM_TOKENS = Counter(
    "ai_llm_tokens_total",
    "Total LLM tokens (estimated or reported)",
    ["tenant", "model", "label", "estimation"],  # estimation: yes|no
)
LLM_COST_USD = Counter(
    "ai_llm_cost_usd_total",
    "Total LLM cost in USD",
    ["tenant", "model", "label"],
)
TENANT_BUDGET_LEFT = Gauge(
    "ai_tenant_budget_left_usd",
    "Current remaining budget per tenant (USD)",
    ["tenant"],
)
