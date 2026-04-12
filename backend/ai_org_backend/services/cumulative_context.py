"""S3-07: Cumulative context service for pipeline agents.

Each agent in the pipeline needs access to the accumulated context from
all preceding phases.  This module builds a structured context dict that
agents can inject into their prompts.

Context hierarchy (each phase includes all previous):

1. Vision Document
2. Product Requirements Document (PRD)
3. Architecture Blueprint
4. Architecture & Domain Review
5. Implementation Plan

Usage::

    from ai_org_backend.services.cumulative_context import load_cumulative_context

    ctx = load_cumulative_context(purpose_id, up_to="architecture blueprint")
    # ctx = {
    #     "vision": "...",
    #     "prd": "...",
    #     "blueprint": "...",
    #     "purpose_name": "My App",
    #     "purpose_mode": "auto",
    # }
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.models import Purpose
from ai_org_backend.services.artifact_resolver import load_by_phase

log = logging.getLogger(__name__)

# Ordered list of phases and their context keys
_PHASE_ORDER: list[tuple[str, str]] = [
    ("vision document", "vision"),
    ("product requirements document", "prd"),
    ("architecture blueprint", "blueprint"),
    ("architecture & domain review", "review"),
    ("implementation plan", "plan"),
]

# Lookup for quick phase-key resolution
_PHASE_KEY_MAP = {desc: key for desc, key in _PHASE_ORDER}
_PHASE_INDEX = {desc: i for i, (desc, _) in enumerate(_PHASE_ORDER)}


def load_cumulative_context(
    purpose_id: str,
    up_to: str | None = None,
    *,
    max_chars_per_phase: int = 50_000,
) -> dict[str, str]:
    """Build cumulative context from all preceding pipeline phases.

    Parameters
    ----------
    purpose_id : str
        The purpose to load artifacts for.
    up_to : str, optional
        Phase description to stop at (inclusive). If None, includes all.
    max_chars_per_phase : int
        Truncate each phase artifact to this many characters to keep
        prompts within token limits.

    Returns
    -------
    dict[str, str]
        Keys are phase abbreviations ("vision", "prd", "blueprint", etc.)
        plus "purpose_name" and "purpose_mode".
    """
    ctx: dict[str, str] = {}

    # Resolve purpose metadata
    try:
        with Session(engine) as session:
            purpose = session.get(Purpose, purpose_id)
            if purpose:
                ctx["purpose_name"] = purpose.name or ""
                ctx["purpose_mode"] = purpose.mode or "manual"
                ctx["tenant_id"] = purpose.tenant_id or ""
            else:
                log.warning("Purpose %s not found for cumulative context", purpose_id)
                ctx["purpose_name"] = ""
                ctx["purpose_mode"] = "manual"
                ctx["tenant_id"] = ""
    except Exception as exc:
        log.error("Failed to load purpose %s: %s", purpose_id, exc)
        ctx["purpose_name"] = ""
        ctx["purpose_mode"] = "manual"
        ctx["tenant_id"] = ""

    # Determine cutoff index
    cutoff = len(_PHASE_ORDER)
    if up_to:
        up_to_lower = up_to.lower()
        if up_to_lower in _PHASE_INDEX:
            cutoff = _PHASE_INDEX[up_to_lower] + 1

    # Load each phase up to the cutoff
    for phase_desc, key in _PHASE_ORDER[:cutoff]:
        try:
            text = load_by_phase(purpose_id, phase_desc)
            if text:
                if len(text) > max_chars_per_phase:
                    text = text[:max_chars_per_phase] + "\n\n[... truncated ...]"
                ctx[key] = text
                log.debug(
                    "Loaded %s for purpose %s (%d chars)",
                    key, purpose_id, len(text),
                )
        except Exception as exc:
            log.warning("Failed to load %s for purpose %s: %s", key, purpose_id, exc)

    return ctx


def context_summary(ctx: dict[str, str]) -> str:
    """Return a one-line summary of which phases are present in a context dict."""
    present = [k for k in ("vision", "prd", "blueprint", "review", "plan") if k in ctx]
    return f"Context phases: {', '.join(present) if present else 'none'}"
