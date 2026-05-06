import unittest

from ai_org_backend.graph.adapters.legacy_phases import graph_to_legacy_phase_dicts, legacy_phases_to_graph
from ai_org_backend.graph.engine import CeleryEngine
from ai_org_backend.graph.schema import PipelineEdge, PipelineGraph, PipelineNode
from ai_org_backend.graph.validator import validate_graph
from ai_org_backend.intent.schema import UserIntent


def intent(**overrides):
    data = {
        "domain": "software",
        "action": "create",
        "deliverable_type": "code_change",
        "scale": "medium",
        "interaction_mode": "hybrid",
        "risk": "medium",
        "confidence": 0.9,
        "rationale": "test",
        "raw_request": "test",
    }
    data.update(overrides)
    return UserIntent(**data)


class PipelineGraphContractTests(unittest.TestCase):
    def test_checksum_is_deterministic(self):
        graph = PipelineGraph(
            id="g1",
            intent=intent(),
            nodes=[PipelineNode(id="a", kind="planner", capability="planner")],
            edges=[],
        ).with_checksum()

        self.assertEqual(graph.checksum, graph.compute_checksum())
        self.assertEqual(graph.checksum, graph.with_checksum().checksum)

    def test_validator_rejects_unbounded_cycles(self):
        graph = PipelineGraph(
            id="cycle",
            intent=intent(),
            nodes=[
                PipelineNode(id="a", kind="planner", capability="planner"),
                PipelineNode(id="b", kind="repair", capability="repair"),
            ],
            edges=[
                PipelineEdge(source="a", target="b"),
                PipelineEdge(source="b", target="a", edge_type="feedback"),
            ],
        )

        result = validate_graph(graph)

        self.assertFalse(result.valid)
        self.assertIn("unbounded_cycle", {issue.code for issue in result.issues})

    def test_validator_accepts_bounded_feedback_cycle(self):
        graph = PipelineGraph(
            id="bounded",
            intent=intent(),
            nodes=[
                PipelineNode(id="review", kind="evaluator", capability="review"),
                PipelineNode(
                    id="repair",
                    kind="repair",
                    capability="repair",
                    max_revisions=2,
                    cost_budget={"tokens": 1000},
                    metadata={"convergence_predicate": "score >= 0.85"},
                ),
            ],
            edges=[
                PipelineEdge(source="review", target="repair", condition="score < 0.85"),
                PipelineEdge(source="repair", target="review", edge_type="feedback"),
            ],
        )

        self.assertTrue(validate_graph(graph).valid)

    def test_validator_rejects_high_risk_without_approval(self):
        graph = PipelineGraph(
            id="risk",
            intent=intent(risk="high"),
            nodes=[PipelineNode(id="publish", kind="publish", capability="release.publish")],
            edges=[],
        )

        result = validate_graph(graph)

        self.assertFalse(result.valid)
        self.assertIn("high_risk_without_approval", {issue.code for issue in result.issues})

    def test_legacy_phase_adapter_roundtrips(self):
        phases = [
            {"id": "p1", "slug": "vision", "name": "Vision", "position": 1, "agent_role": "vision"},
            {
                "id": "p2",
                "slug": "architecture",
                "name": "Architecture",
                "position": 2,
                "predecessor_id": "p1",
                "agent_role": "architect",
            },
        ]

        graph = legacy_phases_to_graph(graph_id="legacy", intent=intent(), phases=phases)
        restored = graph_to_legacy_phase_dicts(graph)

        self.assertTrue(validate_graph(graph).valid)
        self.assertEqual([phase["slug"] for phase in restored], ["vision", "architecture"])

    def test_celery_engine_adapter_is_submit_compatible(self):
        graph = PipelineGraph(
            id="submit",
            intent=intent(),
            nodes=[PipelineNode(id="a", kind="planner", capability="planner")],
            edges=[],
        )
        engine = CeleryEngine()

        run_id = engine.submit(graph, {"x": 1})

        self.assertTrue(run_id.startswith("celery:submit:"))
        self.assertEqual(engine.status(run_id).state, "queued")


if __name__ == "__main__":
    unittest.main()
