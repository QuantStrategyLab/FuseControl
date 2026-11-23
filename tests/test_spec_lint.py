"""Test suite for spec linter (F1-A02)."""

import unittest
from pathlib import Path
import sys

# Add tools directory to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "tools"))

from lint_spec import lint_spec, EXPECTED_IDS


class TestSpecLint(unittest.TestCase):
    """Test the spec linter against spec/spec.json."""

    def setUp(self):
        """Set up test fixtures."""
        self.spec_path = repo_root / "spec" / "spec.json"
        self.assertTrue(
            self.spec_path.exists(),
            f"Spec file not found: {self.spec_path}"
        )

    def test_spec_lint_passes(self):
        """Test that the spec passes linting."""
        success, errors = lint_spec(self.spec_path)

        if not success:
            self.fail(f"Spec linting failed with errors:\n" + "\n".join(f"  - {e}" for e in errors))

        self.assertTrue(success, "Spec should pass linting")
        self.assertEqual(errors, [], "Should have no errors")

    def test_expected_id_count(self):
        """Verify EXPECTED_IDS has exactly 24 IDs."""
        self.assertEqual(
            len(EXPECTED_IDS), 24,
            f"EXPECTED_IDS should have 24 IDs, found {len(EXPECTED_IDS)}"
        )

    def test_expected_id_composition(self):
        """Verify EXPECTED_IDS contains the correct ID ranges."""
        loss_ids = {f"L{i}" for i in range(7)}
        vehicle_ids = {f"V{i}" for i in range(1, 8)}
        ops_ids = {f"O{i}" for i in range(1, 10)}
        joint_ids = {"J1"}

        expected = loss_ids | vehicle_ids | ops_ids | joint_ids

        self.assertEqual(
            EXPECTED_IDS, expected,
            "EXPECTED_IDS should equal L0-L6, V1-V7, O1-O9, J1"
        )


if __name__ == "__main__":
    unittest.main()
