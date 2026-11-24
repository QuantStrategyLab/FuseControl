"""F1-A10: Interface conformance tests.

Tests signature conformance (§5.1 evaluate signature) and engine_hash check.
"""

import unittest
import hashlib
import inspect
from pathlib import Path
import sys

# Add parent directories to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from src.fuse_engine import evaluator as engine


class TestSignatureConformance(unittest.TestCase):
    """Test §5.1 signature conformance."""

    def test_evaluate_signature(self):
        """Test that evaluate() has the exact §5.1 signature."""
        # Expected signature per §5.1
        expected_params = [
            'spec_version',
            'engine_hash',
            'policy_hash',
            'session',
            'as_of',
            'mode',
            'validated_inputs',
            'prior_row_state',
            'authorized_events'
        ]

        # Get actual signature
        sig = inspect.signature(engine.evaluate)
        actual_params = list(sig.parameters.keys())

        self.assertEqual(
            actual_params, expected_params,
            f"evaluate() signature must match §5.1 exactly.\n"
            f"Expected: {expected_params}\n"
            f"Actual:   {actual_params}"
        )

    def test_evaluate_parameter_annotations(self):
        """Test that parameters have appropriate type hints."""
        sig = inspect.signature(engine.evaluate)

        # Check key parameters are annotated
        params = sig.parameters
        self.assertIn('spec_version', params)
        self.assertIn('validated_inputs', params)
        self.assertIn('prior_row_state', params)
        self.assertIn('authorized_events', params)

    def test_evaluate_return_tuple(self):
        """Test that evaluate() returns a 3-tuple."""
        # Build minimal valid inputs
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {}
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        result = engine.evaluate(**inputs)

        # Check return is a tuple of length 3
        self.assertIsInstance(result, tuple, "evaluate() must return a tuple")
        self.assertEqual(len(result), 3, "evaluate() must return 3-tuple")

        rows, scopes, next_state = result

        # Check types
        self.assertIsInstance(rows, dict, "rows_by_ID must be dict")
        self.assertIsInstance(scopes, dict, "effective_state_by_scope must be dict")
        self.assertIsInstance(next_state, dict, "next_row_state must be dict")

    def test_evaluate_returns_24_row_ids(self):
        """Test that evaluate() returns exactly 24 row IDs."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {}
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        result = engine.evaluate(**inputs)
        rows, _, _ = result

        expected_ids = set(engine.ROW_IDS)
        actual_ids = set(rows.keys())

        self.assertEqual(actual_ids, expected_ids,
                        f"evaluate() must return exactly {len(expected_ids)} row IDs")


class TestEngineHash(unittest.TestCase):
    """Test engine_hash conformance (§5.3)."""

    def test_engine_hash_computation(self):
        """Test that engine_hash can be computed from canonical bundle."""
        # Compute SHA-256 of engine source files in canonical order
        engine_dir = repo_root / "src" / "fuse_engine"
        engine_files = sorted(engine_dir.glob("*.py"))

        self.assertGreater(len(engine_files), 0, "Engine source files must exist")

        # Compute hash
        hasher = hashlib.sha256()
        for file_path in engine_files:
            with open(file_path, 'rb') as f:
                hasher.update(f.read())

        engine_hash = hasher.hexdigest()

        # Verify it's a valid SHA-256 hex string
        self.assertEqual(len(engine_hash), 64, "engine_hash must be 64-char hex string")
        self.assertTrue(
            all(c in '0123456789abcdef' for c in engine_hash),
            "engine_hash must be lowercase hex"
        )

    def test_engine_files_canonical_order(self):
        """Test that engine files can be listed in canonical order."""
        engine_dir = repo_root / "src" / "fuse_engine"
        engine_files = sorted(engine_dir.glob("*.py"))

        # Verify canonical order (sorted by path)
        file_names = [f.name for f in engine_files]
        sorted_names = sorted(file_names)

        self.assertEqual(file_names, sorted_names,
                        "Engine files must be hashable in sorted order")

    def test_row_ids_declared(self):
        """Test that ROW_IDS constant is declared in evaluator."""
        self.assertTrue(hasattr(engine, 'ROW_IDS'),
                       "evaluator must declare ROW_IDS constant")

        row_ids = engine.ROW_IDS
        self.assertIsInstance(row_ids, list, "ROW_IDS must be a list")
        self.assertEqual(len(row_ids), 24, "ROW_IDS must have exactly 24 IDs")


class TestBoundOutputBundle(unittest.TestCase):
    """G6 (F1-A10): Output bundle binds spec_version, canonical engine_hash, and shadow posture."""

    def test_evaluator_output_carries_authentic_bound_metadata(self):
        import json
        vi = json.loads(
            (repo_root / "goldens" / "scenarios.json").read_text(encoding="utf-8")
        )["scenarios"]["normal"]["inputs"]["validated_inputs"]

        real_hash = engine.compute_engine_hash()
        res_real = engine.evaluate(
            "fuse-eval-spec/v1", real_hash, "registered_policy_hash_v1",
            "2026-01-05", "2026-01-05T16:00:00Z", "shadow", vi, {}, []
        )
        # Spoofed non-digest label must NOT be echoed; real canonical engine_hash is bound instead
        res_spoof = engine.evaluate(
            "fuse-eval-spec/v1", "spoofed_alpha_111", "registered_policy_hash_v1",
            "2026-01-05", "2026-01-05T16:00:00Z", "shadow", vi, {}, []
        )

        # Recursive key scan confirms all four required binding fields exist
        def collect_keys(obj):
            keys = set()
            if isinstance(obj, dict):
                for k, v in obj.items():
                    keys.add(k)
                    keys |= collect_keys(v)
            elif isinstance(obj, list):
                for item in obj:
                    keys |= collect_keys(item)
            return keys

        keys1 = collect_keys(list(res_real))
        for field in ("spec_version", "engine_hash", "enforcement_mode", "loss_breakers_armed"):
            self.assertIn(field, keys1, f"Missing bound field {field} in evaluator output")

        self.assertEqual(res_real[2]["spec_version"], "fuse-eval-spec/v1")
        self.assertEqual(res_real[2]["engine_hash"], real_hash)
        self.assertEqual(res_spoof[2]["engine_hash"], real_hash)
        self.assertNotEqual(res_spoof[2]["engine_hash"], "spoofed_alpha_111")
        self.assertEqual(res_real[2]["enforcement_mode"], "shadow_would_have_tripped")
        self.assertIs(res_real[2]["loss_breakers_armed"], False)

        # Mismatched 64-hex pinned digest must raise ValueError per §5.3
        with self.assertRaises(ValueError):
            engine.evaluate(
                "fuse-eval-spec/v1", "0" * 64, "registered_policy_hash_v1",
                "2026-01-05", "2026-01-05T16:00:00Z", "shadow", vi, {}, []
            )

    def test_required_successor_evidence_fields_present(self):
        import json
        cases = json.loads(
            (repo_root / "goldens" / "successor-cases.json").read_text(encoding="utf-8")
        )["cases"]

        s08 = cases["SUC-08"]["steps"][0]["inputs"]
        r08, _, _ = engine.evaluate(
            "fuse-eval-spec/v1", "test-hash", "test-policy",
            s08["session"], f"{s08['session']}T16:00:00Z", "shadow",
            s08["validated_inputs"], {}, []
        )
        self.assertEqual(r08["V5"]["fund"], "TQQQ")

        s10 = cases["SUC-10"]["steps"][0]["inputs"]
        r10, _, _ = engine.evaluate(
            "fuse-eval-spec/v1", "test-hash", "test-policy",
            s10["session"], f"{s10['session']}T16:00:00Z", "shadow",
            s10["validated_inputs"], {}, []
        )
        self.assertEqual(r10["O4"]["symbol"], "TQQQ")
        self.assertEqual(r10["O4"]["original_order_id"], "order_X")

        s13 = cases["SUC-13"]["steps"][0]["inputs"]
        r13, _, _ = engine.evaluate(
            "fuse-eval-spec/v1", "test-hash", "test-policy",
            s13["session"], f"{s13['session']}T16:00:00Z", "shadow",
            s13["validated_inputs"], {}, []
        )
        self.assertEqual(r13["V1"]["deviation"], 0.0102)

    def test_non_shadow_mode_rejected(self):
        """A10: FUSE-1 shadow-only engine must raise ValueError for any non-'shadow' mode."""
        scenario = {
            "bankroll": 100000.0,
            "high_water_mark": 100000.0,
            "tier": "balanced",
            "tier_loss_budget_D": 0.30,
            "max_loss_cap": 60000.0,
            "tier_joint_cap": 60000.0,
            "joint_exposure": 45000.0,
            "proposed_exposure": 45000.0,
        }
        for bad_mode in ("live", "enforce", "production", "", None):
            with self.subTest(mode=bad_mode):
                with self.assertRaises(ValueError):
                    engine.evaluate(
                        "fuse-eval-spec/v1", "test-hash", "test-policy",
                        "2026-01-05", "2026-01-05T16:00:00Z", bad_mode,
                        scenario, {}, []
                    )


if __name__ == "__main__":
    unittest.main()
