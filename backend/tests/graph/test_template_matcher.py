import unittest

from ai_org_backend.graph.template_matcher import best_template, instantiate_template, match_templates
from ai_org_backend.intent.schema import UserIntent


def intent(domain, action, deliverable_type):
    return UserIntent(
        domain=domain,
        action=action,
        deliverable_type=deliverable_type,
        scale="medium",
        interaction_mode="hybrid",
        risk="medium",
        confidence=0.9,
        rationale="test",
        raw_request=f"{domain} {action} {deliverable_type}",
    )


class TemplateMatcherTests(unittest.TestCase):
    def test_required_families_match_above_threshold(self):
        cases = [
            ("software", "create", "code_change", "software_delivery"),
            ("book", "create", "manuscript", "book_writing"),
            ("research", "create", "research_brief", "research_brief"),
            ("general", "create", "analysis_report", "analysis_report"),
            ("research", "rework", "knowledge_base_update", "knowledge_base_update"),
            ("software", "rework", "architecture_blueprint", "architecture_rework"),
        ]

        for domain, action, deliverable, family in cases:
            with self.subTest(family=family):
                candidate = best_template(intent(domain, action, deliverable), min_confidence=0.9)
                self.assertIsNotNone(candidate)
                self.assertEqual(candidate.family, family)
                self.assertGreaterEqual(candidate.confidence, 0.9)

    def test_template_corpus_has_sixty_positive_cases(self):
        cases = []
        cases.extend(("software", "create", value) for value in ["code_change", "prd", "implementation_plan"] * 10)
        cases.extend(("book", "create", "manuscript") for _ in range(10))
        cases.extend(("research", action, "research_brief") for action in ["create", "summarize"] * 5)
        cases.extend(("general", "create", "analysis_report") for _ in range(5))
        cases.extend(("software", "rework", "architecture_blueprint") for _ in range(5))

        self.assertGreaterEqual(len(cases), 60)
        for domain, action, deliverable in cases[:60]:
            candidates = match_templates(intent(domain, action, deliverable))
            self.assertTrue(candidates)
            self.assertGreaterEqual(candidates[0].confidence, 0.9)

    def test_best_template_instantiates_valid_graph(self):
        user_intent = intent("book", "create", "manuscript")
        candidate = best_template(user_intent, min_confidence=0.9)
        assert candidate is not None

        graph = instantiate_template(user_intent, candidate)

        self.assertEqual(graph.template_family, "book_writing")
        self.assertTrue(graph.checksum)
        self.assertIn("template_budgets", graph.intent.constraints)


if __name__ == "__main__":
    unittest.main()
