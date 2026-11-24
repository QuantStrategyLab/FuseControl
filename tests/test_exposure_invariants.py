#!/usr/bin/env python3
"""G5 (F1-A09): Property tests for exposure-baseline and policy-mutation invariants."""

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'tools'))

import check_exposure_invariants as inv
from fuse_engine import evaluate


class TestExposureInvariants(unittest.TestCase):
    """Verify exposure-baseline and policy-mutation properties across all batteries."""

    @classmethod
    def setUpClass(cls):
        cls.normal_vi = json.loads(
            (REPO_ROOT / 'goldens' / 'scenarios.json').read_text(encoding='utf-8')
        )['scenarios']['normal']['inputs']['validated_inputs']

    def test_all_matrix_precedence_and_fail_closed_batteries_pass(self):
        checked, errors = inv.run_all_batteries()
        self.assertGreaterEqual(checked, 150)
        self.assertEqual(errors, [], f"Invariant violations: {errors}")

    def test_negative_control_detects_o5_collar_tampering(self):
        """R7: Wrapping evaluate() to mutate validated_inputs['o5_collar']=0.99 must be detected."""
        orig_eval = inv.evaluate
        tampered_calls = 0

        def wrapped_eval(*args, **kwargs):
            nonlocal tampered_calls
            res = orig_eval(*args, **kwargs)
            vi_arg = kwargs.get('validated_inputs') if 'validated_inputs' in kwargs else args[6]
            vi_arg['o5_collar'] = 0.99
            tampered_calls += 1
            return res

        inv.evaluate = wrapped_eval
        try:
            checked, errors = inv.run_all_batteries()
        finally:
            inv.evaluate = orig_eval

        self.assertGreater(tampered_calls, 150)
        mut_errors = [e for e in errors if 'caller validated_inputs mutated during evaluate()' in e]
        self.assertGreaterEqual(len(mut_errors), checked)

    def test_negative_control_detects_cap_tampering_during_evaluate(self):
        """R7: Mutating max_loss_cap in-place during evaluate() must be caught."""
        orig_eval = inv.evaluate

        def wrapped_eval(*args, **kwargs):
            res = orig_eval(*args, **kwargs)
            vi_arg = kwargs.get('validated_inputs') if 'validated_inputs' in kwargs else args[6]
            if 'max_loss_cap' in vi_arg:
                vi_arg['max_loss_cap'] = 999999.0
            return res

        inv.evaluate = wrapped_eval
        try:
            _, errors = inv.run_all_batteries()
        finally:
            inv.evaluate = orig_eval

        self.assertTrue(any('caller validated_inputs mutated during evaluate()' in e for e in errors))

    def test_negative_control_detects_mutated_baseline_cap(self):
        """Deliberately raising L0/J1 cap above policy baseline must fail the property check."""
        vi = copy.deepcopy(self.normal_vi)
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        mutated_rows = copy.deepcopy(rows)
        mutated_rows['L0']['outputs']['cap'] = 90000.0  # > max_loss_cap 60000.0
        mutated_rows['J1']['outputs']['cap'] = 90000.0  # > tier_joint_cap 60000.0
        errors = inv.check_bundle_against_baseline('neg.raised_cap', vi, mutated_rows, eff)
        self.assertTrue(any('exceeds policy max_loss_cap' in e for e in errors))
        self.assertTrue(any('exceeds policy tier_joint_cap' in e for e in errors))

    def test_negative_control_detects_mutated_exposure_above_baseline(self):
        """Deliberately clearing trip/block flags when exposure exceeds cap must fail."""
        vi = copy.deepcopy(self.normal_vi)
        vi['max_loss_cap'] = 40000.0
        vi['tier_joint_cap'] = 40000.0
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        # Mutate bundle as if a trip erroneously allowed proposed_exposure=45000 > cap 40000
        mutated_rows = copy.deepcopy(rows)
        mutated_rows['L0']['outputs']['increases_blocked'] = False
        mutated_rows['J1']['outputs']['above_cap'] = False
        mutated_rows['O5']['would_have_tripped'] = False
        mutated_rows['V7']['would_have_tripped'] = False
        mutated_rows['L0']['outputs']['cap'] = 50000.0
        mutated_rows['J1']['outputs']['cap'] = 50000.0
        errors = inv.check_bundle_against_baseline('neg.raised_exposure', vi, mutated_rows, eff)
        self.assertTrue(any('exceeds no-trip baseline' in e for e in errors))

    def test_negative_control_detects_unhalted_joint_scope_on_account_halt(self):
        """Account HALT with non-HALT joint scope must fail dominance/baseline check."""
        vi = copy.deepcopy(self.normal_vi)
        vi['broker_cash'] = 95000.0
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        mutated_eff = copy.deepcopy(eff)
        mutated_eff['joint'] = 'NORMAL'
        errors = inv.check_bundle_against_baseline('neg.joint_unhalted', vi, rows, mutated_eff)
        self.assertTrue(any('account HALT did not dominate joint' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
