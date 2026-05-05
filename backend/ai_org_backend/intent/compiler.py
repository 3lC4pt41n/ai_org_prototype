from __future__ import annotations

from pydantic import BaseModel

from ai_org_backend.orchestrator.role_rules import heuristic_role

from .classifier import classify_structured
from .extractor import extract_signals
from .resolver import ArtifactLookup, resolve_context
from .schema import UserIntent
from .validator import IntentValidationResult, validate_intent


class CompiledIntent(BaseModel):
    intent: UserIntent
    validation: IntentValidationResult
    legacy_role: str
    requires_clarification: bool
    clarification_reason: str | None = None
    trace: dict[str, object]


def legacy_role_for_intent(intent: UserIntent) -> str:
    heuristic = heuristic_role(intent.raw_request)
    if heuristic:
        return heuristic

    if intent.action == "review":
        if intent.target_artifact_type == "architecture_blueprint":
            return "reviewer"
        return "qa_review"
    if intent.deliverable_type in {"prd", "requirements"}:
        return "po"
    if intent.deliverable_type in {"architecture_blueprint", "implementation_plan"}:
        return "architect"
    if intent.domain == "research":
        return "insight"
    if intent.domain == "ops":
        return "telemetry"
    if intent.domain == "software":
        if intent.action == "create" and intent.deliverable_type == "code_change":
            return "dev"
        if intent.action == "rework":
            return "architect" if intent.target_artifact_type == "architecture_blueprint" else "dev"
    return "dev"


class IntentCompiler:
    def __init__(self, artifact_lookup: ArtifactLookup | None = None):
        self.artifact_lookup = artifact_lookup

    def compile(self, raw_request: str) -> CompiledIntent:
        signals = extract_signals(raw_request)
        resolved = resolve_context(signals, self.artifact_lookup)
        intent = classify_structured(signals, resolved)
        validation = validate_intent(intent)

        clarification_reason = None
        if validation.needs_clarification:
            clarification_reason = "; ".join(issue.message for issue in validation.issues)
            intent.constraints["clarification_node"] = {
                "required": True,
                "reason": clarification_reason,
            }

        legacy_role = legacy_role_for_intent(intent)
        return CompiledIntent(
            intent=intent,
            validation=validation,
            legacy_role=legacy_role,
            requires_clarification=validation.needs_clarification,
            clarification_reason=clarification_reason,
            trace={
                "name": "intent.compile",
                "attributes": {
                    "intent.domain": intent.domain,
                    "intent.action": intent.action,
                    "intent.deliverable_type": intent.deliverable_type,
                    "intent.confidence": intent.confidence,
                    "legacy_role": legacy_role,
                },
            },
        )


def compile_intent(
    raw_request: str,
    artifact_lookup: ArtifactLookup | None = None,
) -> CompiledIntent:
    return IntentCompiler(artifact_lookup=artifact_lookup).compile(raw_request)
