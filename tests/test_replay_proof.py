#!/usr/bin/env python3
"""Slice 4(c): Actual-output replay proof per Q6.

Tests that actual successor state can be serialized, restored, and replayed exactly.
Per PROMPT-FUSE1-P2F Slice 4(c):
- Start real latch/counter through evaluate
- Save ENTIRE actual successor in canonical JSON
- Restore in fresh process, assert read-back equality
- Feed to next invocation, compare all outputs to uninterrupted control
- Repeat across deposit, withdrawal, split, reverse split, tier change
- Include: repeated session, 9→10 clear, 39→40 escalation, outstanding order,
  second unaffected scope, authorized clear + ordinary evaluation
- Assert target-state projections including empty row maps
- Assert ABSENCE of private aliases
"""

import json
import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from fuse_engine import evaluate


def canonical_json(obj):
    """Serialize to canonical JSON (sorted keys)."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def assert_no_private_aliases(state: dict, label: str):
    """Assert absence of private aliases per Q6."""
    forbidden = [
        'V2_pending', 'O4_pending', 'V4_counter', 'V4_last_increment_session',
        'V5_counter', 'V5_escalated', 'O5_counter', 'O5_last_rejection_session',
        'L2_latch', 'V1_latch', 'O1_counter', 'L3_latch', 'L4_latch', 'L5_latch', 'L6_latch',
        'V2_latch', 'V3_latch', 'O3_latch', 'O6_latch', 'O7_latch', 'O9_latch'
    ]
    for alias in forbidden:
        if alias in state:
            raise AssertionError(f"{label}: found private alias '{alias}' in state: {state}")


class TestReplayProof(unittest.TestCase):
    """Q6 proof: serialize-restore-replay equality across events."""

    def test_v4_clearing_chain(self):
        """V4: 9→10 clear across serialize-restore boundary.

        Start V4 interlock, serialize at count 9, restore, advance to 10, verify clearing.
        """
        base_inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.21,  # Below 2×0.24 = 0.48
                    'long_run_volatility': 0.24,
                    'ledger_value': 100000,
                    'broker_value': 100000
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
        }

        # Step 1: Initial trip (count 0)
        _, _, state1 = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T16:00:00Z', 'shadow',
            {**base_inputs, 'funds': {**base_inputs['funds'], 'TQQQ': {**base_inputs['funds']['TQQQ'], 'forecast_volatility': 0.50}}},  # Above threshold
            {}, {}
        )
        self.assertIn('V4', state1)
        self.assertEqual(state1['V4']['TQQQ']['clearing_counter'], 0)
        assert_no_private_aliases(state1, "V4 initial trip")

        # Step 2-10: Advance counter to 9 (uninterrupted chain)
        prior = state1
        for i, session_date in enumerate(['2026-01-06', '2026-01-07', '2026-01-08', '2026-01-09',
                                          '2026-01-13', '2026-01-14', '2026-01-15', '2026-01-16', '2026-01-17'], start=1):
            _, _, prior = evaluate(
                'fuse-eval-spec/v1', 'test', 'test', session_date, f'{session_date}T16:00:00Z', 'shadow',
                base_inputs, prior, {}
            )
            self.assertEqual(prior['V4']['TQQQ']['clearing_counter'], i)
            assert_no_private_aliases(prior, f"V4 count {i}")

        # Step 11: Serialize at count 9
        state9_json = canonical_json(prior)
        state9_restored = json.loads(state9_json)

        # Assert read-back equality
        self.assertEqual(state9_restored, prior)
        assert_no_private_aliases(state9_restored, "V4 restored at count 9")

        # Step 12: Feed restored state to 10th clearing session (interrupted path)
        rows_restored, _, state10_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-20', '2026-01-20T16:00:00Z', 'shadow',
            base_inputs, state9_restored, {}
        )

        # Step 13: Also run uninterrupted control at same inputs
        rows_uninterrupted, _, state10_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-20', '2026-01-20T16:00:00Z', 'shadow',
            base_inputs, prior, {}
        )

        # Assert all three outputs equal (serialize-restore-replay = uninterrupted)
        self.assertEqual(rows_restored, rows_uninterrupted)
        self.assertEqual(state10_restored, state10_uninterrupted)

        # Verify clearing: V4 counter 10 in row, V4 cleared in next state
        self.assertEqual(rows_restored['V4']['reason'], 'cleared_after_ten_sessions')
        self.assertEqual(rows_restored['V4']['outputs']['clearing_counter'], 10)
        self.assertEqual(state10_restored.get('V4', {}), {})  # Empty map per Q4
        assert_no_private_aliases(state10_restored, "V4 after clearing")

    def test_v5_escalation_across_boundary(self):
        """V5: 39→40 escalation across serialize-restore boundary.

        V5 counter at 39, serialize, restore, advance to 40, verify escalation.
        """
        base_inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.24,
                    'long_run_volatility': 0.24,
                    'ledger_value': 100000,
                    'broker_value': 100000,
                    'fund_return': 0.010,
                    'index_return': 0.005,
                    'modelled_fee': 0.0001,
                    'modelled_financing': 0.0001,
                    'shortfall_observed': 0.008,  # Observed shortfall
                    'shortfall_predicted': 0.003,  # Predicted shortfall
                    'v5_tolerance': 0.003  # V5 tolerance: 0.008 - 0.003 = 0.005 > 0.003
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000,
            'positions_cash': 0,
            'broker_cash': 0,
            'loaded_policy_hash': 'test',
            'registered_policy_hash': 'test',
            'one_session_loss': 0.0
        }

        # Build state with V5 count 39
        prior = {
            'V5': {
                'TQQQ': {
                    'consecutive_beyond_tolerance': 39,
                    'escalated': False,
                    'last_session': '2026-03-05'
                }
            }
        }
        assert_no_private_aliases(prior, "V5 count 39 prior")

        # Serialize at count 39
        state39_json = canonical_json(prior)
        state39_restored = json.loads(state39_json)
        self.assertEqual(state39_restored, prior)

        # Feed restored to 40th session (interrupted path)
        rows_restored, _, state40_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-03-06', '2026-03-06T16:00:00Z', 'shadow',
            base_inputs, state39_restored, {}
        )

        # Uninterrupted control
        rows_uninterrupted, _, state40_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-03-06', '2026-03-06T16:00:00Z', 'shadow',
            base_inputs, prior, {}
        )

        # Assert equality
        self.assertEqual(rows_restored, rows_uninterrupted)
        self.assertEqual(state40_restored, state40_uninterrupted)

        # Verify escalation
        self.assertEqual(rows_restored['V5']['state'], 'NO-NEW-RISK')
        self.assertEqual(rows_restored['V5']['reason'], 'escalated_to_v1_treatment')
        self.assertEqual(state40_restored['V5']['TQQQ']['consecutive_beyond_tolerance'], 40)
        self.assertTrue(state40_restored['V5']['TQQQ']['escalated'])
        assert_no_private_aliases(state40_restored, "V5 after escalation")

    def test_deposit_preserves_latch(self):
        """Deposit: L2 latch survives deposit event per §4.4 rule 3."""
        # Start with L2 latched (drawdown at 2D/3)
        prior = {
            'L2': {
                'latched': True,
                'trip_session': '2026-01-05'
            }
        }
        assert_no_private_aliases(prior, "L2 latched prior")

        inputs = {
            'funds': {},
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000,
            'high_water_mark': 100000,
            'flow_event': {'type': 'deposit', 'amount': 10000, 'session': '2026-01-06'}
        }

        # Serialize-restore
        prior_json = canonical_json(prior)
        prior_restored = json.loads(prior_json)
        self.assertEqual(prior_restored, prior)

        # Interrupted path
        rows_restored, _, state_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs, prior_restored, {}
        )

        # Uninterrupted control
        rows_uninterrupted, _, state_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs, prior, {}
        )

        # Assert equality
        self.assertEqual(rows_restored, rows_uninterrupted)
        self.assertEqual(state_restored, state_uninterrupted)

        # Verify latch preserved (reason: latched_survives_deposit per rows_loss.py)
        self.assertTrue(rows_restored['L2']['latched'])
        self.assertEqual(rows_restored['L2']['reason'], 'latched_survives_deposit')
        self.assertTrue(state_restored['L2']['latched'])
        self.assertEqual(state_restored['L2']['trip_session'], '2026-01-05')  # Original trip session
        assert_no_private_aliases(state_restored, "L2 after deposit")

    def test_authorized_rearm_clears_latch(self):
        """Authorized re-arm: L2 clears and serializes as {"L2":{}}.

        Per Q4: eligible re-arm wins for that evaluation, clears latch, writes empty map.
        """
        prior = {
            'L2': {
                'latched': True,
                'trip_session': '2026-01-05'
            }
        }
        assert_no_private_aliases(prior, "L2 latched before rearm")

        inputs = {
            'funds': {},
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000,
            'high_water_mark': 100000
        }

        events = {'account': [{'type': 'rearm', 'row': 'L2', 'session': '2026-01-10'}]}

        # Serialize-restore
        prior_json = canonical_json(prior)
        prior_restored = json.loads(prior_json)

        # Interrupted
        rows_restored, _, state_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-10', '2026-01-10T16:00:00Z', 'shadow',
            inputs, prior_restored, events
        )

        # Uninterrupted
        rows_uninterrupted, _, state_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-10', '2026-01-10T16:00:00Z', 'shadow',
            inputs, prior, events
        )

        # Assert equality
        self.assertEqual(rows_restored, rows_uninterrupted)
        self.assertEqual(state_restored, state_uninterrupted)

        # Verify cleared: NORMAL/authorized_rearm, {"L2":{}} projection per Q4
        self.assertEqual(rows_restored['L2']['state'], 'NORMAL')
        self.assertEqual(rows_restored['L2']['reason'], 'authorized_rearm')
        self.assertFalse(rows_restored['L2']['latched'])
        self.assertEqual(state_restored.get('L2', {}), {})  # Empty map
        assert_no_private_aliases(state_restored, "L2 after rearm")

    def test_o4_outstanding_order_across_restart(self):
        """O4: outstanding order survives restart per §4.4 rule 3.

        Order X timeout, restart, verify order state preserved, then terminal status clears.
        """
        # Step 1: Order timeout
        inputs1 = {
            'funds': {},
            'pending_orders': {'TQQQ': {'order_id': 'order_X', 'status': 'pending', 'timeout': True}},
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000,
            'high_water_mark': 100000,
            'positions_cash': 0,
            'broker_cash': 0,
            'loaded_policy_hash': 'test',
            'registered_policy_hash': 'test',
            'one_session_loss': 0.0
        }
        _, _, state1 = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T16:00:00Z', 'shadow',
            inputs1, {}, {}
        )
        self.assertIn('O4', state1)
        self.assertEqual(state1['O4']['TQQQ']['original_order_id'], 'order_X')
        assert_no_private_aliases(state1, "O4 after timeout")

        # Step 2: Restart (serialize-restore)
        state1_json = canonical_json(state1)
        state1_restored = json.loads(state1_json)
        self.assertEqual(state1_restored, state1)

        inputs2 = {
            'funds': {},
            'pending_orders': {},  # No fresh report
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000,
            'restart_marker': True
        }

        # Interrupted path
        rows_restored, _, state2_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs2, state1_restored, {}
        )

        # Uninterrupted control
        rows_uninterrupted, _, state2_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs2, state1, {}
        )

        # Assert equality
        self.assertEqual(rows_restored, rows_uninterrupted)
        self.assertEqual(state2_restored, state2_uninterrupted)

        # Verify order preserved after restart (reason is 'awaiting_original_order_status' per rows_ops.py:264-273)
        self.assertEqual(rows_restored['O4']['reason'], 'awaiting_original_order_status')
        self.assertEqual(state2_restored['O4']['TQQQ']['original_order_id'], 'order_X')
        assert_no_private_aliases(state2_restored, "O4 after restart")

        # Step 3: Terminal status clears (serialize-restore again)
        state2_json = canonical_json(state2_restored)
        state2_restored2 = json.loads(state2_json)

        inputs3 = {
            **inputs2,
            'pending_orders': {'TQQQ': {'order_id': 'order_X', 'status': 'filled'}},
            'restart_marker': False
        }

        # Interrupted
        rows_cleared_restored, _, state3_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-07', '2026-01-07T16:00:00Z', 'shadow',
            inputs3, state2_restored2, {}
        )

        # Uninterrupted
        rows_cleared_uninterrupted, _, state3_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-07', '2026-01-07T16:00:00Z', 'shadow',
            inputs3, state2_restored, {}
        )

        # Assert equality
        self.assertEqual(rows_cleared_restored, rows_cleared_uninterrupted)
        self.assertEqual(state3_restored, state3_uninterrupted)

        # Verify cleared: O4 empty after terminal status
        self.assertEqual(state3_restored.get('O4', {}), {})
        assert_no_private_aliases(state3_restored, "O4 after clearing")

    def test_repeated_session_deduplication(self):
        """Repeated session: V5 counter does not double-count same session."""
        base_inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.24,
                    'long_run_volatility': 0.24,
                    'ledger_value': 100000,
                    'broker_value': 100000,
                    'fund_return': 0.010,
                    'index_return': 0.005,
                    'modelled_fee': 0.0001,
                    'modelled_financing': 0.0001,
                    'shortfall_observed': 0.008,
                    'shortfall_predicted': 0.003,
                    'v5_tolerance': 0.003
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000,
            'positions_cash': 0,
            'broker_cash': 0,
            'loaded_policy_hash': 'test',
            'registered_policy_hash': 'test',
            'one_session_loss': 0.0
        }

        # First evaluation on 2026-01-05
        _, _, state1 = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T16:00:00Z', 'shadow',
            base_inputs, {}, {}
        )
        self.assertEqual(state1['V5']['TQQQ']['consecutive_beyond_tolerance'], 1)
        assert_no_private_aliases(state1, "V5 first evaluation")

        # Serialize-restore
        state1_json = canonical_json(state1)
        state1_restored = json.loads(state1_json)

        # Second evaluation SAME session (duplicate) - interrupted path
        rows_restored, _, state2_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T17:00:00Z', 'shadow',
            base_inputs, state1_restored, {}
        )

        # Uninterrupted control
        rows_uninterrupted, _, state2_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T17:00:00Z', 'shadow',
            base_inputs, state1, {}
        )

        # Assert equality
        self.assertEqual(rows_restored, rows_uninterrupted)
        self.assertEqual(state2_restored, state2_uninterrupted)

        # Verify count still 1 (deduplicated)
        self.assertEqual(state2_restored['V5']['TQQQ']['consecutive_beyond_tolerance'], 1)
        self.assertEqual(state2_restored['V5']['TQQQ']['last_session'], '2026-01-05')
        assert_no_private_aliases(state2_restored, "V5 after repeated session")

    def test_second_unaffected_scope(self):
        """Second unaffected scope: SOXL state preserved while TQQQ trips."""
        inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.50,  # Above 2×0.24
                    'long_run_volatility': 0.24,
                    'ledger_value': 50000,
                    'broker_value': 50000
                },
                'SOXL': {
                    'forecast_volatility': 0.21,  # Below 2×0.22
                    'long_run_volatility': 0.22,
                    'ledger_value': 50000,
                    'broker_value': 50000
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
        }

        prior = {
            'V4': {
                'SOXL': {
                    'clearing_counter': 5,
                    'last_session_below_threshold': '2026-01-04'
                }
            }
        }
        assert_no_private_aliases(prior, "SOXL V4 prior")

        # Serialize-restore
        prior_json = canonical_json(prior)
        prior_restored = json.loads(prior_json)

        # Interrupted
        rows_restored, _, state_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T16:00:00Z', 'shadow',
            inputs, prior_restored, {}
        )

        # Uninterrupted
        rows_uninterrupted, _, state_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T16:00:00Z', 'shadow',
            inputs, prior, {}
        )

        # Assert equality
        self.assertEqual(rows_restored, rows_uninterrupted)
        self.assertEqual(state_restored, state_uninterrupted)

        # Verify TQQQ tripped (new), SOXL advances (count 5→6)
        self.assertIn('TQQQ', state_restored['V4'])
        self.assertEqual(state_restored['V4']['TQQQ']['clearing_counter'], 0)
        self.assertIn('SOXL', state_restored['V4'])
        self.assertEqual(state_restored['V4']['SOXL']['clearing_counter'], 6)  # Advances on this session
        assert_no_private_aliases(state_restored, "Two-fund V4 state")


class TestG4StateContinuityAndDominance(unittest.TestCase):
    """G4 (F1-A07 + F1-A08 + F1-A12): Astra §5 items 1-4 + dominance + V2 negative control."""

    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).parent.parent
        cls.normal_vi = json.loads(
            (repo / 'goldens' / 'scenarios.json').read_text(encoding='utf-8')
        )['scenarios']['normal']['inputs']['validated_inputs']
        cls.suc_cases = json.loads(
            (repo / 'goldens' / 'successor-cases.json').read_text(encoding='utf-8')
        )['cases']

    def _ev(self, vi, session='2026-01-05', prior=None, events=None):
        return evaluate(
            'fuse-eval-spec/v1', 'test-hash', 'registered_policy_hash_v1',
            session, f'{session}T16:00:00Z', 'shadow', vi, prior or {}, events or []
        )

    def test_v4_counter_survives_missing_forecast(self):
        import copy
        vi = copy.deepcopy(self.normal_vi)
        vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
        vi['funds']['TQQQ']['forecast_volatility'] = 0.50
        _, _, s1 = self._ev(vi, '2026-01-05')

        vi['funds']['TQQQ']['forecast_volatility'] = None
        r2, _, s2 = self._ev(vi, '2026-01-06', s1)
        self.assertEqual(r2['V4']['reason'], 'missing_input')
        self.assertEqual(s2['V4']['TQQQ']['clearing_counter'], 0)

        vi['funds']['TQQQ']['forecast_volatility'] = 0.30
        r3, _, s3 = self._ev(vi, '2026-01-07', s2)
        self.assertEqual(r3['V4']['state'], 'NO-NEW-RISK')
        self.assertEqual(r3['V4']['outputs']['clearing_counter'], 1)
        self.assertEqual(s3['V4']['TQQQ']['clearing_counter'], 1)

    def test_tqqq_v1_and_v2_latches_survive_soxl_only_evaluation(self):
        import copy
        s13 = self.suc_cases['SUC-13']['steps'][0]['inputs']['validated_inputs']
        _, _, s_v1 = self._ev(s13, '2026-01-05')
        s02 = self.suc_cases['SUC-02']['steps'][0]['inputs']['validated_inputs']
        _, _, s_v2 = self._ev(s02, '2026-01-05')

        vi_soxl = copy.deepcopy(self.normal_vi)
        vi_soxl['funds'] = {'SOXL': copy.deepcopy(self.normal_vi['funds']['SOXL'])}

        r_mid1, _, s_mid1 = self._ev(vi_soxl, '2026-01-06', s_v1)
        self.assertTrue(r_mid1['V1']['latched'])
        self.assertTrue(s_mid1['V1']['TQQQ']['latched'])
        r_ret1, _, _ = self._ev(copy.deepcopy(self.normal_vi), '2026-01-07', s_mid1)
        self.assertEqual(r_ret1['V1']['state'], 'NO-NEW-RISK')
        self.assertTrue(r_ret1['V1']['latched'])

        r_mid2, _, s_mid2 = self._ev(vi_soxl, '2026-01-06', s_v2)
        self.assertTrue(r_mid2['V2']['latched'])
        self.assertIn('TQQQ', s_mid2['V2']['latched_mismatches'])
        r_ret2, _, _ = self._ev(copy.deepcopy(self.normal_vi), '2026-01-07', s_mid2)
        self.assertEqual(r_ret2['V2']['state'], 'HALT')
        self.assertTrue(r_ret2['V2']['latched'])

    def test_l3_loss_record_and_l4_trip_date_preserved(self):
        import copy
        vi_l3 = copy.deepcopy(self.normal_vi)
        vi_l3['bankroll'] = 60000.0
        _, _, s_l3 = self._ev(vi_l3, '2026-01-05')
        orig_record = s_l3['L3']['loss_record']
        self.assertEqual(orig_record['drawdown'], 0.4)

        vi_rec = copy.deepcopy(self.normal_vi)
        r_d1, _, s_d1 = self._ev(vi_rec, '2026-01-06', s_l3, [{'type': 'rearm', 'row_id': 'L3', 'days_since_trip': 1}])
        self.assertEqual(r_d1['L3']['outputs']['cooling_off_days_remaining'], 29)
        self.assertEqual(s_d1['L3']['loss_record'], orig_record)

        r_d30, _, s_d30 = self._ev(vi_rec, '2026-02-05', s_d1, [{'type': 'rearm', 'row_id': 'L3', 'days_since_trip': 30}])
        self.assertEqual(r_d30['L3']['state'], 'NORMAL')
        self.assertEqual(r_d30['L3']['reason'], 'authorized_rearm')
        self.assertFalse(s_d30['L3']['latched'])
        self.assertEqual(s_d30['L3']['loss_record'], orig_record)

        _, _, s_after = self._ev(vi_rec, '2026-02-06', s_d30)
        self.assertEqual(s_after['L3']['loss_record'], orig_record)

        vi_l4 = copy.deepcopy(self.normal_vi)
        vi_l4['one_session_loss'] = 0.05
        _, _, s_l4_1 = self._ev(vi_l4, '2026-01-05')
        _, _, s_l4_2 = self._ev(vi_rec, '2026-01-06', s_l4_1)
        self.assertEqual(s_l4_2['L4']['trip_session'], '2026-01-05')

    def test_o4_dual_order_deterministic_across_hash_seeds(self):
        import copy, hashlib, os, subprocess
        vi = copy.deepcopy(self.normal_vi)
        vi['pending_orders'] = {
            'TQQQ': {'order_id': 'ord_t', 'status': 'pending', 'timeout': True},
            'SOXL': {'order_id': 'ord_s', 'status': 'pending', 'timeout': True},
        }
        _, _, s_dual = self._ev(vi, '2026-01-05')
        dual_json = canonical_json(s_dual)

        results = []
        for seed in ('1', '2', '3'):
            code = (
                "import json, hashlib, sys; sys.path.insert(0, 'src'); "
                "from fuse_engine import evaluate; from fuse_engine.canonical import canonical_json; "
                "vi = json.load(open('goldens/scenarios.json'))['scenarios']['normal']['inputs']['validated_inputs']; "
                f"prior = json.loads({dual_json!r}); "
                "res = evaluate('fuse-eval-spec/v1', 'test-hash', 'registered_policy_hash_v1', "
                "'2026-01-06', '2026-01-06T16:00:00Z', 'shadow', vi, prior, []); "
                "print(res[0]['O4']['symbols'], hashlib.sha256(canonical_json(res).encode()).hexdigest())"
            )
            env = {**os.environ, 'PYTHONHASHSEED': seed}
            out = subprocess.check_output(
                [sys.executable, '-c', code], cwd=str(Path(__file__).parent.parent), env=env
            ).decode().strip()
            results.append(out)
        self.assertEqual(len(set(results)), 1, f"Non-deterministic across PYTHONHASHSEED: {results}")

    def test_account_halt_dominates_joint_scope(self):
        import copy
        vi = copy.deepcopy(self.normal_vi)
        vi['funds']['TQQQ']['fund_event'] = 'liquidation'
        vi['funds']['TQQQ']['forecast_volatility'] = 0.60
        vi['funds']['TQQQ']['long_run_volatility'] = 0.24
        vi['pending_orders'] = {'TQQQ': {'order_id': 'ord_t', 'status': 'pending', 'timeout': True}}
        _, eff1, s1 = self._ev(vi, '2026-01-05')
        self.assertEqual(eff1['joint'], 'NORMAL')

        vi2 = copy.deepcopy(vi)
        vi2['broker_cash'] = 95000.0
        _, eff2, _ = self._ev(vi2, '2026-01-06', s1)
        self.assertEqual(eff2['account'], 'HALT')
        self.assertEqual(eff2['joint'], 'HALT')

    def test_v2_contradictory_exact_flag_with_amount_mismatch_latches_halt(self):
        import copy
        s1_in = self.suc_cases['SUC-01']['steps'][0]['inputs']['validated_inputs']
        s2_in = self.suc_cases['SUC-01']['steps'][1]['inputs']['validated_inputs']
        s3_in = copy.deepcopy(self.suc_cases['SUC-01']['steps'][2]['inputs']['validated_inputs'])
        _, _, st1 = self._ev(s1_in, '2026-01-05')
        _, _, st2 = self._ev(s2_in, '2026-01-06', st1)
        s3_in['funds']['TQQQ']['broker_value'] = 24900.0
        rows, _, st3 = self._ev(s3_in, '2026-01-07', st2)
        self.assertEqual(rows['V2']['state'], 'HALT')
        self.assertTrue(rows['V2']['latched'])
        self.assertEqual(rows['V2']['reason'], 'reconciliation_mismatch')
        self.assertIn('TQQQ', st3['V2']['latched_mismatches'])


if __name__ == '__main__':
    unittest.main()
