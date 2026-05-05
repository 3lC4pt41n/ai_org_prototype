from __future__ import annotations

from .extractor import IntentSignals
from .resolver import ResolvedContext
from .schema import UserIntent


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
    if signals.target_artifact_id:
        score += 0.08
    if resolved.target_artifact_exists is True:
        score += 0.08
    if resolved.target_artifact_exists is False:
        score -= 0.18
    if signals.ambiguity_markers:
        score -= 0.12 * len(signals.ambiguity_markers)
    return max(0.0, min(0.98, round(score, 2)))


def classify_structured(signals: IntentSignals, resolved: ResolvedContext) -> UserIntent:
    domain = signals.domain or "general"
    action = signals.action or "create"
    deliverable_type = signals.deliverable_type or _default_deliverable(signals)
    target_artifact_type = resolved.target_artifact_type or signals.target_artifact_type
    constraints = {
        "signal_keywords": sorted(set(signals.matched_keywords)),
        "ambiguity_markers": signals.ambiguity_markers,
        "resolver_notes": resolved.notes,
    }
    if resolved.latest_version_id:
        constraints["latest_version_id"] = resolved.latest_version_id

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
