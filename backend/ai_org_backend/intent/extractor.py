from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .schema import Action, Domain, InteractionMode, Risk, Scale


class IntentSignals(BaseModel):
    raw_request: str
    domain: Domain | None = None
    action: Action | None = None
    deliverable_type: str | None = None
    target_artifact_id: str | None = None
    target_artifact_type: str | None = None
    scale: Scale | None = None
    interaction_mode: InteractionMode | None = None
    risk: Risk | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    ambiguity_markers: list[str] = Field(default_factory=list)


SignalKind = Literal["domain", "action", "deliverable", "scale", "interaction", "risk"]


_DOMAIN_KEYWORDS: list[tuple[Domain, tuple[str, ...]]] = [
    ("book", ("buch", "manuskript", "kapitel", "outline", "expose", "exposé", "leser")),
    ("research", ("research", "recherche", "quellen", "briefing", "studie", "paper")),
    ("ops", ("deploy", "deployment", "incident", "monitoring", "grafana", "slo", "runbook")),
    (
        "software",
        (
            "code",
            "repo",
            "api",
            "backend",
            "frontend",
            "system",
            "architekt",
            "architektur",
            "architecture",
            "prd",
            "test",
            "pipeline",
        ),
    ),
]

_ACTION_KEYWORDS: list[tuple[Action, tuple[str, ...]]] = [
    ("rework", ("überarbeit", "ueberarbeit", "nachbesser", "rework", "fix", "korrigier")),
    ("review", ("review", "prüf", "pruef", "bewerte", "audit", "check")),
    ("continue", ("weiter", "fortsetzen", "continue", "resume")),
    ("summarize", ("zusammenfass", "summarize", "summary", "kurzfassen")),
    ("translate", ("übersetz", "uebersetz", "translate")),
    ("create", ("erstelle", "schreib", "entwerf", "baue", "implementier", "create", "new", "neu")),
]

_DELIVERABLE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "architecture_blueprint",
        ("architecture blueprint", "architekt", "architektur", "blueprint", "systemdesign"),
    ),
    ("implementation_plan", ("implementierungsplan", "implementation plan", "umsetzungsplan")),
    ("prd", ("prd", "product requirements", "anforderungen", "requirements")),
    ("manuscript", ("manuskript", "buch", "kapitel")),
    ("research_brief", ("research brief", "briefing", "recherchebericht")),
    ("analysis_report", ("analysebericht", "analysis report", "report")),
    ("code_change", ("code", "implementier", "bugfix", "feature")),
    ("test_report", ("testbericht", "qa report", "testergebnis")),
    ("runbook", ("runbook", "incident", "deployment")),
]

_TARGET_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("architecture_blueprint", ("architecture blueprint", "architekt", "architektur", "blueprint")),
    ("implementation_plan", ("implementierungsplan", "implementation plan")),
    ("prd", ("prd", "anforderungen", "requirements")),
    ("manuscript", ("manuskript", "buch")),
    ("artifact", ("artifact", "artefakt", "dokument")),
    ("software_system", ("system", "plattform", "anwendung")),
    ("repository", ("repo", "repository")),
]

_SMALL_KEYWORDS = ("klein", "kurz", "minor", "small", "schnell")
_LARGE_KEYWORDS = ("komplett", "vollständig", "full", "large", "buch", "plattform", "e2e")
_AUTO_KEYWORDS = ("automatisch", "autonom", "auto", "ohne rückfrage", "ohne rueckfrage")
_MANUAL_KEYWORDS = ("manuell", "approval", "freigabe", "reviewer", "rückfrage", "rueckfrage")
_HIGH_RISK_KEYWORDS = (
    "production",
    "prod",
    "payment",
    "security",
    "delete",
    "löschen",
    "loeschen",
    "migration",
    "datenbank",
    "auth",
)
_LOW_RISK_KEYWORDS = ("zusammenfassung", "summary", "doku", "documentation", "lesen")

_ARTIFACT_PATTERNS = [
    re.compile(r"\b(?:artifact|artefakt)[:\s#-]+([a-zA-Z0-9_.:-]{3,})", re.IGNORECASE),
    re.compile(r"\b(?:target|ziel)[:\s#-]+([a-zA-Z0-9_.:-]{3,})", re.IGNORECASE),
    re.compile(r"\b([a-zA-Z]+-[a-zA-Z0-9_.:-]{2,})\b"),
]


def _contains(text: str, keyword: str) -> bool:
    return keyword.lower() in text


def _first_match(text: str, candidates: list[tuple[str, tuple[str, ...]]]) -> tuple[str | None, list[str]]:
    matched: list[str] = []
    for value, keywords in candidates:
        hits = [keyword for keyword in keywords if _contains(text, keyword)]
        if hits:
            matched.extend(hits)
            return value, matched
    return None, matched


def _matched_domains(text: str) -> list[Domain]:
    domains: list[Domain] = []
    for domain, keywords in _DOMAIN_KEYWORDS:
        if any(_contains(text, keyword) for keyword in keywords):
            domains.append(domain)
    return domains


def _artifact_id(text: str) -> str | None:
    for pattern in _ARTIFACT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip(".,;:()[]{}")
    return None


def extract_signals(raw_request: str) -> IntentSignals:
    text = (raw_request or "").strip().lower()
    signals = IntentSignals(raw_request=raw_request)
    if not text:
        signals.ambiguity_markers.append("empty_request")
        return signals

    domains = _matched_domains(text)
    if domains:
        signals.domain = domains[0]
        if len(domains) > 1:
            signals.ambiguity_markers.append("multiple_domains")
    action, action_hits = _first_match(text, _ACTION_KEYWORDS)
    deliverable, deliverable_hits = _first_match(text, _DELIVERABLE_KEYWORDS)
    target_type, target_hits = _first_match(text, _TARGET_TYPE_KEYWORDS)

    signals.action = action  # type: ignore[assignment]
    signals.deliverable_type = deliverable
    signals.target_artifact_type = target_type
    signals.target_artifact_id = _artifact_id(raw_request or "")

    if any(_contains(text, keyword) for keyword in _SMALL_KEYWORDS):
        signals.scale = "small"
        signals.matched_keywords.append("scale:small")
    elif any(_contains(text, keyword) for keyword in _LARGE_KEYWORDS):
        signals.scale = "large"
        signals.matched_keywords.append("scale:large")

    if any(_contains(text, keyword) for keyword in _AUTO_KEYWORDS):
        signals.interaction_mode = "auto"
        signals.matched_keywords.append("interaction:auto")
    elif any(_contains(text, keyword) for keyword in _MANUAL_KEYWORDS):
        signals.interaction_mode = "manual"
        signals.matched_keywords.append("interaction:manual")

    if any(_contains(text, keyword) for keyword in _HIGH_RISK_KEYWORDS):
        signals.risk = "high"
        signals.matched_keywords.append("risk:high")
    elif any(_contains(text, keyword) for keyword in _LOW_RISK_KEYWORDS):
        signals.risk = "low"
        signals.matched_keywords.append("risk:low")

    signals.matched_keywords.extend(action_hits)
    signals.matched_keywords.extend(deliverable_hits)
    signals.matched_keywords.extend(target_hits)
    if "architekt" in text and "überarbeit" in text:
        signals.ambiguity_markers.append("role_vs_rework")
    return signals
