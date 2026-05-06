import unittest

from ai_org_backend.testing_harness import RubricScorer


class EvalHarnessTests(unittest.TestCase):
    def test_keyword_rubric_scores_fractional_matches(self):
        scorer = RubricScorer(["continuity"])

        scores = scorer.score_keywords("Chapter keeps the same thesis.", {"continuity": ["chapter", "thesis"]})

        self.assertEqual(scores[0].score, 1.0)


if __name__ == "__main__":
    unittest.main()
