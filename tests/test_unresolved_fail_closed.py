"""F1-A11: UNRESOLVED-FAIL-CLOSED verification.

For each §4.5 register entry marked UNRESOLVED-FAIL-CLOSED:
1. Prove an evaluation that depends on it fails closed when input is absent
2. Grep proof the parameter appears nowhere as a numeric default

UNRESOLVED-FAIL-CLOSED parameters per §4.5:
- V7 spread width (v7_spread_width)
- O5 price collar (o5_collar)
- V5 tolerance (v5_tolerance)
"""

import unittest
from pathlib import Path
import sys
import re

# Add parent directories to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from src.fuse_engine import evaluator as engine


class TestUnresolvedFailClosed(unittest.TestCase):
    """Test that UNRESOLVED-FAIL-CLOSED parameters fail closed."""

    def test_v7_spread_width_unresolved_fails_closed(self):
        """V7: unresolved v7_spread_width fails closed (no order sent)."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {
                    'TQQQ': {
                        'quote_staleness': 0,
                        'spread_width': 0.02,  # Spread present
                        'v7_spread_width': None,  # Threshold unresolved
                        'trading_pause': False,
                        'session_time': 'regular'
                    }
                }
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, _, _ = engine.evaluate(**inputs)
        v7_result = rows['V7']

        # Must fail closed when threshold unresolved
        self.assertEqual(v7_result['state'], 'NORMAL',
                        "V7 with unresolved width must still evaluate")
        self.assertTrue(v7_result['would_have_tripped'],
                       "V7 must trip (fail closed) when v7_spread_width is unresolved")
        self.assertEqual(v7_result['reason'], 'unresolved_fail_closed',
                        "V7 reason must be 'unresolved_fail_closed'")

    def test_o5_collar_unresolved_fails_closed(self):
        """O5: unresolved o5_collar fails closed (order rejected)."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'symbol_whitelist': ['TQQQ', 'SOXL', 'BIL'],
                'account_whitelist': ['test-account'],
                'position_direction': 'long',
                'settled_cash': 50000.0,
                'order_size': 10,
                'session_order_count': 1,
                'session_turnover': 5000.0,
                'o5_collar': None,  # Collar unresolved
                'o5_order_price': 50.0,
                'o5_reference_price': 49.5,
                'funds': {}
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, _, _ = engine.evaluate(**inputs)
        o5_result = rows['O5']

        # Must fail closed when collar unresolved
        self.assertTrue(o5_result['would_have_tripped'],
                       "O5 must trip (fail closed) when o5_collar is unresolved")
        self.assertEqual(o5_result['reason'], 'unresolved_fail_closed',
                        "O5 reason must be 'unresolved_fail_closed'")

    def test_v5_tolerance_unresolved_fails_closed(self):
        """V5: unresolved v5_tolerance fails closed (diagnostic only)."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {
                    'TQQQ': {
                        'shortfall_observed': 0.015,
                        'shortfall_predicted': 0.010,
                        'v5_tolerance': None  # Tolerance unresolved
                    }
                }
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, _, _ = engine.evaluate(**inputs)
        v5_result = rows['V5']

        # Must fail closed when tolerance unresolved (diagnostic trips)
        self.assertEqual(v5_result['kind'], 'diagnostic',
                        "V5 is diagnostic row")
        self.assertTrue(v5_result['would_have_tripped'],
                       "V5 must trip (fail closed) when v5_tolerance is unresolved")
        self.assertEqual(v5_result['reason'], 'unresolved_fail_closed',
                        "V5 reason must be 'unresolved_fail_closed'")

        # Check outputs
        self.assertIn('outputs', v5_result)
        self.assertEqual(v5_result['outputs']['disposition'], 'UNRESOLVED-FAIL-CLOSED',
                        "V5 disposition must be UNRESOLVED-FAIL-CLOSED")
        self.assertIsNone(v5_result['outputs']['excess_shortfall'],
                         "V5 excess_shortfall must be None when unresolved")


class TestNoNumericDefaults(unittest.TestCase):
    """Grep proof: unresolved parameters appear nowhere as numeric defaults."""

    def test_v7_spread_width_no_numeric_default(self):
        """Grep proof: v7_spread_width has no numeric default in spec/ or src/."""
        self._check_no_numeric_default('v7_spread_width')

    def test_o5_collar_no_numeric_default(self):
        """Grep proof: o5_collar has no numeric default in spec/ or src/."""
        self._check_no_numeric_default('o5_collar')

    def test_v5_tolerance_no_numeric_default(self):
        """Grep proof: v5_tolerance has no numeric default in spec/ or src/."""
        self._check_no_numeric_default('v5_tolerance')

    def _check_no_numeric_default(self, param_name: str):
        """Check that parameter has no numeric default in spec/ or src/."""
        # Search spec/ and src/ for the parameter name
        spec_dir = repo_root / "spec"
        src_dir = repo_root / "src"

        violations = []

        # Pattern to find: param_name = <number> or param_name: <number>
        # Allowed: param_name = None, param_name is None, param_name: null
        numeric_pattern = re.compile(
            rf'\b{param_name}\s*[=:]\s*[-+]?\d+\.?\d*',
            re.IGNORECASE
        )

        for directory in [spec_dir, src_dir]:
            for file_path in directory.rglob("*.py"):
                with open(file_path, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        # Skip comments
                        if line.strip().startswith('#'):
                            continue

                        # Check for numeric assignment
                        if numeric_pattern.search(line):
                            violations.append(f"{file_path}:{line_num}: {line.strip()}")

            for file_path in directory.rglob("*.json"):
                with open(file_path, 'r') as f:
                    content = f.read()
                    # Check for "param_name": <number> in JSON
                    if re.search(rf'"{param_name}"\s*:\s*[-+]?\d+\.?\d*', content):
                        violations.append(f"{file_path}: contains numeric value for {param_name}")

        if violations:
            self.fail(
                f"{param_name} must have no numeric default, found:\n" +
                "\n".join(f"  {v}" for v in violations)
            )


if __name__ == "__main__":
    unittest.main()
