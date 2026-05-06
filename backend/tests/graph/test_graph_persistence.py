import unittest

from ai_org_backend.graph.persistence import graph_from_record_payloads, graph_to_record_payloads
from ai_org_backend.graph.schema import PipelineEdge, PipelineGraph, PipelineNode
from ai_org_backend.intent.schema import UserIntent


def _intent(raw_request: str = "test") -> UserIntent:
    return UserIntent(
        domain="software",
        action="create",
        deliverable_type="code_change",
        scale="medium",
        interaction_mode="hybrid",
        risk="medium",
        confidence=0.9,
        rationale="test",
        raw_request=raw_request,
    )


def _graph(graph_id: str, raw_request: str = "test") -> PipelineGraph:
    return PipelineGraph(
        id=graph_id,
        template_family="test",
        intent=_intent(raw_request),
        nodes=[
            PipelineNode(id=f"{graph_id}-a", kind="planner", capability="planner"),
            PipelineNode(id=f"{graph_id}-b", kind="generator", capability="writer"),
        ],
        edges=[PipelineEdge(source=f"{graph_id}-a", target=f"{graph_id}-b")],
    ).with_checksum()


class GraphPersistenceTests(unittest.TestCase):
    def test_graph_record_payload_roundtrip(self):
        graph = _graph("g")

        payloads = graph_to_record_payloads(graph)
        restored = graph_from_record_payloads(payloads["graph"], payloads["nodes"], payloads["edges"])

        self.assertEqual(restored.checksum, graph.checksum)
        self.assertEqual(restored.nodes[1].capability, "writer")


if __name__ == "__main__":
    unittest.main()
