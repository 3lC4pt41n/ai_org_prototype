import unittest

from ai_org_backend.testing_harness import validate_required_fields


class ContractHarnessTests(unittest.TestCase):
    def test_required_field_validation(self):
        result = validate_required_fields(
            {"id": "node-1", "kind": "planner"},
            required={"id", "kind", "capability"},
            allowed={"id", "kind", "capability"},
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.missing_fields, ["capability"])


if __name__ == "__main__":
    unittest.main()
