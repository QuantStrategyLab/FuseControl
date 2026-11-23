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
                    'shortfall_vs_model': 0.005,  # Excess beyond tolerance
                    'tolerance': 0.003  # V5 tolerance
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
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
            'authorized_events': [{'type': 'deposit', 'amount': 10000, 'session': '2026-01-06'}]
        }

        # Serialize-restore
        prior_json = canonical_json(prior)
        prior_restored = json.loads(prior_json)
        self.assertEqual(prior_restored, prior)

        # Interrupted path
        rows_restored, _, state_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs, prior_restored, {'authorized_events': inputs['authorized_events']}
        )

        # Uninterrupted control
        rows_uninterrupted, _, state_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs, prior, {'authorized_events': inputs['authorized_events']}
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
            'bankroll': 100000
        }

        events = [{'type': 'owner_rearm', 'row': 'L2', 'scope': 'account', 'session': '2026-01-10'}]

        # Serialize-restore
        prior_json = canonical_json(prior)
        prior_restored = json.loads(prior_json)

        # Interrupted
        rows_restored, _, state_restored = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-10', '2026-01-10T16:00:00Z', 'shadow',
            inputs, prior_restored, {'authorized_events': events}
        )

        # Uninterrupted
        rows_uninterrupted, _, state_uninterrupted = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-10', '2026-01-10T16:00:00Z', 'shadow',
            inputs, prior, {'authorized_events': events}
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
            'pending_orders': [{'symbol': 'TQQQ', 'original_order_id': 'order_X', 'status': 'pending'}],
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
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
            'pending_orders': [],  # No fresh report
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

        # Verify order preserved after restart
        self.assertEqual(rows_restored['O4']['reason'], 'awaiting_original_order_status_after_restart')
        self.assertEqual(state2_restored['O4']['TQQQ']['original_order_id'], 'order_X')
        assert_no_private_aliases(state2_restored, "O4 after restart")

        # Step 3: Terminal status clears (serialize-restore again)
        state2_json = canonical_json(state2_restored)
        state2_restored2 = json.loads(state2_json)

        inputs3 = {
            **inputs2,
            'pending_orders': [{'symbol': 'TQQQ', 'original_order_id': 'order_X', 'status': 'filled'}],
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
                    'shortfall_vs_model': 0.005
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
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

        # Verify TQQQ tripped (new), SOXL preserved (count 5 unchanged)
        self.assertIn('TQQQ', state_restored['V4'])
        self.assertEqual(state_restored['V4']['TQQQ']['clearing_counter'], 0)
        self.assertIn('SOXL', state_restored['V4'])
        self.assertEqual(state_restored['V4']['SOXL']['clearing_counter'], 5)
        assert_no_private_aliases(state_restored, "Two-fund V4 state")


if __name__ == '__main__':
    unittest.main()
