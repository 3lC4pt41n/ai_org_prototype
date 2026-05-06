import unittest

from ai_org_backend.testing_harness import ChaosHarness


class ChaosHarnessTests(unittest.TestCase):
    def test_provider_outage_resume_is_idempotent(self):
        harness = ChaosHarness()

        self.assertTrue(
            harness.provider_outage_resume_is_idempotent(
                run_id="run-1",
                checkpoint_id="node-a",
                payload={"result": "ok", "created_at": "t1"},
            )
        )


if __name__ == "__main__":
    unittest.main()
