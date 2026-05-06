import unittest

from ai_org_backend.testing_harness import ReplaySnapshot, ReplayStore


class ReplayHarnessTests(unittest.TestCase):
    def test_resume_digest_ignores_timestamps(self):
        store = ReplayStore()
        before = ReplaySnapshot(run_id="r1", checkpoint_id="c1", payload={"value": 1, "timestamp": "a"})
        after = ReplaySnapshot(run_id="r1", checkpoint_id="c1", payload={"value": 1, "timestamp": "b"})

        self.assertTrue(store.is_idempotent_resume(before, after))


if __name__ == "__main__":
    unittest.main()
