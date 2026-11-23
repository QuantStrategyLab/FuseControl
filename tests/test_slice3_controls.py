"""Slice 3 verification controls.

Per PROMPT-FUSE1-P2F.md Slice 3:
- Complete-input D4 control (unmasked O4 symbol transition)
- Tier_change dominance control
- Fail-closed negative controls (V4/O3/O6/O1)

Each control must FAIL on pre-fix behavior and PASS on current engine.
Controls prove by execution that the engine can detect the defects they guard.
"""

import unittest
from pathlib import Path
import sys

# Add parent directories to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from src.fuse_engine import evaluator as engine


class TestCompleteInputD4Control(unittest.TestCase):
    """D4 control: O4 symbol transition with complete account inputs.

    Exercise UNMASKED O4 symbol transition with complete, reconciled
    synthetic account inputs, matching hash pair and clean account latches.
    Demonstrate:
    1. Symbol alone enters ORDER-UNKNOWN and clears on terminal report
    2. Account HALT dominates the same symbol in mixed case
    3. Exercise WITHOUT matching fund holding to prevent masking

    Per REVIEW-REPORT Q5 and "Further defects" A.
    """

    def test_o4_symbol_alone_enters_order_unknown(self):
        """O4: symbol enters ORDER-UNKNOWN on timeout, clears on terminal status."""
        # Step 1: Order timeout with complete account inputs
        inputs_timeout = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {},  # No matching fund holding - prevents masking
                'pending_orders': {
                    'TQQQ': {
                        'order_id': 'order_test_001',
                        'symbol': 'TQQQ',
                        'status': 'pending',
                        'timeout': True  # Timeout detected
                    }
                },
                # Complete account inputs - O3/O6 clean
                'positions_cash': 100000.0,
                'broker_cash': 100000.0,
                'loaded_policy_hash': 'abc123',
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows1, scopes1, next1 = engine.evaluate(**inputs_timeout)

        # Verify O4 enters ORDER-UNKNOWN
        self.assertEqual(rows1['O4']['state'], 'ORDER-UNKNOWN',
                        "O4 must enter ORDER-UNKNOWN on timeout")
        self.assertTrue(rows1['O4']['would_have_tripped'],
                       "O4 must trip on timeout")
        self.assertEqual(rows1['O4']['reason'], 'order_timeout',
                        "O4 reason must be order_timeout")

        # Verify symbol scope is ORDER-UNKNOWN
        self.assertEqual(scopes1.get('symbol:TQQQ'), 'ORDER-UNKNOWN',
                        "symbol:TQQQ scope must be ORDER-UNKNOWN")

        # Verify O4 state persisted
        self.assertIn('O4', next1)
        self.assertIn('TQQQ', next1['O4'])
        self.assertEqual(next1['O4']['TQQQ']['original_order_id'], 'order_test_001')
        self.assertEqual(next1['O4']['TQQQ']['status'], 'unknown')

        # Step 2: Terminal status for SAME original order clears O4
        inputs_terminal = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:30:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {},
                'pending_orders': {
                    'TQQQ': {
                        'order_id': 'order_test_001',  # Same order
                        'symbol': 'TQQQ',
                        'status': 'filled',  # Terminal status
                        'timeout': False
                    }
                },
                'positions_cash': 100000.0,
                'broker_cash': 100000.0,
                'loaded_policy_hash': 'abc123',
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': next1,  # Feed persistent state
            'authorized_events': {}
        }

        rows2, scopes2, next2 = engine.evaluate(**inputs_terminal)

        # Verify O4 clears (NORMAL, no trip)
        self.assertEqual(rows2['O4']['state'], 'NORMAL',
                        "O4 must clear to NORMAL on terminal status for same order")
        self.assertFalse(rows2['O4']['would_have_tripped'],
                        "O4 must not trip after clearing")
        # Reason can be 'none' or specific clearing reason like 'original_order_terminal_status_received'
        self.assertIn(rows2['O4']['reason'], ['none', 'original_order_terminal_status_received'],
                     "O4 reason must indicate clearing")

        # Verify symbol scope returns to NORMAL
        self.assertEqual(scopes2.get('symbol:TQQQ', 'NORMAL'), 'NORMAL',
                        "symbol:TQQQ scope must be NORMAL after clearing")

        # Verify O4 state cleared for TQQQ
        if 'O4' in next2:
            self.assertNotIn('TQQQ', next2['O4'],
                           "TQQQ should be removed from O4 state after clearing")

    def test_account_halt_dominates_symbol_order_unknown(self):
        """O4: Account HALT dominates symbol ORDER-UNKNOWN (Q5 precedence)."""
        # Inputs with both O4 timeout AND O3 reconciliation failure
        inputs_mixed = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {},  # No matching fund holding
                'pending_orders': {
                    'TQQQ': {
                        'order_id': 'order_test_002',
                        'symbol': 'TQQQ',
                        'status': 'pending',
                        'timeout': True
                    }
                },
                # O3 reconciliation failure (account HALT)
                'positions_cash': 100000.0,
                'broker_cash': 95000.0,  # Mismatch > tolerance
                'reconciliation_tolerance': 100.0,
                'loaded_policy_hash': 'abc123',
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, scopes, _ = engine.evaluate(**inputs_mixed)

        # Verify O4 still evaluates (local contribution)
        self.assertEqual(rows['O4']['state'], 'ORDER-UNKNOWN',
                        "O4 local state must be ORDER-UNKNOWN")

        # Verify O3 triggers account HALT
        self.assertEqual(rows['O3']['state'], 'HALT',
                        "O3 must trigger account HALT on reconciliation failure")

        # CRITICAL: Account HALT must dominate symbol scope (§4.1 precedence)
        self.assertEqual(scopes.get('symbol:TQQQ'), 'HALT',
                        "Account HALT must dominate symbol:TQQQ scope (Q5)")
        self.assertEqual(scopes.get('account'), 'HALT',
                        "Account scope must be HALT")

    def test_o4_different_order_does_not_clear(self):
        """O4: Different order ID or unrecognized status cannot clear."""
        # Set up O4 state with order_A
        inputs_timeout = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {},
                'pending_orders': {
                    'TQQQ': {
                        'order_id': 'order_A',
                        'symbol': 'TQQQ',
                        'status': 'pending',
                        'timeout': True
                    }
                },
                'positions_cash': 100000.0,
                'broker_cash': 100000.0,
                'loaded_policy_hash': 'abc123',
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        _, _, next1 = engine.evaluate(**inputs_timeout)

        # Try to clear with order_B (different order)
        inputs_different = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:30:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {},
                'pending_orders': {
                    'TQQQ': {
                        'order_id': 'order_B',  # Different order
                        'symbol': 'TQQQ',
                        'status': 'filled',
                        'timeout': False
                    }
                },
                'positions_cash': 100000.0,
                'broker_cash': 100000.0,
                'loaded_policy_hash': 'abc123',
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': next1,
            'authorized_events': {}
        }

        rows2, _, next2 = engine.evaluate(**inputs_different)

        # O4 must NOT clear (different order ID)
        self.assertEqual(rows2['O4']['state'], 'ORDER-UNKNOWN',
                        "O4 must remain ORDER-UNKNOWN (different order ID)")
        self.assertTrue(rows2['O4']['would_have_tripped'],
                       "O4 must still trip (original order unresolved)")

        # Original order_A must still be in state
        self.assertIn('O4', next2)
        self.assertIn('TQQQ', next2['O4'])
        self.assertEqual(next2['O4']['TQQQ']['original_order_id'], 'order_A',
                        "Original order_A must persist")


