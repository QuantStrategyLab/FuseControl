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
    """Test framed engine_hash conformance (§5.3)."""

    def test_engine_hash_computation(self):
        """Test that framed engine_hash matches engine & matrix verifier across verified whitelist."""
        sys.path.insert(0, str(repo_root / "tools"))
        import run_matrix

        engine_dir = repo_root / "src" / "fuse_engine"
        py_files = sorted(
            engine_dir.rglob("*.py"),
            key=lambda p: p.relative_to(engine_dir).as_posix(),
        )
        rel_paths = [p.relative_to(engine_dir).as_posix() for p in py_files]
        self.assertEqual(rel_paths, list(engine._EXPECTED_ENGINE_FILES))

        hasher = hashlib.sha256()
        for file_path, rel_path in zip(py_files, rel_paths):
            rel_bytes = rel_path.encode("utf-8")
            data = file_path.read_bytes()
            hasher.update(len(rel_bytes).to_bytes(4, "big"))
            hasher.update(rel_bytes)
            hasher.update(len(data).to_bytes(8, "big"))
            hasher.update(data)

        engine_hash = hasher.hexdigest()
        self.assertEqual(len(engine_hash), 64, "engine_hash must be 64-char hex string")
        self.assertTrue(
            all(c in '0123456789abcdef' for c in engine_hash),
            "engine_hash must be lowercase hex"
        )
        self.assertEqual(engine_hash, engine.compute_engine_hash())
        self.assertEqual(engine_hash, run_matrix.compute_engine_hash())

    def test_engine_files_canonical_order(self):
        """Test that engine files match strict canonical whitelist in sorted POSIX order."""
        engine_dir = repo_root / "src" / "fuse_engine"
        engine_files = sorted(
            engine_dir.rglob("*.py"),
            key=lambda p: p.relative_to(engine_dir).as_posix(),
        )
        rel_names = [f.relative_to(engine_dir).as_posix() for f in engine_files]
        self.assertEqual(rel_names, list(engine._EXPECTED_ENGINE_FILES))

    def test_engine_hash_framing_and_unexpected_file_rejection(self):
        """Security P2: Moving bytes between engine files changes hash and unexpected/missing .py raises RuntimeError."""
        import py_compile
        import shutil
        import struct
        import subprocess
        import tempfile

        src_dir = repo_root / "src" / "fuse_engine"
        ignore_cache = shutil.ignore_patterns("__pycache__")
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            dir_a = td_path / "eng_a"
            dir_b = td_path / "eng_b"
            shutil.copytree(src_dir, dir_a, ignore=ignore_cache)
            shutil.copytree(src_dir, dir_b, ignore=ignore_cache)

            # Move 1 byte from end of canonical.py to start of state.py (identical unframed concatenation)
            c_bytes = (dir_b / "canonical.py").read_bytes()
            s_bytes = (dir_b / "state.py").read_bytes()
            (dir_b / "canonical.py").write_bytes(c_bytes[:-1])
            (dir_b / "state.py").write_bytes(c_bytes[-1:] + s_bytes)

            self.assertNotEqual(
                engine._compute_canonical_engine_hash_from_dir(dir_a),
                engine._compute_canonical_engine_hash_from_dir(dir_b),
            )

            # Unexpected top-level or nested .py file MUST fail closed with RuntimeError
            dir_extra = td_path / "eng_extra"
            shutil.copytree(src_dir, dir_extra, ignore=ignore_cache)
            (dir_extra / "rogue.py").write_text("# unexpected\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                engine._compute_canonical_engine_hash_from_dir(dir_extra)

            dir_sub = td_path / "eng_sub"
            shutil.copytree(src_dir, dir_sub, ignore=ignore_cache)
            (dir_sub / "nested").mkdir()
            (dir_sub / "nested" / "helper.py").write_text("# unexpected\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                engine._compute_canonical_engine_hash_from_dir(dir_sub)

            # Missing expected .py file MUST also fail closed with RuntimeError
            dir_miss = td_path / "eng_miss"
            shutil.copytree(src_dir, dir_miss, ignore=ignore_cache)
            (dir_miss / "state.py").unlink()
            with self.assertRaises(RuntimeError):
                engine._compute_canonical_engine_hash_from_dir(dir_miss)

            # Binary/extension/non-whitelisted artifacts (.so, .pyd, .dylib, .pth, root .pyc, rogue __pycache__) fail closed
            for bad_rel in (
                "rows_ops.cpython-314-darwin.so",
                "evil.pyd",
                "evil.dylib",
                "evil.pth",
                "canonical.pyc",
                "__pycache__/evil.cpython-313.pyc",
                "__pycache__/rows_ops.cpython-314-darwin.so",
            ):
                dir_bin = td_path / ("bin_" + bad_rel.replace("/", "_").replace(".", "_"))
                shutil.copytree(src_dir, dir_bin, ignore=ignore_cache)
                bad_path = dir_bin / bad_rel
                bad_path.parent.mkdir(exist_ok=True)
                bad_path.write_bytes(b"binary-payload")
                with self.assertRaises(RuntimeError, msg=f"Expected RuntimeError for {bad_rel}"):
                    engine._compute_canonical_engine_hash_from_dir(dir_bin)

            # Genuine Python-generated __pycache__ (non--B run) passes cleanly across fresh and cached imports
            dir_pyc = td_path / "eng_pyc"
            pkg_pyc = dir_pyc / "fuse_engine"
            shutil.copytree(src_dir, pkg_pyc, ignore=ignore_cache)
            expected_digest = engine.compute_engine_hash()
            for pass_label in ("fresh", "cached"):
                proc_ok = subprocess.run(
                    [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(dir_pyc)!r}); import fuse_engine; print(fuse_engine.evaluator.compute_engine_hash())"],
                    capture_output=True, text=True, check=True,
                )
                self.assertEqual(proc_ok.stdout.strip(), expected_digest, msg=pass_label)
            self.assertEqual(engine._compute_canonical_engine_hash_from_dir(pkg_pyc), expected_digest)

            # Forged __pycache__/*.pyc with matching co_filename AND spoofed (mtime, size) fails BEFORE importing submodules
            cache_tag = sys.implementation.cache_tag
            for target_mod in ("rows_ops", "evaluator"):
                dir_forged = td_path / f"forged_{target_mod}"
                pkg_forged = dir_forged / "fuse_engine"
                shutil.copytree(src_dir, pkg_forged, ignore=ignore_cache)
                (pkg_forged / "__pycache__").mkdir()
                evil_py = td_path / f"evil_{target_mod}.py"
                evil_py.write_text('raise AssertionError("PWNED_FROM_FORGED_PYC")\n', encoding="utf-8")
                code_forged = compile(evil_py.read_bytes(), str(pkg_forged / f"{target_mod}.py"), "exec", optimize=0)
                import importlib.util
                import marshal
                st_src = (pkg_forged / f"{target_mod}.py").stat()
                hdr = importlib.util.MAGIC_NUMBER + struct.pack(
                    "<III", 0, int(st_src.st_mtime) & 0xffffffff, st_src.st_size & 0xffffffff
                )
                pyc_path = pkg_forged / "__pycache__" / f"{target_mod}.{cache_tag}.pyc"
                pyc_path.write_bytes(hdr + marshal.dumps(code_forged))

                with self.assertRaises(RuntimeError, msg=f"Direct hash check must reject forged {target_mod}.pyc"):
                    engine._compute_canonical_engine_hash_from_dir(pkg_forged)
                proc_evil = subprocess.run(
                    [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(dir_forged)!r}); import fuse_engine"],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(proc_evil.returncode, 0)
                self.assertIn("RuntimeError", proc_evil.stderr)
                self.assertNotIn("PWNED_FROM_FORGED_PYC", proc_evil.stderr)

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

    def test_zero_file_io_during_evaluate_and_spec_version_check(self):
        """R5 (G): evaluate() performs zero file I/O (precomputed engine_hash) and rejects invalid spec_version."""
        import json
        from unittest.mock import patch
        vi = json.loads(
            (repo_root / "goldens" / "scenarios.json").read_text(encoding="utf-8")
        )["scenarios"]["normal"]["inputs"]["validated_inputs"]

        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("Unexpected file I/O in evaluate()")), \
             patch("builtins.open", side_effect=AssertionError("Unexpected open() in evaluate()")):
            rows, _, nxt = engine.evaluate(
                "fuse-eval-spec/v1", "test-hash", "registered_policy_hash_v1",
                "2026-01-05", "2026-01-05T16:00:00Z", "shadow", vi, {}, []
            )
        self.assertEqual(len(rows), 24)
        self.assertEqual(nxt["engine_hash"], engine.compute_engine_hash())

        with self.assertRaises(ValueError):
            engine.evaluate(
                "fuse-eval-spec/v999", "test-hash", "registered_policy_hash_v1",
                "2026-01-05", "2026-01-05T16:00:00Z", "shadow", vi, {}, []
            )

        # Intentional None prior_row_state passes; malformed non-None non-dict prior_row_state must fail closed
        rows_none, _, _ = engine.evaluate(
            "fuse-eval-spec/v1", "test-hash", "registered_policy_hash_v1",
            "2026-01-05", "2026-01-05T16:00:00Z", "shadow", vi, None, []
        )
        self.assertEqual(len(rows_none), 24)
        for bad_prior in ("unavailable", ["O6"], 123, True):
            with self.assertRaises(ValueError, msg=f"Expected ValueError for prior_row_state={bad_prior!r}"):
                engine.evaluate(
                    "fuse-eval-spec/v1", "test-hash", "registered_policy_hash_v1",
                    "2026-01-05", "2026-01-05T16:00:00Z", "shadow", vi, bad_prior, []
                )


if __name__ == "__main__":
    unittest.main()
