from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .schema import UserIntent


IssueSeverity = Literal["warning", "error"]


class IntentIssue(BaseModel):
    code: str
    message: str
    severity: IssueSeverity = "error"


class IntentValidationResult(BaseModel):
    valid: bool
    needs_clarification: bool
    issues: list[IntentIssue] = []


def validate_intent(intent: UserIntent) -> IntentValidationResult:
    issues: list[IntentIssue] = []

    if intent.action == "rework" and not intent.target_artifact_id:
        issues.append(
            IntentIssue(
                code="missing_rework_target",
                message="action=rework requires an existing target_artifact_id.",
            )
        )

    if intent.action == "rework" and intent.constraints.get("resolver_notes") == [
        "artifact_reference_not_found"
    ]:
        issues.append(
            IntentIssue(
                code="unknown_rework_target",
                message="Referenced artifact could not be resolved.",
            )
        )

    if intent.domain == "book" and intent.deliverable_type in {
        "architecture_blueprint",
        "implementation_plan",
        "code_change",
    }:
        issues.append(
            IntentIssue(
                code="domain_deliverable_mismatch",
                message="domain=book is incompatible with a software deliverable type.",
            )
        )

    if intent.domain == "software" and intent.deliverable_type == "manuscript":
        issues.append(
            IntentIssue(
                code="domain_deliverable_mismatch",
                message="domain=software is incompatible with deliverable_type=manuscript.",
            )
        )

    if intent.risk == "high" and intent.interaction_mode == "auto":
        issues.append(
            IntentIssue(
                code="high_risk_auto_mode",
                message="High-risk work cannot proceed in auto mode without approval.",
            )
        )

    if intent.confidence < 0.75:
        issues.append(
            IntentIssue(
                code="low_confidence",
                message="Intent confidence is below the 0.75 clarification gate.",
                severity="warning",
            )
        )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    return IntentValidationResult(
        valid=error_count == 0,
        needs_clarification=bool(issues),
        issues=issues,
    )
