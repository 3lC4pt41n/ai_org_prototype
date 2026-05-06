import unittest

from ai_org_backend.intent import IntentCompiler, compile_intent, legacy_role_for_intent
from ai_org_backend.intent.schema import UserIntent
from ai_org_backend.intent.validator import validate_intent


ARTIFACTS = {
    "arch-v3": {"type": "architecture_blueprint", "latest_version_id": "arch-v3"},
    "prd-v2": {"type": "prd", "latest_version_id": "prd-v2"},
    "plan-v4": {"type": "implementation_plan", "latest_version_id": "plan-v4"},
    "book-v1": {"type": "manuscript", "latest_version_id": "book-v1"},
}


def artifact_lookup(artifact_id: str):
    return ARTIFACTS.get(artifact_id)


class IntentCompilerGoldenTests(unittest.TestCase):
    def setUp(self):
        self.compiler = IntentCompiler(artifact_lookup=artifact_lookup)

    def assert_compiled(self, raw_request: str, expected: dict[str, object]) -> None:
        compiled = self.compiler.compile(raw_request)
        for field, value in expected.items():
            with self.subTest(raw_request=raw_request, field=field):
                if field == "requires_clarification":
                    self.assertEqual(compiled.requires_clarification, value)
                elif field == "legacy_role":
                    self.assertEqual(compiled.legacy_role, value)
                else:
                    self.assertEqual(getattr(compiled.intent, field), value)

    def test_golden_intent_cases(self):
        cases = [
            (
                "bitte als Architekt das System X überarbeiten",
                {
                    "domain": "software",
                    "action": "rework",
                    "deliverable_type": "architecture_blueprint",
                    "target_artifact_type": "architecture_blueprint",
                    "requires_clarification": True,
                    "legacy_role": "architect",
                },
            ),
            (
                "bitte ein neues System X entwerfen",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "code_change",
                    "target_artifact_type": "software_system",
                    "requires_clarification": False,
                    "legacy_role": "dev",
                },
            ),
            (
                "Überarbeite Artefakt:arch-v3 architecture blueprint",
                {
                    "domain": "software",
                    "action": "rework",
                    "deliverable_type": "architecture_blueprint",
                    "target_artifact_id": "arch-v3",
                    "requires_clarification": False,
                    "legacy_role": "architect",
                },
            ),
            (
                "Review Artefakt:arch-v3 architecture blueprint",
                {
                    "domain": "software",
                    "action": "review",
                    "deliverable_type": "architecture_blueprint",
                    "target_artifact_id": "arch-v3",
                    "requires_clarification": False,
                    "legacy_role": "reviewer",
                },
            ),
            (
                "Erstelle ein PRD für die neue API",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "prd",
                    "requires_clarification": False,
                    "legacy_role": "po",
                },
            ),
            (
                "Implementiere den Backend API Bugfix",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "code_change",
                    "requires_clarification": False,
                    "legacy_role": "dev",
                },
            ),
            (
                "Schreib mir ein Buch mit acht Kapiteln",
                {
                    "domain": "book",
                    "action": "create",
                    "deliverable_type": "manuscript",
                    "scale": "large",
                    "requires_clarification": False,
                    "legacy_role": "dev",
                },
            ),
            (
                "Überarbeite Artefakt:book-v1 Manuskript",
                {
                    "domain": "book",
                    "action": "rework",
                    "deliverable_type": "manuscript",
                    "target_artifact_id": "book-v1",
                    "requires_clarification": False,
                },
            ),
            (
                "Erstelle eine Recherche zu Graph-basierten Agenten",
                {
                    "domain": "research",
                    "action": "create",
                    "deliverable_type": "research_brief",
                    "requires_clarification": False,
                    "legacy_role": "insight",
                },
            ),
            (
                "Fasse die Studie kurz zusammen",
                {
                    "domain": "research",
                    "action": "summarize",
                    "deliverable_type": "research_brief",
                    "scale": "small",
                    "risk": "low",
                    "requires_clarification": False,
                },
            ),
            (
                "Übersetze das Research Brief ins Englische",
                {
                    "domain": "research",
                    "action": "translate",
                    "deliverable_type": "research_brief",
                    "requires_clarification": False,
                },
            ),
            (
                "Erstelle ein Deployment Runbook",
                {
                    "domain": "ops",
                    "action": "create",
                    "deliverable_type": "runbook",
                    "requires_clarification": False,
                    "legacy_role": "telemetry",
                },
            ),
            (
                "Prüfe Monitoring und Grafana SLOs",
                {
                    "domain": "ops",
                    "action": "review",
                    "deliverable_type": "runbook",
                    "legacy_role": "telemetry",
                },
            ),
            (
                "Erstelle einen Analysebericht für die Daten",
                {
                    "domain": "general",
                    "action": "create",
                    "deliverable_type": "analysis_report",
                    "requires_clarification": True,
                },
            ),
            (
                "Review den Code mit Lint und static analysis",
                {
                    "domain": "software",
                    "action": "review",
                    "deliverable_type": "code_change",
                    "legacy_role": "qa_review",
                },
            ),
            (
                "Refactor cleanup im Backend",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "code_change",
                    "legacy_role": "qa_refactor",
                },
            ),
            (
                "Baue Docker Compose Setup für das Repo",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "code_change",
                    "legacy_role": "repo",
                },
            ),
            (
                "Erstelle Tests mit pytest für die API",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "test_report",
                    "legacy_role": "qa",
                },
            ),
            (
                "Prüfe Performance p95 im Backend",
                {
                    "domain": "ops",
                    "action": "review",
                    "deliverable_type": "runbook",
                    "risk": "medium",
                    "legacy_role": "telemetry",
                },
            ),
            (
                "Bitte Security OWASP Check für die API",
                {
                    "domain": "software",
                    "action": "review",
                    "deliverable_type": "security_report",
                    "risk": "high",
                    "legacy_role": "telemetry",
                },
            ),
            (
                "Continue work on the repository pipeline",
                {
                    "domain": "software",
                    "action": "continue",
                    "deliverable_type": "code_change",
                    "legacy_role": "repo",
                },
            ),
            (
                "Auto implementier das kleine Backend Feature",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "code_change",
                    "scale": "small",
                    "interaction_mode": "auto",
                    "requires_clarification": False,
                },
            ),
            (
                "Manuelle Freigabe für architecture blueprint Review",
                {
                    "domain": "software",
                    "action": "review",
                    "deliverable_type": "architecture_blueprint",
                    "interaction_mode": "manual",
                    "legacy_role": "reviewer",
                },
            ),
            (
                "Implementierungsplan Artefakt:plan-v4 überarbeiten",
                {
                    "domain": "software",
                    "action": "rework",
                    "deliverable_type": "implementation_plan",
                    "target_artifact_id": "plan-v4",
                    "legacy_role": "architect",
                },
            ),
            (
                "PRD Artefakt:prd-v2 zusammenfassen",
                {
                    "domain": "software",
                    "action": "summarize",
                    "deliverable_type": "prd",
                    "target_artifact_id": "prd-v2",
                    "risk": "low",
                    "legacy_role": "po",
                },
            ),
            (
                "Create research brief from sources",
                {
                    "domain": "research",
                    "action": "create",
                    "deliverable_type": "research_brief",
                    "legacy_role": "insight",
                },
            ),
            (
                "Translate manuscript chapter",
                {
                    "domain": "book",
                    "action": "translate",
                    "deliverable_type": "manuscript",
                },
            ),
            (
                "Review product requirements",
                {
                    "domain": "software",
                    "action": "review",
                    "deliverable_type": "prd",
                    "legacy_role": "po",
                },
            ),
            (
                "Kleine Doku Zusammenfassung lesen",
                {
                    "domain": "general",
                    "action": "summarize",
                    "deliverable_type": "general_response",
                    "scale": "small",
                    "risk": "low",
                    "requires_clarification": True,
                },
            ),
            (
                "Erstelle vollständige Plattform Pipeline",
                {
                    "domain": "software",
                    "action": "create",
                    "deliverable_type": "code_change",
                    "scale": "large",
                    "target_artifact_type": "software_system",
                },
            ),
        ]

        self.assertGreaterEqual(len(cases), 30)
        for raw_request, expected in cases:
            self.assert_compiled(raw_request, expected)

    def test_adversarial_cases_hit_clarification_gate(self):
        adversarial = [
            "",
            "überarbeite das bitte",
            "Schreib ein Buch als architecture blueprint",
            "lösche prod database automatisch",
            "Review Artefakt:missing-999",
        ]

        for raw_request in adversarial:
            with self.subTest(raw_request=raw_request):
                compiled = self.compiler.compile(raw_request)
                self.assertTrue(compiled.requires_clarification)
                self.assertTrue(compiled.validation.issues)

    def test_user_intent_can_be_validated_after_manual_edit(self):
        intent = UserIntent(
            domain="software",
            action="create",
            deliverable_type="architecture_blueprint",
            scale="medium",
            interaction_mode="hybrid",
            risk="medium",
            confidence=0.91,
            rationale="manual correction",
            raw_request="neues System entwerfen",
        )

        validation = validate_intent(intent)

        self.assertTrue(validation.valid)
        self.assertFalse(validation.needs_clarification)
        self.assertEqual(legacy_role_for_intent(intent), "architect")

    def test_module_level_compile_helper(self):
        compiled = compile_intent("Erstelle ein PRD für die API")

        self.assertEqual(compiled.intent.deliverable_type, "prd")
        self.assertEqual(compiled.legacy_role, "po")

    def test_llm_fallback_can_recover_low_confidence_intent(self):
        def fake_llm(_raw_request: str):
            return {
                "domain": "book",
                "action": "create",
                "deliverable_type": "manuscript",
                "scale": "large",
                "interaction_mode": "hybrid",
                "risk": "medium",
                "confidence": 0.91,
                "rationale": "LLM recognized a long-form book request.",
                "raw_request": "ignored because compiler preserves original",
            }

        compiled = compile_intent(
            "großes langes Werk ohne klare Schlüsselwörter",
            llm_classifier=fake_llm,
        )

        self.assertEqual(compiled.intent.domain, "book")
        self.assertEqual(compiled.intent.action, "create")
        self.assertEqual(compiled.intent.deliverable_type, "manuscript")
        self.assertEqual(compiled.intent.raw_request, "großes langes Werk ohne klare Schlüsselwörter")
        self.assertEqual(compiled.intent.constraints["classification_source"], "llm")
        self.assertFalse(compiled.requires_clarification)


if __name__ == "__main__":
    unittest.main()