class TestTierChangeDominanceControl(unittest.TestCase):
    """Tier change dominance control.

    The tier_change base input gives O9 account HALT, but none of its 24 base
    cells asserts the effective map. Exercise dominance and standalone O4 controls.

    Per REVIEW-REPORT "Further defects" and adjudication.
    """

    def test_tier_change_o9_account_halt(self):
        """O9: Tier change without card triggers account HALT."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'conservative',
                'tier_change_event': {  # Tier change detected
                    'from': 'balanced',
                    'to': 'conservative',
                    'unauthorized': True  # No authorized card
                },
                'funds': {
                    'TQQQ': {
                        'quote_staleness': 0,
                        'spread_width': 0.001,
                        'v7_spread_width': 0.01,
                        'trading_pause': False,
                        'session_time': 'regular'
                    }
                },
                'positions_cash': 100000.0,
                'broker_cash': 100000.0,
                'loaded_policy_hash': 'abc123',
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': {},
            'authorized_events': {}  # No authorized tier change
        }

        rows, scopes, _ = engine.evaluate(**inputs)

        # Verify O9 triggers account HALT
        self.assertEqual(rows['O9']['state'], 'HALT',
                        "O9 must trigger HALT on tier change without card")
        self.assertTrue(rows['O9']['would_have_tripped'],
                       "O9 must trip on tier change without card")
        # Reason indicates unauthorized change
        self.assertIn(rows['O9']['reason'], ['tier_change_without_card', 'unauthorized_change'],
                     "O9 reason must indicate unauthorized change")

        # Verify account scope is HALT
        self.assertEqual(scopes.get('account'), 'HALT',
                        "Account scope must be HALT")

        # Verify account HALT dominates fund scope (§4.1 precedence)
        self.assertEqual(scopes.get('fund:TQQQ'), 'HALT',
                        "Account HALT must dominate fund:TQQQ")

    def test_tier_change_with_authorized_card(self):
        """O9: Tier change WITH authorized card does not trip."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'tier_change_event': {
                    'from': 'conservative',
                    'to': 'balanced',
                    'unauthorized': False  # Flag for detection, but authorization checked via events
                },
                'funds': {},
                'positions_cash': 100000.0,
                'broker_cash': 100000.0,
                'loaded_policy_hash': 'abc123',
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': {},
            'authorized_events': [
                {
                    'type': 'tier_change_card',
                    'from': 'conservative',
                    'to': 'balanced',
                    'card_id': 'TC-001'
                }
            ]
        }

        rows, scopes, _ = engine.evaluate(**inputs)

        # O9 must not trip with authorized event
        self.assertEqual(rows['O9']['state'], 'NORMAL',
                        "O9 must be NORMAL with authorized tier change")
        self.assertFalse(rows['O9']['would_have_tripped'],
                        "O9 must not trip with authorized tier change")
        self.assertEqual(rows['O9']['reason'], 'none',
                        "O9 reason must be none")

        # Account scope can be DE-RISK from other rows (e.g., L3),
        # but O9 specifically should not contribute to it
        # The key test is that O9 itself doesn't trip


