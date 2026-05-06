import unittest

from pydantic import ValidationError

from ai_org_backend.services.rework import (
    ArtifactGraph,
    RevisionLimitPolicy,
    evaluate_rework_iteration,
)


class ReworkServiceTests(unittest.TestCase):
    def test_revision_policy_requires_all_bounds(self):
        with self.assertRaises(ValidationError):
            RevisionLimitPolicy(max_revisions=2, convergence_predicate="score >= 0.85", cost_budget={})

    def test_downstream_artifacts_become_stale_from_lowest_recompute_point(self):
        graph = ArtifactGraph()
        graph.add_dependency("architecture_blueprint:v3", "implementation_plan:v2")
        graph.add_dependency("implementation_plan:v2", "code_patch:v1")

        result = graph.mark_downstream_stale("architecture_blueprint:v3")

        self.assertEqual(result.statuses["implementation_plan:v2"], "stale")
        self.assertEqual(result.statuses["code_patch:v1"], "stale")
        self.assertEqual(graph.lowest_recompute_points("architecture_blueprint:v3"), ["implementation_plan:v2"])

    def test_invalidates_edges_mark_downstream_invalidated(self):
        graph = ArtifactGraph()
        graph.add_dependency("policy:v1", "cached_summary:v1", kind="invalidates")

        result = graph.mark_downstream_stale("policy:v1")

        self.assertEqual(result.statuses["cached_summary:v1"], "invalidated")

    def test_rework_loop_stops_at_revision_limit(self):
        policy = RevisionLimitPolicy(
            max_revisions=3,
            convergence_predicate="score >= 0.85",
            cost_budget={"cost_eur": 10.0},
        )

        decision = evaluate_rework_iteration(
            policy=policy,
            revision_count=3,
            score=0.7,
            spent={"cost_eur": 2.0},
        )

        self.assertFalse(decision.should_continue)
        self.assertEqual(decision.terminal_status, "revision_limit_reached")

    def test_convergence_predicate_stops_early(self):
        policy = RevisionLimitPolicy(
            max_revisions=3,
            convergence_predicate="score >= 0.85",
            cost_budget={"cost_eur": 10.0},
        )

        decision = evaluate_rework_iteration(policy=policy, revision_count=1, score=0.9)

        self.assertFalse(decision.should_continue)
        self.assertEqual(decision.terminal_status, "converged")

    def test_budget_exceeded_requires_approval(self):
        policy = RevisionLimitPolicy(
            max_revisions=3,
            convergence_predicate="score >= 0.85",
            cost_budget={"cost_eur": 10.0},
        )

        decision = evaluate_rework_iteration(
            policy=policy,
            revision_count=1,
            score=0.5,
            spent={"cost_eur": 11.0},
        )

        self.assertFalse(decision.should_continue)
        self.assertEqual(decision.terminal_status, "budget_exceeded")
        self.assertTrue(decision.requires_approval)


if __name__ == "__main__":
    unittest.main()
