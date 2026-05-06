import unittest

from ai_org_backend.agents.book.workflow import (
    BookChapter,
    continuity_check,
    plan_outline,
    review_manuscript,
    run_book_smoke_workflow,
    style_harmonize,
    write_chapter,
)


class BookWorkflowTests(unittest.TestCase):
    def test_eight_chapter_smoke_workflow_produces_approved_manuscript(self):
        result = run_book_smoke_workflow("Graphbasierte Agentenarchitekturen", chapter_count=8)

        self.assertEqual(len(result["chapters"]), 8)
        self.assertTrue(result["review"].approved)
        self.assertIn("Chapter 1", result["manuscript"])
        self.assertEqual(len(result["lineage"]), 8)

    def test_continuity_check_detects_adversarial_inconsistency(self):
        outline = plan_outline("A Book", chapter_count=2)
        chapter = write_chapter(outline, 1).model_copy(update={"content": "INCONSISTENT claim"})
        duplicate = BookChapter(index=1, title="Duplicate", content="text")

        report = continuity_check([chapter, duplicate])

        self.assertLess(report.score, 0.85)
        self.assertGreaterEqual(len(report.issues), 2)

    def test_human_style_intervention_does_not_break_review(self):
        outline = plan_outline("A Book", chapter_count=1)
        chapter = write_chapter(outline, 1)
        styled = style_harmonize([chapter], "Tim override: concise and practical.")

        review = review_manuscript(styled)

        self.assertTrue(review.approved)
        self.assertIn("Tim override", styled[0].content)


if __name__ == "__main__":
    unittest.main()