class TestFailClosedNegativeControls(unittest.TestCase):
    """Fail-closed negative controls.

    Per Q5 and "Further defects":
    - V4 missing measurements → NO-NEW-RISK refusal
    - O3/O6 missing evidence → HALT
    - O1 blocks increases on missing volatility
    - O1 fresh→missing: current missing source must REFUSE even after fresh session

    Each control demonstrates fail-closed behavior.
    """

    def test_v4_missing_measurements_refuses_new_risk(self):
        """V4: Missing volatility measurements → NO-NEW-RISK/missing_input."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {
                    'TQQQ': {
                        'forecast_volatility': None,  # Missing
                        'long_run_volatility': 0.24
                    }
                }
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, _, _ = engine.evaluate(**inputs)
        v4 = rows['V4']

        # V4 must refuse (fail closed)
        self.assertEqual(v4['state'], 'NO-NEW-RISK',
                        "V4 must refuse with NO-NEW-RISK on missing forecast")
        self.assertTrue(v4['would_have_tripped'],
                       "V4 must trip on missing volatility")
        self.assertEqual(v4['reason'], 'missing_input',
                        "V4 reason must be missing_input")
        self.assertFalse(v4['latched'],
                        "V4 interlock must not latch")

        # Missing observation earns ZERO clearing credit
        # (no active interlock state created)

    def test_o3_missing_reconciliation_data_halts(self):
        """O3: Missing cash reconciliation data → HALT/missing_input."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {},
                'positions_cash': None,  # Missing
                'broker_cash': 100000.0
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, scopes, next_state = engine.evaluate(**inputs)
        o3 = rows['O3']

        # O3 must HALT (fail closed)
        self.assertEqual(o3['state'], 'HALT',
                        "O3 must HALT on missing reconciliation data")
        self.assertTrue(o3['would_have_tripped'],
                       "O3 must trip on missing data")
        self.assertEqual(o3['reason'], 'missing_input',
                        "O3 reason must be missing_input")
        self.assertTrue(o3['latched'],
                       "O3 breaker must latch on missing input")

        # Account scope must be HALT
        self.assertEqual(scopes.get('account'), 'HALT',
                        "Account scope must be HALT")

        # Latch must persist in next_state
        self.assertIn('O3', next_state)
        self.assertTrue(next_state['O3']['latched'])

    def test_o6_missing_policy_hash_halts(self):
        """O6: Missing policy hash → HALT/missing_input."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {},
                'positions_cash': 100000.0,
                'broker_cash': 100000.0,
                'loaded_policy_hash': None,  # Missing
                'registered_policy_hash': 'abc123'
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, scopes, next_state = engine.evaluate(**inputs)
        o6 = rows['O6']

        # O6 must HALT (fail closed)
        self.assertEqual(o6['state'], 'HALT',
                        "O6 must HALT on missing policy hash")
        self.assertTrue(o6['would_have_tripped'],
                       "O6 must trip on missing hash")
        self.assertEqual(o6['reason'], 'missing_input',
                        "O6 reason must be missing_input")
        self.assertTrue(o6['latched'],
                       "O6 breaker must latch on missing input")

        # Account scope must be HALT
        self.assertEqual(scopes.get('account'), 'HALT',
                        "Account scope must be HALT")

        # Latch must persist in next_state
        self.assertIn('O6', next_state)
        self.assertTrue(next_state['O6']['latched'])

    def test_o1_blocks_increases_on_missing_volatility(self):
        """O1: Missing volatility blocks increases (conservative substitution)."""
        inputs = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'funds': {
                    'TQQQ': {
                        'forecast_volatility': None,  # Missing
                        'long_run_volatility': None,  # Also missing
                        'last_valid_volatility': 0.30
                    }
                }
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows, _, _ = engine.evaluate(**inputs)
        o1 = rows['O1']

        # O1 must refuse (NO-NEW-RISK)
        self.assertEqual(o1['state'], 'NO-NEW-RISK',
                        "O1 must block increases on missing volatility")
        self.assertTrue(o1['would_have_tripped'],
                       "O1 must trip on missing volatility")
        # O1 owns conservative volatility substitution (§4.4)

    def test_o1_fresh_to_missing_refuses(self):
        """O1: Current missing source must REFUSE even after prior fresh session.

        This is the critical O1 fresh→missing negative control per "Further defects" A.
        The bug (rows_ops.py:73-84) turned current missing into NORMAL when prior fresh ≥1.
        """
        # Step 1: Fresh session establishes O1_counter ≥1 in old code
        inputs_fresh = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-14',
            'as_of': '2026-01-14T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'bankroll': 100000.0,
                'high_water_mark': 100000.0,
                'joint_exposure': 25000.0,
                'max_loss_cap': 40000.0,
                'funds': {
                    'TQQQ': {
                        'forecast_volatility': 0.25,  # Fresh
                        'long_run_volatility': 0.24
                    }
                },
                'source_records': {
                    'market_data': {'as_of': '2026-01-14T16:00:00Z', 'age_sessions': 0},
                    'index_returns': {'as_of': '2026-01-14T16:00:00Z', 'age_sessions': 0},
                    'volatility': {'as_of': '2026-01-14T16:00:00Z', 'age_sessions': 0},
                    'positions': {'as_of': '2026-01-14T16:00:00Z', 'age_sessions': 0},
                    'broker_reconciliation': {'as_of': '2026-01-14T16:00:00Z', 'age_sessions': 0},
                    'session_calendar': {'as_of': '2026-01-14T16:00:00Z', 'age_sessions': 0}
                }
            },
            'prior_row_state': {},
            'authorized_events': {}
        }

        rows1, _, next1 = engine.evaluate(**inputs_fresh)

        # Verify fresh data accepted
        self.assertEqual(rows1['O1']['state'], 'NORMAL',
                        "O1 must accept fresh data")
        self.assertFalse(rows1['O1']['would_have_tripped'],
                        "O1 must not trip on fresh data")

        # Step 2: Next session, data becomes missing (current missing source)
        inputs_missing = {
            'spec_version': 'fuse-eval-spec/v1',
            'engine_hash': 'test-hash',
            'policy_hash': 'test-policy',
            'session': '2026-01-15',
            'as_of': '2026-01-15T16:00:00Z',
            'mode': 'shadow',
            'validated_inputs': {
                'tier': 'balanced',
                'bankroll': 100000.0,
                'high_water_mark': 100000.0,
                'joint_exposure': 25000.0,
                'max_loss_cap': 40000.0,
                'funds': {
                    'TQQQ': {
                        'forecast_volatility': None,  # Now missing
                        'long_run_volatility': None
                    }
                },
                'source_records': {
                    'market_data': {'as_of': '2026-01-15T16:00:00Z', 'age_sessions': 0},
                    'index_returns': {'as_of': '2026-01-15T16:00:00Z', 'age_sessions': 0},
                    'volatility': {'as_of': '2026-01-13T16:00:00Z', 'age_sessions': 2},  # Stale
                    'positions': {'as_of': '2026-01-15T16:00:00Z', 'age_sessions': 0},
                    'broker_reconciliation': {'as_of': '2026-01-15T16:00:00Z', 'age_sessions': 0},
                    'session_calendar': {'as_of': '2026-01-15T16:00:00Z', 'age_sessions': 0}
                }
            },
            'prior_row_state': next1,  # Feed prior fresh state
            'authorized_events': {}
        }

        rows2, _, _ = engine.evaluate(**inputs_missing)
        o1 = rows2['O1']

        # CRITICAL: O1 must REFUSE despite prior fresh session
        self.assertEqual(o1['state'], 'NO-NEW-RISK',
                        "O1 must refuse on CURRENT missing source (fresh→missing)")
        self.assertTrue(o1['would_have_tripped'],
                       "O1 must trip on current missing data")
        self.assertEqual(o1['reason'], 'stale_or_missing_input',
                        "O1 reason must indicate stale/missing")

        # This proves the bug is fixed: a current missing source cannot
        # become NORMAL just because prior O1_counter ≥1


if __name__ == '__main__':
    unittest.main()
