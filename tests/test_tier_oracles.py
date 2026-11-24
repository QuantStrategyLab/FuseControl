#!/usr/bin/env python3
"""G2 (F1-A04): Discriminating tier oracle verification.

Tests tier-parameterized rows (L0-L4, J1) across all 11 scenarios using the
documented tier caps from goldens/DERIVATION.md (conservative 0.4 * bankroll = 40,000,
balanced 0.6 * bankroll = 60,000, aggressive 0.8 * bankroll = 80,000 on 100k baseline),
covers balanced+aggressive for tier_change (whose frozen base is conservative),
honours frozen restart/tier_change priors, and verifies -1 J1-cap mutation detection.
"""

import copy
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


TIER_D = {'conservative': 0.15, 'balanced': 0.30, 'aggressive': 0.50}
TIER_CAP_RATIO = {'conservative': 0.40, 'balanced': 0.60, 'aggressive': 0.80}
TIER_ROWS = ['L0', 'L1', 'L2', 'L3', 'L4', 'J1']


def derive_discriminating_tier_outcome(row_id: str, vi: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Independently derive expected outcome for tier-parameterized row per spec §4.3 & DERIVATION.md."""
    D = TIER_D[tier]
    bankroll = vi['bankroll']
    hwm = vi['high_water_mark']
    drawdown = (hwm - bankroll) / hwm if hwm > 0 else 0.0
    cap = round(bankroll * TIER_CAP_RATIO[tier], 2)
    joint_exp = vi['joint_exposure']
    proposed = vi['proposed_exposure']
    tier_change_event = vi.get('tier_change_event')

    if row_id == 'L0':
        cap_breached = joint_exp > cap
        increases_blocked = proposed > cap
        tripped = False if tier_change_event else (cap_breached or increases_blocked)
        return {
            'state': 'NORMAL',
            'would_have_tripped': tripped,
            'kind': 'limit',
            'latched': False,
            'reason': 'breached' if tripped else 'none',
            'outputs': {
                'cap': cap,
                'cap_breached': cap_breached,
                'increases_blocked': increases_blocked,
            },
        }
    if row_id == 'L1':
        tripped = drawdown >= D / 3.0
        return {
            'state': 'NORMAL',
            'would_have_tripped': tripped,
            'kind': 'interlock',
            'latched': False,
            'reason': 'drawdown_threshold' if tripped else 'none',
            'outputs': {'locked_against_loosening': tripped, 'notify': tripped},
        }
    if row_id == 'L2':
        tripped = drawdown >= 2.0 * D / 3.0
        return {
            'state': 'NO-NEW-RISK' if tripped else 'NORMAL',
            'would_have_tripped': tripped,
            'kind': 'breaker',
            'latched': tripped,
            'reason': 'drawdown_at_2D_over_3' if tripped else 'none',
        }
    if row_id == 'L3':
        tripped = drawdown >= D
        return {
            'state': 'DE-RISK' if tripped else 'NORMAL',
            'would_have_tripped': tripped,
            'kind': 'breaker',
            'latched': tripped,
            'reason': 'drawdown_threshold' if tripped else 'none',
            'outputs': {
                'cooling_off_days_remaining': 30 if tripped else 0,
                'locked_flat': tripped,
                'loss_record_cleared': False,
            },
        }
    if row_id == 'L4':
        tripped = vi['one_session_loss'] >= D / 10.0
        return {
            'state': 'NO-NEW-RISK' if tripped else 'NORMAL',
            'would_have_tripped': tripped,
            'kind': 'breaker',
            'latched': tripped,
            'reason': 'one_session_loss_threshold' if tripped else 'none',
        }
    if row_id == 'J1':
        headroom = cap - joint_exp
        above_cap = joint_exp > cap
        above_trim = joint_exp > cap * 1.10
        if tier_change_event and (above_cap or above_trim):
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'limit',
                'latched': False,
                'reason': 'none',
                'outputs': {
                    'headroom': max(0, headroom),
                    'cap': cap,
                    'above_cap': above_cap,
                    'above_trim_threshold': above_trim,
                },
            }
        return {
            'state': 'NORMAL',
            'would_have_tripped': above_cap or above_trim,
            'kind': 'limit',
            'latched': False,
            'reason': 'joint_cap_exceeded' if above_cap else 'none',
            'outputs': {
                'headroom': headroom,
                'cap': cap,
                'above_cap': above_cap,
                'above_trim_threshold': above_trim,
            },
        }
    raise ValueError(f"Unsupported tier row {row_id}")


class TestTierOracles(unittest.TestCase):
    """Verify discriminating tier oracles and mutation sensitivity per G2 (F1-A04)."""

    @classmethod
    def setUpClass(cls):
        cls.scenarios = json.loads((REPO_ROOT / 'goldens' / 'scenarios.json').read_text(encoding='utf-8'))
        cls.golden_table = json.loads((REPO_ROOT / 'goldens' / 'golden-table.json').read_text(encoding='utf-8'))
        cls.engine_hash = run_matrix.compute_engine_hash()

    def _run_discriminating_132(self, j1_cap_delta: float = 0.0):
        passed = 0
        failed = 0
        discriminating_vs_base = 0
        for sc_name, sc in self.scenarios['scenarios'].items():
            sinp = sc['inputs']
            base_tier = sinp['validated_inputs']['tier']
            alt_tiers = [t for t in ('conservative', 'balanced', 'aggressive') if t != base_tier]
            self.assertEqual(len(alt_tiers), 2)

            for tier in alt_tiers:
                vi = copy.deepcopy(sinp['validated_inputs'])
                vi['tier'] = tier
                vi['tier_loss_budget_D'] = TIER_D[tier]
                cap = round(vi['bankroll'] * TIER_CAP_RATIO[tier], 2)
                vi['max_loss_cap'] = cap
                vi['tier_joint_cap'] = cap

                rows, _, _ = evaluate(
                    spec_version=sinp['spec_version'],
                    engine_hash=self.engine_hash,
                    policy_hash=sinp['policy_hash'],
                    session=sinp['session'],
                    as_of=sinp['as_of'],
                    mode=sinp['mode'],
                    validated_inputs=vi,
                    prior_row_state=copy.deepcopy(sinp.get('prior_row_state') or {}),
                    authorized_events=copy.deepcopy(sinp.get('authorized_events') or []),
                )
                for row_id in TIER_ROWS:
                    actual = copy.deepcopy(rows[row_id])
                    if row_id == 'J1' and j1_cap_delta != 0.0:
                        actual['outputs']['cap'] += j1_cap_delta
                    expected = derive_discriminating_tier_outcome(row_id, vi, tier)
                    if actual == expected:
                        passed += 1
                    else:
                        failed += 1
                    base_expected = self.golden_table['base_cells'][f'{sc_name}.{row_id}']['outcome']
                    if expected != base_expected:
                        discriminating_vs_base += 1
        return passed, failed, discriminating_vs_base

    def test_discriminating_tier_oracles_132_pass(self):
        """All 132 discriminating tier cells pass and 44/132 differ from base oracle."""
        passed, failed, discriminating = self._run_discriminating_132()
        self.assertEqual(passed, 132)
        self.assertEqual(failed, 0)
        self.assertEqual(discriminating, 44)

    def test_normal_j1_conservative_and_aggressive_discriminate(self):
        """Normal J1 returns headroom=-5000/trip=True at 40k and headroom=35000/trip=False at 80k."""
        sinp = self.scenarios['scenarios']['normal']['inputs']
        for tier, cap, exp_headroom, exp_trip in [
            ('conservative', 40000.0, -5000.0, True),
            ('aggressive', 80000.0, 35000.0, False),
        ]:
            vi = copy.deepcopy(sinp['validated_inputs'])
            vi['tier'] = tier
            vi['tier_loss_budget_D'] = TIER_D[tier]
            vi['max_loss_cap'] = cap
            vi['tier_joint_cap'] = cap
            rows, _, _ = evaluate(
                sinp['spec_version'], self.engine_hash, sinp['policy_hash'],
                sinp['session'], sinp['as_of'], sinp['mode'], vi, {}, []
            )
            j1 = rows['J1']
            self.assertEqual(j1['outputs']['cap'], cap)
            self.assertEqual(j1['outputs']['headroom'], exp_headroom)
            self.assertEqual(j1['would_have_tripped'], exp_trip)

    def test_j1_cap_minus_one_mutation_detected(self):
        """Mutating returned J1 cap by -1 fails all 22 J1 cells (110 pass / 22 fail)."""
        passed, failed, _ = self._run_discriminating_132(j1_cap_delta=-1.0)
        self.assertEqual(passed, 110)
        self.assertEqual(failed, 22)

    def test_frozen_tier_goldens_match_discriminating_caps_and_tier_change_balanced(self):
        """R5: v2 tier_repetitions (132/132) match 40k/60k/80k caps, cover balanced tier_change, and detect -1 cap mutation."""
        disagreements = 0
        tc_tiers = set()
        for _, cell in self.golden_table['tier_repetitions'].items():
            if cell['scenario'] == 'tier_change':
                tc_tiers.add(cell['tier'])
            sinp = self.scenarios['scenarios'][cell['scenario']]['inputs']
            tier = cell['tier']
            vi = copy.deepcopy(sinp['validated_inputs'])
            vi['tier'] = tier
            vi['tier_loss_budget_D'] = TIER_D[tier]
            cap = round(vi['bankroll'] * TIER_CAP_RATIO[tier], 2)
            vi['max_loss_cap'] = cap
            vi['tier_joint_cap'] = cap
            rows, _, _ = evaluate(
                sinp['spec_version'], self.engine_hash, sinp['policy_hash'],
                sinp['session'], sinp['as_of'], sinp['mode'],
                vi, copy.deepcopy(sinp.get('prior_row_state') or {}), copy.deepcopy(sinp.get('authorized_events') or [])
            )
            if rows[cell['row_id']] != cell['outcome']:
                disagreements += 1
        self.assertEqual(disagreements, 0)
        self.assertEqual(tc_tiers, {'balanced', 'aggressive'})

        # Verify formal run_matrix.run_tier_repetitions detects -1 J1 cap mutation (110 pass / 22 fail)
        orig_eval = run_matrix.evaluate

        def mutated_j1_eval(*args, **kwargs):
            rows, eff, st = orig_eval(*args, **kwargs)
            rows_mut = copy.deepcopy(rows)
            rows_mut['J1']['outputs']['cap'] -= 1.0
            return rows_mut, eff, st

        run_matrix.evaluate = mutated_j1_eval
        try:
            mut_res = run_matrix.run_tier_repetitions(self.scenarios, self.golden_table, self.engine_hash)
        finally:
            run_matrix.evaluate = orig_eval
        self.assertEqual(mut_res['passed'], 110)
        self.assertEqual(mut_res['failed'], 22)

    def test_run_tier_repetitions_honours_frozen_priors(self):
        """run_matrix.run_tier_repetitions passes non-empty frozen restart & tier_change priors."""
        seen_priors = {}
        orig_eval = run_matrix.evaluate

        def spy_eval(*args, **kwargs):
            vi = kwargs.get('validated_inputs')
            pr = kwargs.get('prior_row_state')
            if vi and vi.get('tier_change_event'):
                seen_priors['tier_change'] = pr
            if vi and vi.get('restart_marker'):
                seen_priors['restart'] = pr
            return orig_eval(*args, **kwargs)

        run_matrix.evaluate = spy_eval
        try:
            res = run_matrix.run_tier_repetitions(self.scenarios, self.golden_table, self.engine_hash)
        finally:
            run_matrix.evaluate = orig_eval

        self.assertEqual(res['passed'], 132)
        self.assertEqual(res['failed'], 0)
        self.assertEqual(seen_priors.get('tier_change'), {'prior_tier': 'balanced'})
        self.assertEqual(
            seen_priors.get('restart'),
            {'serialization_round_trip': True, 'restored_from': '2026-01-13T16:00:00Z'}
        )

    def test_loss_thresholds_discriminate_across_all_three_tiers(self):
        """12% drawdown trips L2 only on conservative; 2% 1d loss trips L4 only on conservative."""
        sinp = self.scenarios['scenarios']['normal']['inputs']
        for tier, bankroll, loss_1d, exp_l2, exp_l4 in [
            ('conservative', 88000.0, 0.02, 'NO-NEW-RISK', 'NO-NEW-RISK'),
            ('balanced', 88000.0, 0.02, 'NORMAL', 'NORMAL'),
            ('aggressive', 88000.0, 0.02, 'NORMAL', 'NORMAL'),
        ]:
            vi = copy.deepcopy(sinp['validated_inputs'])
            vi['tier'] = tier
            vi['tier_loss_budget_D'] = TIER_D[tier]
            vi['bankroll'] = bankroll
            vi['one_session_loss'] = loss_1d
            rows, _, _ = evaluate(
                sinp['spec_version'], self.engine_hash, sinp['policy_hash'],
                sinp['session'], sinp['as_of'], sinp['mode'], vi, {}, []
            )
            self.assertEqual(rows['L2']['state'], exp_l2)
            self.assertEqual(rows['L4']['state'], exp_l4)


if __name__ == '__main__':
    unittest.main()
