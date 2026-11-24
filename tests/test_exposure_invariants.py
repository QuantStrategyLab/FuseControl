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

    def test_negative_control_detects_j1_headroom_inflation(self):
        """A09: Inflating J1.outputs.headroom must fail invariant checks even when caps match."""
        vi = copy.deepcopy(self.normal_vi)
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        mutated_rows = copy.deepcopy(rows)
        mutated_rows['J1']['outputs']['headroom'] += 1_000_000.0
        errors = inv.check_bundle_against_baseline('neg.headroom_inflated', vi, mutated_rows, eff)
        self.assertTrue(any('headroom' in e for e in errors))

    def test_sole_fund_no_new_risk_blocks_exposure_increase(self):
        """A09: Sole-fund NO-NEW-RISK blocks raising exposure from 45,000 to 50,000."""
        vi = copy.deepcopy(self.normal_vi)
        vi['joint_exposure'] = 45000.0
        vi['proposed_exposure'] = 50000.0
        vi['tier_joint_cap'] = 60000.0
        rows, _, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        eff = {'account': 'NORMAL', 'fund:TQQQ': 'NO-NEW-RISK', 'symbol:TQQQ': 'NORMAL', 'joint': 'NORMAL'}
        permitted = inv.compute_permitted_exposure(vi, rows, eff)
        self.assertEqual(permitted, 45000.0)

    def test_negative_control_detects_missing_j1_cap(self):
        """A09: Removing J1.outputs.cap (setting None) must fail invariant checks."""
        vi = copy.deepcopy(self.normal_vi)
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        mutated_rows = copy.deepcopy(rows)
        mutated_rows['J1']['outputs']['cap'] = None
        errors = inv.check_bundle_against_baseline('neg.missing_j1_cap', vi, mutated_rows, eff)
        self.assertTrue(any('J1.outputs.cap missing or non-finite' in e for e in errors))

    def test_permits_genuine_reduction_under_no_new_risk(self):
        """A09: Genuine exposure reduction (45,000 -> 40,000) under account NO-NEW-RISK has 0 errors."""
        vi = copy.deepcopy(self.normal_vi)
        vi.update({'joint_exposure': 45000.0, 'proposed_exposure': 40000.0, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        eff_nnr = {**eff, 'account': 'NO-NEW-RISK'}
        self.assertEqual(inv.compute_permitted_exposure(vi, rows, eff_nnr), 40000.0)
        errors = inv.check_bundle_against_baseline('pos.reduce_45_to_40', vi, rows, eff_nnr)
        self.assertEqual(errors, [])

    def test_permits_unrestricted_fund_purchase_when_other_fund_restricted(self):
        """A09: Buying normal SOXL when only TQQQ is NO-NEW-RISK permits 50,000 cleanly."""
        vi = copy.deepcopy(self.normal_vi)
        vi.update({'joint_exposure': 45000.0, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, 'o5_collar': 0.05, 'o5_symbol': 'SOXL'})
        vi['funds']['TQQQ'].update({'forecast_volatility': 0.60, 'v5_tolerance': 0.01})
        vi['funds']['SOXL'].update({'v5_tolerance': 0.01})
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        self.assertEqual(eff['fund:TQQQ'], 'NO-NEW-RISK')
        self.assertEqual(eff['fund:SOXL'], 'NORMAL')
        self.assertEqual(inv.compute_permitted_exposure(vi, rows, eff), 50000.0)
        errors = inv.check_bundle_against_baseline('pos.buy_soxl_only_tqqq_nnr', vi, rows, eff)
        self.assertEqual(errors, [])

    def test_r5_symbol_key_v7_per_symbol_and_negative_j1_headroom(self):
        """R5 (G/A09): Captures symbol='TQQQ' NNR increase, permits SOXL when TQQQ has V7, and handles negative J1 headroom."""
        vi_blk = copy.deepcopy(self.normal_vi)
        vi_blk.update({'joint_exposure': 45000.0, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, 'o5_collar': 0.05, 'symbol': 'TQQQ'})
        vi_blk['funds']['TQQQ'].update({'forecast_volatility': 0.60, 'v5_tolerance': 0.01})
        vi_blk['funds']['SOXL'].update({'v5_tolerance': 0.01})
        rows_b, eff_b, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi_blk, {}, []
        )
        self.assertEqual(eff_b['fund:TQQQ'], 'NO-NEW-RISK')
        self.assertEqual(inv.compute_permitted_exposure(vi_blk, rows_b, eff_b), 45000.0)
        self.assertEqual(inv.check_bundle_against_baseline('pos.symbol_tqqq_nnr', vi_blk, rows_b, eff_b), [])

        # Only TQQQ stale under V7 -> buying SOXL permits 50,000 cleanly
        vi_soxl = copy.deepcopy(self.normal_vi)
        vi_soxl.update({'joint_exposure': 45000.0, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, 'o5_collar': 0.05, 'symbol': 'SOXL'})
        vi_soxl['funds']['TQQQ'].update({'quote_staleness': 5.0, 'v5_tolerance': 0.01})
        vi_soxl['funds']['SOXL'].update({'v5_tolerance': 0.01})
        rows_s, eff_s, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi_soxl, {}, []
        )
        self.assertEqual(inv.compute_permitted_exposure(vi_soxl, rows_s, eff_s), 50000.0)
        self.assertEqual(inv.check_bundle_against_baseline('pos.buy_soxl_only_tqqq_v7', vi_soxl, rows_s, eff_s), [])

        # Negative joint_exposure fails closed to headroom=0.0 with zero checker false-positive
        vi_neg = copy.deepcopy(self.normal_vi)
        vi_neg['joint_exposure'] = -10.0
        rows_n, eff_n, _ = evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi_neg, {}, []
        )
        self.assertEqual(inv.check_bundle_against_baseline('pos.neg_joint_exp', vi_neg, rows_n, eff_n), [])


if __name__ == '__main__':
    unittest.main()
