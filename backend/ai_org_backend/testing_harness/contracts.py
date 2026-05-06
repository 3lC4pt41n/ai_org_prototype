from __future__ import annotations

from pydantic import BaseModel, Field


class ContractCheckResult(BaseModel):
    valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    unexpected_fields: list[str] = Field(default_factory=list)


def validate_required_fields(
    payload: dict,
    *,
    required: set[str],
    allowed: set[str] | None = None,
) -> ContractCheckResult:
    missing = sorted(required - set(payload.keys()))
    unexpected = sorted(set(payload.keys()) - allowed) if allowed is not None else []
    return ContractCheckResult(valid=not missing and not unexpected, missing_fields=missing, unexpected_fields=unexpected)
