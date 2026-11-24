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


PRECEDENCE = ['HALT', 'ORDER-UNKNOWN', 'DE-RISK', 'NO-NEW-RISK', 'NORMAL']


def _more_restrictive(a: str, b: str) -> str:
    return a if PRECEDENCE.index(a) < PRECEDENCE.index(b) else b


def derive_expected_effective_map(
    scenario_name: str,
    scenario_data: Dict[str, Any],
    base_cells: Dict[str, Any],
    spec_data: Dict[str, Any],
) -> Dict[str, str]:
    """Independently derive expected effective_state_by_scope from frozen artifacts + §4.1."""
    vi = scenario_data['inputs']['validated_inputs']
    funds = vi.get('funds', {})
    fund_symbols = list(funds.keys())
    pending_orders = vi.get('pending_orders', {})
    prior = scenario_data['inputs'].get('prior_row_state') or {}
    symbol_universe = sorted(set(fund_symbols) | set(pending_orders.keys()) | set(prior.get('O4', {}).keys()))

    expected_map: Dict[str, str] = {'account': 'NORMAL'}
    for sym in fund_symbols:
        expected_map[f'fund:{sym}'] = 'NORMAL'
    for sym in symbol_universe:
        expected_map[f'symbol:{sym}'] = 'NORMAL'
    expected_map['joint'] = 'NORMAL'

    row_scopes = {row['id']: row['scope'] for row in spec_data['rows']}

    for row_id, scope_kind in row_scopes.items():
        outcome = base_cells[f'{scenario_name}.{row_id}']['outcome']
        state = outcome['state']
        if state == 'NORMAL':
            continue

        if scope_kind == 'account' or (row_id == 'O5' and outcome.get('latched')):
            expected_map['account'] = _more_restrictive(expected_map['account'], state)
        elif scope_kind == 'fund':
            reason = outcome.get('reason', '')
            matched_fund = None
            for sym in fund_symbols:
                if reason.endswith(f'_{sym}') or outcome.get('fund') == sym:
                    matched_fund = sym
                    break
            if matched_fund is not None:
                expected_map[f'fund:{matched_fund}'] = _more_restrictive(
                    expected_map[f'fund:{matched_fund}'], state
                )
            else:
                for sym in fund_symbols:
                    expected_map[f'fund:{sym}'] = _more_restrictive(
                        expected_map[f'fund:{sym}'], state
                    )
        elif scope_kind == 'symbol':
            sym = outcome.get('symbol')
            if sym and f'symbol:{sym}' in expected_map:
                expected_map[f'symbol:{sym}'] = _more_restrictive(
                    expected_map[f'symbol:{sym}'], state
                )
        elif scope_kind == 'joint':
            expected_map['joint'] = _more_restrictive(expected_map['joint'], state)

    # Spec §4.1: Account HALT dominates every narrower scope including joint.
    if expected_map['account'] == 'HALT':
        for scope in list(expected_map.keys()):
            expected_map[scope] = 'HALT'

    return expected_map


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


if __name__ == '__main__':
    unittest.main()
