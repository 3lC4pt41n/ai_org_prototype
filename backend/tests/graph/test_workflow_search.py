import unittest

from ai_org_backend.graph.workflow_search import WorkflowSearchLimits, bounded_workflow_search
from ai_org_backend.intent.schema import UserIntent


def intent():
    return UserIntent(
        domain="book",
        action="create",
        deliverable_type="manuscript",
        scale="medium",
        interaction_mode="hybrid",
        risk="medium",
        confidence=0.9,
        rationale="test",
        raw_request="write a book",
    )


class WorkflowSearchTests(unittest.TestCase):
    def test_bounded_search_selects_candidate_within_limits(self):
        result = bounded_workflow_search(intent(), WorkflowSearchLimits(max_candidates=2, max_iterations=1))

        self.assertIsNotNone(result.selected_graph)
        self.assertLessEqual(len(result.candidate_scores), 1)
        self.assertEqual(result.selected_graph.template_family, "book_writing")

    def test_search_rejects_when_min_score_too_high(self):
        result = bounded_workflow_search(intent(), WorkflowSearchLimits(min_score=1.0))

        self.assertIsNone(result.selected_graph)
        self.assertIn("below minimum", result.rejected_reason)


if __name__ == "__main__":
    unittest.main()
