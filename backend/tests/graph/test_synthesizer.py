import random
import unittest

from ai_org_backend.graph.synthesizer import (
    MAX_SYNTH_NODES,
    GraphSynthesisError,
    compile_graph,
    synthesize_graph_from_capabilities,
)
from ai_org_backend.intent.schema import UserIntent


def intent(domain="software", action="create", deliverable_type="unknown_deliverable", **constraints):
    return UserIntent(
        domain=domain,
        action=action,
        deliverable_type=deliverable_type,
        scale="medium",
        interaction_mode="hybrid",
        risk=constraints.pop("risk", "medium"),
        constraints=constraints,
        confidence=constraints.pop("confidence", 0.4),
        rationale="test",
        raw_request="test",
    )


class GraphSynthesizerTests(unittest.TestCase):
    def test_template_fallback_is_used_for_known_high_confidence_intent(self):
        user_intent = intent("book", "create", "manuscript", confidence=0.9)

        graph = compile_graph(user_intent)

        self.assertEqual(graph.template_family, "book_writing")
        self.assertEqual(graph.intent.constraints["graph.origin"], "template")

    def test_synthesizer_uses_only_catalog_capabilities(self):
        graph = synthesize_graph_from_capabilities(intent())

        self.assertEqual(graph.intent.constraints["graph.origin"], "synthesized")
        self.assertLessEqual(len(graph.nodes), MAX_SYNTH_NODES)
        self.assertTrue(all("." in node.capability or node.capability == "human.approval" for node in graph.nodes))

    def test_high_risk_synthesis_adds_approval(self):
        graph = synthesize_graph_from_capabilities(intent(risk="high"))

        self.assertTrue(any(node.kind == "approval" for node in graph.nodes))
        self.assertTrue(all(node.requires_human_approval for node in graph.nodes if node.kind in {"generator", "tool", "repair", "publish"}))

    def test_budget_limit_rejects_expensive_synthesis(self):
        with self.assertRaises(GraphSynthesisError):
            synthesize_graph_from_capabilities(intent(budget={"cost_eur": 0.01}))

    def test_adversarial_intents_never_crash_or_exceed_limits(self):
        domains = ["software", "book", "research", "ops", "general"]
        actions = ["create", "rework", "review", "continue", "summarize", "translate"]
        deliverables = [f"unknown_{idx}" for idx in range(20)]
        random.seed(7)

        for idx in range(20):
            user_intent = intent(
                random.choice(domains),
                random.choice(actions),
                random.choice(deliverables),
                confidence=0.2,
            )
            try:
                graph = synthesize_graph_from_capabilities(user_intent)
            except GraphSynthesisError as exc:
                self.assertIn("capability", str(exc).lower())
            else:
                self.assertLessEqual(len(graph.nodes), MAX_SYNTH_NODES)


if __name__ == "__main__":
    unittest.main()
