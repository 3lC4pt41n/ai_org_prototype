import unittest

from ai_org_backend.observability import CostRecord, CostTracker, InMemoryRunTracer, OpenLineageEmitter
from ai_org_backend.observability.run_tracer import scrub_attributes


class ObservabilityContractTests(unittest.TestCase):
    def test_scrubber_redacts_pii_by_default(self):
        scrubbed = scrub_attributes({"raw_request": "secret prompt", "intent.domain": "book"})

        self.assertEqual(scrubbed["raw_request"], "<redacted>")
        self.assertEqual(scrubbed["intent.domain"], "book")

    def test_trace_hierarchy_exports_bounded_payload(self):
        tracer = InMemoryRunTracer(max_trace_bytes=10_000)
        root = tracer.start_span("run-1", "request", attributes={"prompt": "hidden"})
        graph = tracer.start_span("run-1", "graph", parent_span_id=root.span_id)
        node = tracer.start_span("run-1", "node", parent_span_id=graph.span_id)
        tracer.end_span(node.span_id)

        exported = tracer.export_trace("run-1")

        self.assertFalse(exported["truncated"])
        self.assertEqual(len(exported["spans"]), 3)
        self.assertEqual(exported["spans"][0]["attributes"]["prompt"], "<redacted>")

    def test_lineage_emits_node_inputs_outputs(self):
        emitter = OpenLineageEmitter()

        event = emitter.emit(
            event_type="COMPLETE",
            run_id="run-1",
            job_name="node.chapter",
            inputs=["outline:v1"],
            outputs=["chapter-1:v1"],
        )

        self.assertEqual(event.outputs[0].name, "chapter-1:v1")
        self.assertEqual(len(emitter.events), 1)

    def test_cost_tracker_summarizes_run_costs(self):
        tracker = CostTracker()
        tracker.record(CostRecord(run_id="run-1", node_id="a", provider="openai", model="m", cost_eur=0.2))
        tracker.record(CostRecord(run_id="run-1", node_id="a", provider="openai", model="m", cost_eur=0.3))
        tracker.record(CostRecord(run_id="run-1", node_id="b", provider="openai", model="m", cost_eur=0.5))

        self.assertEqual(tracker.total_for_run("run-1"), 1.0)
        self.assertEqual(tracker.by_node("run-1"), {"a": 0.5, "b": 0.5})


if __name__ == "__main__":
    unittest.main()
