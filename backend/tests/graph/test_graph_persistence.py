import unittest

from ai_org_backend.graph.persistence import graph_from_record_payloads, graph_to_record_payloads
from ai_org_backend.graph.schema import PipelineEdge, PipelineGraph, PipelineNode
from ai_org_backend.intent.schema import UserIntent


class GraphPersistenceTests(unittest.TestCase):
    def test_graph_record_payload_roundtrip(self):
        intent = UserIntent(
            domain="software",
            action="create",
            deliverable_type="code_change",
            scale="medium",
            interaction_mode="hybrid",
            risk="medium",
            confidence=0.9,
            rationale="test",
            raw_request="test",
        )
        graph = PipelineGraph(
            id="g",
            template_family="test",
            intent=intent,
            nodes=[PipelineNode(id="a", kind="planner", capability="planner"), PipelineNode(id="b", kind="generator", capability="writer")],
            edges=[PipelineEdge(source="a", target="b")],
        ).with_checksum()

        payloads = graph_to_record_payloads(graph)
        restored = graph_from_record_payloads(payloads["graph"], payloads["nodes"], payloads["edges"])

        self.assertEqual(restored.checksum, graph.checksum)
        self.assertEqual(restored.nodes[1].capability, "writer")


if __name__ == "__main__":
    unittest.main()
