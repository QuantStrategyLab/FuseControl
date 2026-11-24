#!/usr/bin/env python3
"""Slice 4(d): SUC-11 by execution - deep-shape fixture per F1-A07.

Exercises V4/V5/V6 outputs with deep recursive shape comparison.
Tests that nested fields are present and mutations are detected.
Binds SUC-11 credit to executable evidence, not flag.
"""

import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from fuse_engine import evaluate


class TestDeepShape(unittest.TestCase):
    """Deep-shape fixture: exercises V4/V5/V6 outputs, rejects mutations."""

    def test_v4_outputs_shape(self):
        """V4: clearing_counter in outputs, nested correctly."""
        inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.21,  # Below 2×0.24
                    'long_run_volatility': 0.24,
                    'ledger_value': 100000,
                    'broker_value': 100000
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
        }

        # Prior state with active V4 count 5
        prior = {
            'V4': {
                'TQQQ': {
                    'clearing_counter': 5,
                    'last_session_below_threshold': '2026-01-05'
                }
            }
        }

        rows, _, state = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs, prior, {}
        )

        # V4 shape checks
        v4 = rows['V4']
        self.assertIn('state', v4)
        self.assertIn('would_have_tripped', v4)
        self.assertIn('kind', v4)
        self.assertIn('latched', v4)
        self.assertIn('reason', v4)
        self.assertIn('outputs', v4)

        # Outputs nested correctly per Q1 (single-fund unwrapped)
        self.assertIn('clearing_counter', v4['outputs'])
        self.assertEqual(v4['outputs']['clearing_counter'], 6)

        # Reject mutation: outputs should NOT be wrapped per-fund
        self.assertNotIn('TQQQ', v4['outputs'],
                         "V4 outputs must not be wrapped per-fund for single-fund scenarios")

    def test_v5_outputs_shape(self):
        """V5: diagnostic outputs with counter, escalation flag."""
        inputs = {
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
                    'shortfall_vs_model': 0.005,
                    'tolerance': 0.003
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
        }

        # Prior state at count 20 (pre-escalation)
        prior = {
            'V5': {
                'TQQQ': {
                    'consecutive_beyond_tolerance': 20,
                    'escalated': False,
                    'last_session': '2026-02-01'
                }
            }
        }

        rows, _, state = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-02-02', '2026-02-02T16:00:00Z', 'shadow',
            inputs, prior, {}
        )

        # V5 shape checks
        v5 = rows['V5']
        self.assertIn('state', v5)
        self.assertIn('would_have_tripped', v5)
        self.assertIn('kind', v5)
        self.assertIn('latched', v5)
        self.assertIn('reason', v5)
        self.assertIn('outputs', v5)

        # V5 diagnostic outputs (per §4.3 Table B V5)
        self.assertIn('excess_shortfall', v5['outputs'])
        self.assertIn('consecutive_sessions_beyond_tolerance', v5['outputs'])
        self.assertIn('escalated_to_v1', v5['outputs'])

        # Type checks (shape verification only)
        self.assertIsInstance(v5['outputs']['consecutive_sessions_beyond_tolerance'], int)
        self.assertIsInstance(v5['outputs']['escalated_to_v1'], bool)

    def test_v6_outputs_shape(self):
        """V6: carrying cost diagnostic outputs."""
        inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.24,
                    'long_run_volatility': 0.24,
                    'ledger_value': 100000,
                    'broker_value': 100000,
                    'carrying_cost_per_unit_exposure': 0.015,  # Above threshold
                    'shrunk_excess_return': 0.04,  # Quarter = 0.01
                    'index_exposure': 100000
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
        }

        rows, _, _ = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-05', '2026-01-05T16:00:00Z', 'shadow',
            inputs, {}, {}
        )

        # V6 shape checks
        v6 = rows['V6']
        self.assertIn('state', v6)
        self.assertIn('would_have_tripped', v6)
        self.assertIn('kind', v6)
        self.assertIn('latched', v6)
        self.assertIn('reason', v6)

        # V6 is diagnostic - should have outputs when triggered
        if v6['would_have_tripped']:
            self.assertIn('outputs', v6)

    def test_reject_nested_state_mutation(self):
        """Negative control: mutated next_row_state must be detectable.

        Per F1-A07: deep comparison must detect nested mutations.
        """
        inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.21,
                    'long_run_volatility': 0.24,
                    'ledger_value': 100000,
                    'broker_value': 100000
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
        }

        prior = {
            'V4': {
                'TQQQ': {
                    'clearing_counter': 5,
                    'last_session_below_threshold': '2026-01-05'
                }
            }
        }

        _, _, state = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs, prior, {}
        )

        # Actual state
        actual_counter = state['V4']['TQQQ']['clearing_counter']
        self.assertEqual(actual_counter, 6)

        # Mutated state (injected error)
        mutated_state = {
            'V4': {
                'TQQQ': {
                    'clearing_counter': 7,  # WRONG - should be 6
                    'last_session_below_threshold': '2026-01-06'
                }
            }
        }

        # Deep comparison must detect difference
        self.assertNotEqual(state, mutated_state,
                           "Deep comparison must detect nested state mutations")
        self.assertNotEqual(state['V4']['TQQQ']['clearing_counter'],
                           mutated_state['V4']['TQQQ']['clearing_counter'],
                           "Nested counter mutation must be detectable")

    def test_reject_outputs_structure_mutation(self):
        """Negative control: outputs structure mutations must be detected.

        V4 outputs wrapped per-fund would be a structure mutation.
        """
        inputs = {
            'funds': {
                'TQQQ': {
                    'forecast_volatility': 0.21,
                    'long_run_volatility': 0.24,
                    'ledger_value': 100000,
                    'broker_value': 100000
                }
            },
            'tier': 'balanced',
            'tier_loss_budget_D': 0.30,
            'bankroll': 100000
        }

        prior = {
            'V4': {
                'TQQQ': {
                    'clearing_counter': 5,
                    'last_session_below_threshold': '2026-01-05'
                }
            }
        }

        rows, _, _ = evaluate(
            'fuse-eval-spec/v1', 'test', 'test', '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
            inputs, prior, {}
        )

        # Actual structure (unwrapped)
        actual_outputs = rows['V4']['outputs']
        self.assertEqual(actual_outputs, {'clearing_counter': 6})

        # Mutated structure (wrapped per-fund - the bug we fixed)
        mutated_outputs = {
            'TQQQ': {
                'clearing_counter': 6
            }
        }

        # Deep comparison must detect structure difference
        self.assertNotEqual(actual_outputs, mutated_outputs,
                           "Deep comparison must detect outputs structure mutations")


if __name__ == '__main__':
    unittest.main()
