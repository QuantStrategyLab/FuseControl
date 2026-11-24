#!/usr/bin/env python3
"""G1 (F1-A03): Full comparator tests — exact row dicts and independent scope maps.

Independently derives expected effective_state_by_scope for all 264 base cells
from spec/spec.json + goldens/scenarios.json + goldens/golden-table.json using
spec §4.1 scope rules (separate derivation path from evaluator.py).
Also verifies G1.2 SUC-11 evaluator call count > 0 and G1.3 comparator checks.
"""

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'tools'))

import run_matrix
from fuse_engine import evaluate
from run_matrix import PRECEDENCE, _more_restrictive, derive_expected_effective_map


class TestFullComparator(unittest.TestCase):
    """Verify per-cell row dict and independent effective-map agreement across 264 cells."""

    @classmethod
    def setUpClass(cls):
        cls.scenarios = json.loads((REPO_ROOT / 'goldens' / 'scenarios.json').read_text(encoding='utf-8'))
        cls.golden_table = json.loads((REPO_ROOT / 'goldens' / 'golden-table.json').read_text(encoding='utf-8'))
        cls.spec = json.loads((REPO_ROOT / 'spec' / 'spec.json').read_text(encoding='utf-8'))
        cls.engine_hash = run_matrix.compute_engine_hash()

    def test_all_264_cells_strict_raw_row_dict_equality(self):
        """R4: All 264 base cells match v2 golden dicts byte-for-byte without O5 field projection."""
        raw_equal = 0
        comparator_equal = 0
        raw_diffs = []

        for cell_key, cell in self.golden_table['base_cells'].items():
            sc_name = cell['scenario']
            row_id = cell['row_id']
            actual_row, _ = run_matrix.execute_cell(
                self.scenarios['scenarios'][sc_name], row_id, self.engine_hash
            )
            if actual_row == cell['outcome']:
                raw_equal += 1
            else:
                raw_diffs.append((cell_key, actual_row, cell['outcome']))

            ok, _ = run_matrix.compare_base_outcome_exact(actual_row, cell['outcome'], row_id)
            if ok:
                comparator_equal += 1

        self.assertEqual(raw_equal, 264, f"Expected 264/264 strict raw dict matches, got {raw_equal}; diffs={raw_diffs[:3]}")
        self.assertEqual(comparator_equal, 264)
        # Negative control: missing rejection_count_this_session on O5 must now be rejected
        o5_actual = {'state': 'NORMAL', 'would_have_tripped': True, 'kind': 'breaker', 'latched': False, 'reason': 'unresolved_fail_closed', 'rejection_count_this_session': 1}
        o5_missing = {k: v for k, v in o5_actual.items() if k != 'rejection_count_this_session'}
        ok_o5, _ = run_matrix.compare_base_outcome_exact(o5_actual, o5_missing, 'O5')
        self.assertFalse(ok_o5, "Strict comparator must reject missing O5.rejection_count_this_session")

    def test_240_non_tier_change_cells_both_row_and_scope_equal(self):
        """All 240 non-tier_change cells pass both row-dict equality and independent scope-map equality."""
        both_equal = 0
        for cell_key, cell in self.golden_table['base_cells'].items():
            sc_name = cell['scenario']
            if sc_name == 'tier_change':
                continue
            row_id = cell['row_id']
            actual_row, actual_eff = run_matrix.execute_cell(
                self.scenarios['scenarios'][sc_name], row_id, self.engine_hash
            )
            expected_eff = derive_expected_effective_map(
                sc_name, self.scenarios['scenarios'][sc_name], self.golden_table['base_cells'], self.spec
            )
            row_ok, _ = run_matrix.compare_base_outcome_exact(actual_row, cell['outcome'], row_id)
            self.assertTrue(row_ok, f"{cell_key} row mismatch")
            self.assertEqual(actual_eff, expected_eff, f"{cell_key} effective map mismatch")
            both_equal += 1
        self.assertEqual(both_equal, 240)

    def test_all_264_cells_both_row_and_scope_equal(self):
        """All 264 base cells match both row dict and independently derived scope map (including tier_change joint HALT)."""
        both_equal = 0
        failures = []
        for cell_key, cell in self.golden_table['base_cells'].items():
            sc_name = cell['scenario']
            row_id = cell['row_id']
            actual_row, actual_eff = run_matrix.execute_cell(
                self.scenarios['scenarios'][sc_name], row_id, self.engine_hash
            )
            expected_eff = derive_expected_effective_map(
                sc_name, self.scenarios['scenarios'][sc_name], self.golden_table['base_cells'], self.spec
            )
            row_ok, _ = run_matrix.compare_base_outcome_exact(actual_row, cell['outcome'], row_id)
            if row_ok and actual_eff == expected_eff:
                both_equal += 1
            else:
                failures.append((cell_key, actual_eff, expected_eff))
        self.assertEqual(both_equal, 264, f"Only {both_equal}/264 matched; first failure: {failures[:1]}")

    def test_suc11_executes_real_evaluator_calls(self):
        """G1.2: SUC-11 executes >0 real evaluate() calls inside run_successor_cases."""
        suc_data = json.loads((REPO_ROOT / 'goldens' / 'successor-cases.json').read_text(encoding='utf-8'))
        call_count = 0
        orig_evaluate = run_matrix.evaluate

        def counting_eval(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return orig_evaluate(*args, **kwargs)

        run_matrix.evaluate = counting_eval
        try:
            res = run_matrix.run_successor_cases({'cases': {'SUC-11': suc_data['cases']['SUC-11']}}, self.engine_hash)
        finally:
            run_matrix.evaluate = orig_evaluate

        self.assertEqual(res['passed'], 1)
        self.assertEqual(res['failed'], 0)
        self.assertGreater(call_count, 0)

    def test_successor_comparator_rejects_field_and_empty_map_mutations(self):
        """G1.3: Mutated fund/symbol/original_order_id/deviation or absent {} fails comparator."""
        base_ok = {'state': 'NORMAL', 'would_have_tripped': False, 'kind': 'breaker', 'latched': False, 'reason': 'none'}
        for field, val in [('fund', 'TQQQ'), ('symbol', 'TQQQ'), ('original_order_id', 'order_X'), ('deviation', 0.0102)]:
            ok, diffs = run_matrix.compare_outcome(base_ok, {**base_ok, field: val})
            self.assertFalse(ok, f"Expected failure when {field} missing")
            self.assertTrue(any(field in d for d in diffs))

        ok_absent, diffs_absent = run_matrix.compare_next_row_state({}, {'L2': {}})
        self.assertFalse(ok_absent, "Expected failure for absent state when {} expected")
        self.assertTrue(any('L2' in d for d in diffs_absent))

    def test_suc08_executes_all_70_continuous_sessions_without_frozen_prior_injection(self):
        """R6: SUC-08 executes all 70 sequential sessions threading live state without frozen prior skips."""
        suc_data = json.loads((REPO_ROOT / 'goldens' / 'successor-cases.json').read_text(encoding='utf-8'))
        seen_priors = []
        orig_evaluate = run_matrix.evaluate

        def spy_eval(*args, **kwargs):
            pr = kwargs.get('prior_row_state') if 'prior_row_state' in kwargs else args[7]
            seen_priors.append(pr)
            return orig_evaluate(*args, **kwargs)

        run_matrix.evaluate = spy_eval
        try:
            res = run_matrix.run_successor_cases({'cases': {'SUC-08': suc_data['cases']['SUC-08']}}, self.engine_hash)
        finally:
            run_matrix.evaluate = orig_evaluate

        self.assertEqual(res['passed'], 1)
        self.assertEqual(res['failed'], 0)
        self.assertEqual(len(seen_priors), 70)
        # Every session 2..70 must carry live V5 state including last_session (absent in frozen prior_row_state)
        for idx in range(1, 70):
            v5_prior = seen_priors[idx].get('V5', {}).get('TQQQ', {})
            self.assertEqual(v5_prior.get('consecutive_beyond_tolerance'), idx)
            self.assertIsNotNone(v5_prior.get('last_session'))

    def test_strict_value_equal_rejects_bool_int_mismatch(self):
        """R4: strict comparator rejects bool vs int (True != 1, False != 0)."""
        self.assertFalse(run_matrix.strict_value_equal(True, 1))
        self.assertFalse(run_matrix.strict_value_equal(False, 0))
        o5_exp = {
            'state': 'NORMAL', 'would_have_tripped': True, 'kind': 'breaker',
            'latched': False, 'reason': 'unresolved_fail_closed', 'rejection_count_this_session': 1,
        }
        o5_mut = {**o5_exp, 'rejection_count_this_session': True}
        ok_base, diffs_base = run_matrix.compare_base_outcome_exact(o5_mut, o5_exp, 'O5')
        self.assertFalse(ok_base)
        self.assertTrue(any('rejection_count_this_session' in d for d in diffs_base))
        ok_out, diffs_out = run_matrix.compare_outcome(o5_mut, o5_exp)
        self.assertFalse(ok_out)
        self.assertTrue(any('rejection_count_this_session' in d for d in diffs_out))

    def test_formal_run_base_cells_detects_tier_change_joint_scope_mutation(self):
        """A03: Mutating tier_change.joint -> NORMAL fails formal run_matrix.run_base_cells."""
        orig_execute = run_matrix.execute_cell

        def spoof_execute(scenario, row_id, engine_hash):
            out, eff = orig_execute(scenario, row_id, engine_hash)
            if scenario is self.scenarios['scenarios']['tier_change'] and 'joint' in eff:
                eff = dict(eff)
                eff['joint'] = 'NORMAL'
            return out, eff

        run_matrix.execute_cell = spoof_execute
        try:
            res = run_matrix.run_base_cells(self.scenarios, self.golden_table, self.engine_hash, self.spec)
        finally:
            run_matrix.execute_cell = orig_execute
        self.assertEqual(res['passed'], 240)
        self.assertEqual(res['failed'], 24)

    def test_generate_golden_table_matches_v2_golden_table(self):
        """Generator in tools/generate_golden_table.py stays synced with v2 goldens/golden-table.json."""
        import generate_golden_table as ggt
        generated = ggt.generate_golden_table(REPO_ROOT / 'goldens' / 'scenarios.json')
        self.assertEqual(generated['base_cells'], self.golden_table['base_cells'])
        self.assertEqual(generated['tier_repetitions'], self.golden_table['tier_repetitions'])
        self.assertEqual(generated, self.golden_table)


if __name__ == '__main__':
    unittest.main()
