from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from .extractor import IntentSignals
from .resolver import ResolvedContext
from .schema import UserIntent


LLMClassifier = Callable[[str], Mapping[str, Any] | str | None]


def _default_deliverable(signals: IntentSignals) -> str:
    if signals.domain == "book":
        return "manuscript"
    if signals.domain == "research":
        return "research_brief"
    if signals.domain == "ops":
        return "runbook"
    if signals.domain == "software":
        if signals.action == "review":
            return "review_report"
        if signals.action == "rework" and signals.target_artifact_type:
            return signals.target_artifact_type
        return "code_change"
    return "general_response"


def _confidence(signals: IntentSignals, resolved: ResolvedContext) -> float:
    score = 0.35
    if signals.domain:
        score += 0.15
    if signals.action:
        score += 0.15
    if signals.deliverable_type or signals.target_artifact_type:
        score += 0.12
    elif signals.domain in {"book", "research", "ops"}:
        score += 0.12
    if signals.target_artifact_id:
        score += 0.08
    if resolved.target_artifact_exists is True:
        score += 0.08
    if resolved.target_artifact_exists is False:
        score -= 0.18
    if signals.ambiguity_markers:
        score -= 0.12 * len(signals.ambiguity_markers)
    return max(0.0, min(0.98, round(score, 2)))


def _constraints(signals: IntentSignals, resolved: ResolvedContext) -> dict[str, Any]:
    constraints: dict[str, Any] = {
        "signal_keywords": sorted(set(signals.matched_keywords)),
        "ambiguity_markers": signals.ambiguity_markers,
        "resolver_notes": resolved.notes,
        "classification_source": "deterministic",
    }
    if resolved.latest_version_id:
        constraints["latest_version_id"] = resolved.latest_version_id
    return constraints


def classify_structured(signals: IntentSignals, resolved: ResolvedContext) -> UserIntent:
    domain = signals.domain or "general"
    action = signals.action or "create"
    deliverable_type = signals.deliverable_type or _default_deliverable(signals)
    target_artifact_type = resolved.target_artifact_type or signals.target_artifact_type
    constraints = _constraints(signals, resolved)

    rationale_parts = [
        f"domain={domain}",
        f"action={action}",
        f"deliverable_type={deliverable_type}",
    ]
    if signals.ambiguity_markers:
        rationale_parts.append(f"ambiguity={','.join(signals.ambiguity_markers)}")
    if resolved.notes:
        rationale_parts.append(f"resolver={','.join(resolved.notes)}")

    return UserIntent(
        domain=domain,
        action=action,
        deliverable_type=deliverable_type,
        target_artifact_id=resolved.target_artifact_id,
        target_artifact_type=target_artifact_type,
        scale=signals.scale or "medium",
        interaction_mode=signals.interaction_mode or "hybrid",
        risk=signals.risk or "medium",
        constraints=constraints,
        confidence=_confidence(signals, resolved),
        rationale="; ".join(rationale_parts),
        raw_request=signals.raw_request,
    )


def _coerce_llm_payload(payload: Mapping[str, Any] | str | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return dict(payload)


def classify_with_llm_fallback(
    signals: IntentSignals,
    resolved: ResolvedContext,
    llm_classifier: LLMClassifier | None = None,
) -> UserIntent:
    deterministic = classify_structured(signals, resolved)
    if llm_classifier is None or deterministic.confidence >= 0.75:
        return deterministic

    payload = _coerce_llm_payload(llm_classifier(signals.raw_request))
    if not payload:
        deterministic.constraints["llm_fallback"] = "empty_or_unparseable"
        return deterministic

    merged = deterministic.model_dump()
    for key in (
        "domain",
        "action",
        "deliverable_type",
        "target_artifact_id",
        "target_artifact_type",
        "scale",
        "interaction_mode",
        "risk",
        "confidence",
        "rationale",
    ):
        if payload.get(key) is not None:
            merged[key] = payload[key]

    merged["raw_request"] = signals.raw_request
    merged["target_artifact_id"] = resolved.target_artifact_id or merged.get("target_artifact_id")
    merged["target_artifact_type"] = resolved.target_artifact_type or merged.get("target_artifact_type")
    constraints = dict(deterministic.constraints)
    constraints["classification_source"] = "llm"
    constraints["llm_rationale"] = payload.get("rationale")
    if resolved.latest_version_id:
        constraints["latest_version_id"] = resolved.latest_version_id
    merged["constraints"] = constraints
    return UserIntent(**merged)


def default_llm_classifier(raw_request: str, model: str = "gpt-4o-mini", tenant_id: str | None = None) -> str:
    from ai_org_backend.utils.llm import chat_completion

    prompt = (
        "Classify the user request as JSON matching this schema exactly. "
        "Use only these enum values: domain=software|book|research|ops|general; "
        "action=create|rework|review|continue|summarize|translate; "
        "scale=small|medium|large; interaction_mode=auto|manual|hybrid; "
        "risk=low|medium|high. Include confidence between 0 and 1, rationale, "
        "and raw_request unchanged. Return JSON only.\n\n"
        f"raw_request: {raw_request}"
    )
    return chat_completion(prompt, model=model, tenant_id=tenant_id, max_tokens=500, temperature=0.0)
