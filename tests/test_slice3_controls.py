"""Slice 3 verification controls.

Per PROMPT-FUSE1-P2F.md Slice 3:
- Complete-input D4 control (unmasked O4 symbol transition)
- Tier_change dominance control
- Fail-closed negative controls (V4/O3/O6/O1)

Each control must FAIL on pre-fix behavior and PASS on current engine.
Controls prove by execution that the engine can detect the defects they guard.
"""

import copy
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
                'funds': {
                    # No matching TQQQ fund holding - prevents masking while keeping O3 position data valid
                    'SOXL': {
                        'share_count': 800,
                        'ledger_value': 20000.0,
                        'broker_position': 800,
                        'broker_value': 20000.0,
                    }
                },
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
                'reconciliation_tolerance': 1.0,
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
                'funds': {
                    'SOXL': {
                        'share_count': 800,
                        'ledger_value': 20000.0,
                        'broker_position': 800,
                        'broker_value': 20000.0,
                    }
                },
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
                'reconciliation_tolerance': 1.0,
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
                    'card_id': 'TC-001',
                    'session': '2026-01-15',
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


class TestG3FailClosedAndV1FiveSession(unittest.TestCase):
    """G3 (F1-A06): 9 silent-pass probes + §6 V1 five-session branch."""

    @classmethod
    def setUpClass(cls):
        import json
        cls.normal_vi = json.loads(
            (repo_root / 'goldens' / 'scenarios.json').read_text(encoding='utf-8')
        )['scenarios']['normal']['inputs']['validated_inputs']

    def _eval(self, vi, session='2026-01-05', prior=None, events=None):
        return engine.evaluate(
            'fuse-eval-spec/v1', 'test-hash', 'registered_policy_hash_v1',
            session, f'{session}T16:00:00Z', 'shadow', vi, prior or {}, events or []
        )

    def test_v1_missing_fund_return_refuses(self):
        import copy
        vi = copy.deepcopy(self.normal_vi)
        vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
        vi['funds']['TQQQ'].pop('fund_return')
        rows, _, _ = self._eval(vi)
        self.assertEqual(rows['V1']['state'], 'NO-NEW-RISK')
        self.assertTrue(rows['V1']['would_have_tripped'])
        self.assertEqual(rows['V1']['reason'], 'missing_input')

    def test_v1_missing_index_return_refuses(self):
        """R1: V1 must fail closed when index_return is missing even on a 1-session open window."""
        import copy
        vi = copy.deepcopy(self.normal_vi)
        vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
        vi['funds']['TQQQ']['index_return'] = None
        rows, eff, _ = self._eval(vi)
        self.assertEqual(rows['V1']['state'], 'NO-NEW-RISK')
        self.assertTrue(rows['V1']['would_have_tripped'])
        self.assertFalse(rows['V1']['latched'])
        self.assertEqual(rows['V1']['reason'], 'missing_input')
        self.assertEqual(eff['fund:TQQQ'], 'NO-NEW-RISK')

    def test_v4_nan_forecast_volatility_refuses(self):
        import copy
        vi = copy.deepcopy(self.normal_vi)
        vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
        vi['funds']['TQQQ']['forecast_volatility'] = float('nan')
        rows, _, _ = self._eval(vi)
        self.assertEqual(rows['V4']['state'], 'NO-NEW-RISK')
        self.assertTrue(rows['V4']['would_have_tripped'])
        self.assertEqual(rows['V4']['reason'], 'missing_input')

    def test_o1_all_six_sources_nan_age_refuse(self):
        import copy
        sources = [
            'market_data', 'index_returns', 'volatility',
            'positions', 'broker_reconciliation', 'session_calendar'
        ]
        for src in sources:
            with self.subTest(source=src):
                vi = copy.deepcopy(self.normal_vi)
                vi['source_records'][src]['age_sessions'] = float('nan')
                rows, _, _ = self._eval(vi)
                self.assertEqual(rows['O1']['state'], 'NO-NEW-RISK')
                self.assertTrue(rows['O1']['would_have_tripped'])

    def test_o1_four_field_removal_refuses_even_with_fresh_sources(self):
        import copy
        vi = copy.deepcopy(self.normal_vi)
        for key in ('bankroll', 'high_water_mark', 'joint_exposure', 'max_loss_cap'):
            vi.pop(key)
        rows, _, _ = self._eval(vi)
        self.assertEqual(rows['O1']['state'], 'NO-NEW-RISK')
        self.assertTrue(rows['O1']['would_have_tripped'])
        self.assertEqual(rows['O1']['reason'], 'stale_or_missing_input')

    def test_v1_five_session_jan5_to_9_trips_and_latches(self):
        """§6 control: 5 consecutive 0.5pp days compound to 2.5251253pp -> NO-NEW-RISK latched."""
        import copy
        prior = {}
        rows = {}
        for day in ('2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08', '2026-01-09'):
            vi = copy.deepcopy(self.normal_vi)
            vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
            vi['funds']['TQQQ'].update({
                'fund_return': 0.005,
                'index_return': 0.0,
                'modelled_fee': 0.0,
                'modelled_financing': 0.0,
                'sessions_window': 5,
            })
            rows, _, prior = self._eval(vi, session=day, prior=prior)
            if day != '2026-01-09':
                self.assertEqual(rows['V1']['state'], 'NO-NEW-RISK')
                self.assertFalse(rows['V1']['latched'])

        self.assertEqual(rows['V1']['state'], 'NO-NEW-RISK')
        self.assertTrue(rows['V1']['would_have_tripped'])
        self.assertTrue(rows['V1']['latched'])
        self.assertEqual(rows['V1']['reason'], 'tracking_deviation_exceeds_2_0pp')
        self.assertAlmostEqual(rows['V1']['deviation'], 0.025251253125, places=9)
        self.assertTrue(prior['V1']['TQQQ']['latched'])

    def test_v1_five_session_benign_window_clears_and_missing_history_refuses(self):
        import copy
        vi = copy.deepcopy(self.normal_vi)
        vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
        vi['funds']['TQQQ'].update({
            'fund_return': 0.001,
            'index_return': 0.0,
            'modelled_fee': 0.0,
            'modelled_financing': 0.0,
            'sessions_window': 5,
        })
        rows_day1, _, _ = self._eval(vi, session='2026-01-05')
        self.assertEqual(rows_day1['V1']['state'], 'NO-NEW-RISK')
        self.assertEqual(rows_day1['V1']['reason'], 'missing_input')

        prior = {}
        for day in ('2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08', '2026-01-09'):
            rows_day, _, prior = self._eval(vi, session=day, prior=prior)
        self.assertEqual(rows_day['V1']['state'], 'NORMAL')
        self.assertFalse(rows_day['V1']['would_have_tripped'])
        self.assertFalse(rows_day['V1']['latched'])

    def test_v1_five_session_preserves_history_across_holiday_and_closed(self):
        """R2: Holiday/closed call mid-window preserves 4-day history so day 5 still trips & latches V1."""
        import copy
        import json
        holiday_vi = json.loads(
            (repo_root / 'goldens' / 'scenarios.json').read_text(encoding='utf-8')
        )['scenarios']['holiday']['inputs']['validated_inputs']

        for closed_variant in ('holiday_with_fund', 'closed_with_fund', 'holiday_empty_funds'):
            with self.subTest(closed_variant=closed_variant):
                prior = {}
                for day in ('2026-01-13', '2026-01-14', '2026-01-15', '2026-01-16'):
                    vi = copy.deepcopy(self.normal_vi)
                    vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
                    vi['funds']['TQQQ'].update({
                        'fund_return': 0.005,
                        'index_return': 0.0,
                        'modelled_fee': 0.0,
                        'modelled_financing': 0.0,
                        'sessions_window': 5,
                    })
                    _, _, prior = self._eval(vi, session=day, prior=prior)
                self.assertEqual(len(prior['V1']['TQQQ']['session_returns']), 4)

                # Jan 19 holiday/closed call must NOT wipe 4-day return window
                vi_closed = copy.deepcopy(holiday_vi)
                if closed_variant == 'closed_with_fund':
                    vi_closed['session_calendar_status'] = 'closed'
                    vi_closed['exchange_status'] = 'closed'
                elif closed_variant == 'holiday_empty_funds':
                    vi_closed['funds'] = {}
                else:
                    vi_closed['funds'] = {'TQQQ': copy.deepcopy(holiday_vi['funds']['TQQQ'])}
                r_hol, _, prior_after_hol = self._eval(vi_closed, session='2026-01-19', prior=prior)
                self.assertEqual(r_hol['V1']['state'], 'NORMAL')
                self.assertEqual(len(prior_after_hol.get('V1', {}).get('TQQQ', {}).get('session_returns', [])), 4)

                # Jan 20 5th trading day with +0.5pp compounds to ~2.5251253pp -> NO-NEW-RISK latched
                vi_20 = copy.deepcopy(self.normal_vi)
                vi_20['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
                vi_20['funds']['TQQQ'].update({
                    'fund_return': 0.005,
                    'index_return': 0.0,
                    'modelled_fee': 0.0,
                    'modelled_financing': 0.0,
                    'sessions_window': 5,
                })
                r_20, _, prior_20 = self._eval(vi_20, session='2026-01-20', prior=prior_after_hol)
                self.assertEqual(r_20['V1']['state'], 'NO-NEW-RISK')
                self.assertTrue(r_20['V1']['would_have_tripped'])
                self.assertTrue(r_20['V1']['latched'])
                self.assertEqual(r_20['V1']['reason'], 'tracking_deviation_exceeds_2_0pp')
                self.assertAlmostEqual(r_20['V1']['deviation'], 0.025251253125, places=9)

                # Subsequent 4 zero-return days without re-arm remain latched NO-NEW-RISK
                p_cur = prior_20
                for d in ('2026-01-21', '2026-01-22', '2026-01-23', '2026-01-26'):
                    vi_z = copy.deepcopy(self.normal_vi)
                    vi_z['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
                    vi_z['funds']['TQQQ'].update({
                        'fund_return': 0.0,
                        'index_return': 0.0,
                        'modelled_fee': 0.0,
                        'modelled_financing': 0.0,
                        'sessions_window': 5,
                    })
                    r_z, _, p_cur = self._eval(vi_z, session=d, prior=p_cur)
                    self.assertEqual(r_z['V1']['state'], 'NO-NEW-RISK')
                    self.assertTrue(r_z['V1']['latched'])
                    self.assertEqual(r_z['V1']['reason'], 'latched_prior_trip')

    def test_v1_five_session_rolling_history_accumulates_without_sessions_window(self):
        """A06: 5 consecutive +0.5% deviation days trip V1 even when sessions_window is omitted."""
        prior = {}
        for idx, day in enumerate(('2026-01-13', '2026-01-14', '2026-01-15', '2026-01-16', '2026-01-19'), start=1):
            vi = copy.deepcopy(self.normal_vi)
            vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
            vi['funds']['TQQQ'].pop('sessions_window', None)
            vi['funds']['TQQQ'].update({
                'fund_return': 0.005,
                'index_return': 0.0,
                'modelled_fee': 0.0,
                'modelled_financing': 0.0,
            })
            rows, eff, prior = self._eval(vi, session=day, prior=prior)
            if idx < 5:
                self.assertEqual(rows['V1']['state'], 'NORMAL')
            else:
                self.assertEqual(rows['V1']['state'], 'NO-NEW-RISK')
                self.assertTrue(rows['V1']['would_have_tripped'])
                self.assertTrue(rows['V1']['latched'])
                self.assertEqual(eff['fund:TQQQ'], 'NO-NEW-RISK')

    def test_o3_non_finite_balances_fail_closed(self):
        """A06: NaN/inf/bool cash or fund balances fail closed to HALT in O3."""
        for bad_val in (float('nan'), float('inf'), -1.0, True):
            with self.subTest(bad_val=bad_val):
                vi = copy.deepcopy(self.normal_vi)
                vi['broker_cash'] = bad_val
                rows, eff, _ = self._eval(vi)
                self.assertEqual(rows['O3']['state'], 'HALT')
                self.assertEqual(eff['account'], 'HALT')

    def test_v6_exact_carrying_cost_formula_and_nan_fail_closed(self):
        """A06: V6 uses carrying_cost_measured > (excess_return_shrunk / 4) and fails closed on NaN."""
        vi = copy.deepcopy(self.normal_vi)
        vi['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
        vi['funds']['TQQQ'].update({'carrying_cost_measured': 0.10, 'excess_return_shrunk': 0.04})
        rows, _, _ = self._eval(vi)
        self.assertTrue(rows['V6']['would_have_tripped'])
        self.assertEqual(rows['V6']['reason'], 'carrying_cost_exceeded')
        self.assertAlmostEqual(rows['V6']['outputs']['threshold'], 0.01)

        vi_nan = copy.deepcopy(vi)
        vi_nan['funds']['TQQQ']['carrying_cost_measured'] = float('nan')
        rows_nan, _, _ = self._eval(vi_nan)
        self.assertTrue(rows_nan['V6']['would_have_tripped'])
        self.assertEqual(rows_nan['V6']['reason'], 'missing_input')

    def test_a11_non_finite_and_negative_thresholds_fail_closed(self):
        """A11: NaN/inf/negative/bool tolerances on V5, V7, O5 fail closed; O5 price collar enforces bounds."""
        vi = copy.deepcopy(self.normal_vi)
        vi.update({'v5_tolerance': float('nan'), 'v7_spread_width': float('nan'), 'o5_collar': float('nan')})
        rows, _, _ = self._eval(vi)
        self.assertTrue(rows['V5']['would_have_tripped'])
        self.assertEqual(rows['V5']['reason'], 'invalid_input')
        self.assertTrue(rows['V7']['would_have_tripped'])
        self.assertEqual(rows['V7']['reason'], 'invalid_input')
        self.assertTrue(rows['O5']['would_have_tripped'])
        self.assertEqual(rows['O5']['reason'], 'invalid_input')

        vi_neg = copy.deepcopy(self.normal_vi)
        vi_neg.update({'v5_tolerance': -0.01, 'v7_spread_width': -0.02, 'o5_collar': -0.05})
        rows_neg, _, _ = self._eval(vi_neg)
        self.assertTrue(rows_neg['V5']['would_have_tripped'])
        self.assertEqual(rows_neg['V5']['reason'], 'invalid_input')
        self.assertTrue(rows_neg['V7']['would_have_tripped'])
        self.assertEqual(rows_neg['V7']['reason'], 'invalid_input')
        self.assertTrue(rows_neg['O5']['would_have_tripped'])
        self.assertEqual(rows_neg['O5']['reason'], 'invalid_input')

        vi_collar = copy.deepcopy(self.normal_vi)
        vi_collar.update({'o5_collar': 0.05, 'o5_reference_price': 100.0, 'o5_order_price': 120.0})
        rows_col, _, _ = self._eval(vi_collar)
        self.assertTrue(rows_col['O5']['would_have_tripped'])
        self.assertEqual(rows_col['O5']['reason'], 'pre_trade_limit_violation')

    def test_o5_mixed_reject_pass_reject_preserves_session_count_and_halts_on_third(self):
        """A07: Mixed Reject-Reject-Pass-Reject in one session counts 1, 2, 2, 3 and latches HALT."""
        prior = {}
        seq = []
        for bad in (True, True, False, True):
            vi = copy.deepcopy(self.normal_vi)
            vi['o5_collar'] = 0.05
            if bad:
                vi['o5_side'] = 'sell'
            rows, eff, prior = self._eval(vi, session='2026-01-05', prior=prior)
            seq.append((rows['O5']['state'], rows['O5']['rejection_count_this_session'], eff['account']))
        self.assertEqual(
            seq,
            [('NORMAL', 1, 'NORMAL'), ('NORMAL', 2, 'NORMAL'), ('NORMAL', 2, 'NORMAL'), ('HALT', 3, 'HALT')]
        )

    def test_o5_settled_cash_zero_blocks_positive_order(self):
        """F1-O5: Explicit None check rejects buy when settled_cash=0 and o5_order_value=100."""
        vi = copy.deepcopy(self.normal_vi)
        vi.update({'o5_collar': 0.05, 'o5_side': 'buy', 'o5_order_value': 100.0, 'settled_cash': 0.0})
        rows, _, _ = self._eval(vi)
        self.assertTrue(rows['O5']['would_have_tripped'])
        self.assertEqual(rows['O5']['reason'], 'pre_trade_limit_violation')

    def test_o7_heartbeat_gap_and_v1_joint_priority(self):
        """A08: 7h heartbeat gap (>3600s) trips O7 NO-NEW-RISK, survives across sessions + V1, clears on rearm."""
        vi = copy.deepcopy(self.normal_vi)
        vi.update({'last_heartbeat': '2026-01-13T09:00:00Z', 'scheduled_interval': 3600})
        rows1, eff1, st1 = self._eval(vi, session='2026-01-13')
        self.assertEqual(rows1['O7']['state'], 'NO-NEW-RISK')
        self.assertTrue(rows1['O7']['latched'])
        self.assertEqual(eff1['account'], 'NO-NEW-RISK')

        # Consecutive session with fresh heartbeat + TQQQ V1 1-day trip keeps O7 latched NO-NEW-RISK
        vi2 = copy.deepcopy(self.normal_vi)
        vi2.update({'last_heartbeat': '2026-01-14T15:59:30Z', 'scheduled_interval': 3600})
        vi2['funds']['TQQQ']['fund_return'] = 0.05
        rows2, eff2, st2 = self._eval(vi2, session='2026-01-14', prior=st1)
        self.assertEqual(rows2['O7']['state'], 'NO-NEW-RISK')
        self.assertEqual(rows2['O7']['reason'], 'latched_prior_trip')
        self.assertEqual(eff2['account'], 'NO-NEW-RISK')
        self.assertEqual(eff2['fund:TQQQ'], 'NO-NEW-RISK')

        # Authorized re-arm clears O7 latch cleanly when session & account scope match (Q4)
        vi3 = copy.deepcopy(self.normal_vi)
        vi3.update({'last_heartbeat': '2026-01-15T15:59:30Z', 'scheduled_interval': 3600})
        rows3, eff3, st3 = self._eval(
            vi3, session='2026-01-15', prior=st2,
            events=[{'type': 'rearm', 'row_id': 'O7', 'session': '2026-01-15', 'scope': 'account'}]
        )
        self.assertEqual(rows3['O7']['state'], 'NORMAL')
        self.assertEqual(rows3['O7']['reason'], 'authorized_rearm')
        self.assertEqual(st3['O7'], {})
        self.assertEqual(eff3['account'], 'NORMAL')

    def test_o9_tier_change_card_does_not_authorize_o9_change_descriptors(self):
        """F1-O9: tier_change_card alone must NOT clear unauthorized o9_change_descriptors."""
        vi = copy.deepcopy(self.normal_vi)
        vi.update({
            'tier_change_event': {'from': 'balanced', 'to': 'aggressive'},
            'o9_change_descriptors': [{'param': 'max_loss_cap', 'from': 60000, 'to': 80000}],
        })
        rows, eff, _ = self._eval(vi, events=[{'type': 'tier_change_card'}])
        self.assertEqual(rows['O9']['state'], 'HALT')
        self.assertTrue(rows['O9']['latched'])
        self.assertEqual(rows['O9']['reason'], 'unauthorized_change')
        self.assertEqual(eff['account'], 'HALT')

    def test_o9_rejects_stitched_multi_card_parameter_approval(self):
        """R4/O9: Requires one single parameter_change_card approving all changed fields (no cross-card stitching)."""
        vi = copy.deepcopy(self.normal_vi)
        vi['o9_change_descriptors'] = {'param': 'max_loss_cap', 'from': 60000, 'to': 80000}
        stitched_cards = [
            {'type': 'parameter_change_card', 'change_descriptors': {'param': 'max_loss_cap', 'from': 60000, 'to': 61000}},
            {'type': 'parameter_change_card', 'change_descriptors': {'param': 'other_param', 'to': 80000}},
        ]
        r_bad, _, _ = self._eval(vi, events=stitched_cards)
        self.assertEqual(r_bad['O9']['state'], 'HALT')
        self.assertTrue(r_bad['O9']['latched'])
        self.assertEqual(r_bad['O9']['reason'], 'unauthorized_change')

        vi_ok = copy.deepcopy(vi)
        vi_ok['max_loss_cap'] = 80000.0
        single_card = [
            {
                'type': 'parameter_change_card',
                'session': '2026-01-05',
                'change_descriptors': {'param': 'max_loss_cap', 'from': 60000, 'to': 80000},
            }
        ]
        r_ok, _, _ = self._eval(vi_ok, events=single_card)
        self.assertEqual(r_ok['O9']['state'], 'NORMAL')
        self.assertFalse(r_ok['O9']['would_have_tripped'])

    def test_account_rearm_enforces_session_date_and_account_scope(self):
        """R4/Q4: Account re-arms on O5, O7, O9 reject prior-day, undated, and fund-scoped cards."""
        # O5 latch
        vi_o5 = copy.deepcopy(self.normal_vi)
        vi_o5.update({'o5_collar': 0.05, 'o5_side': 'sell'})
        st_o5 = {}
        for _ in range(3):
            _, _, st_o5 = self._eval(vi_o5, session='2026-01-05', prior=st_o5)
        # O7 latch
        vi_o7 = copy.deepcopy(self.normal_vi)
        vi_o7.update({'last_heartbeat': '2026-01-05T08:00:00Z', 'scheduled_interval': 3600})
        _, _, st_o7 = self._eval(vi_o7, session='2026-01-05')
        # O9 latch
        vi_o9 = copy.deepcopy(self.normal_vi)
        vi_o9['o9_change_descriptors'] = {'param': 'max_loss_cap', 'to': 80000}
        _, _, st_o9 = self._eval(vi_o9, session='2026-01-05')

        for row_id, st_latched in (('O5', st_o5), ('O7', st_o7), ('O9', st_o9)):
            vi_clean = copy.deepcopy(self.normal_vi)
            vi_clean.update({'last_heartbeat': '2026-01-06T15:59:30Z', 'scheduled_interval': 3600, 'o5_collar': 0.05})
            for bad_ev in (
                {'type': 'rearm', 'row_id': row_id, 'session': '2026-01-05'},
                {'type': 'rearm', 'row_id': row_id, 'session': '2026-01-06', 'fund': 'TQQQ'},
                {'type': 'rearm', 'row_id': row_id, 'session': '2026-01-06', 'scope': 'fund:TQQQ'},
                {'type': 'rearm', 'row_id': row_id},
            ):
                r_refuse, _, _ = self._eval(vi_clean, session='2026-01-06', prior=st_latched, events=[bad_ev])
                self.assertTrue(r_refuse[row_id]['latched'], f"{row_id} accepted invalid card {bad_ev}")

            r_clear, _, _ = self._eval(
                vi_clean, session='2026-01-06', prior=st_latched,
                events=[{'type': 'rearm', 'row_id': row_id, 'session': '2026-01-06', 'scope': 'account'}]
            )
            self.assertEqual(r_clear[row_id]['reason'], 'authorized_rearm')
            self.assertEqual(r_clear[row_id]['state'], 'NORMAL')

    def test_loss_breakers_l4_nan_l6_mixed_indices_l6_o3_block_and_missing_bankroll(self):
        """R4/L3/L4/L6: L4 NaN fails closed; L6 scans past invalid index; L6 refuses rearm on O3 failure; missing bankroll safe."""
        vi_l4 = copy.deepcopy(self.normal_vi)
        vi_l4['one_session_loss'] = float('nan')
        r_l4, _, _ = self._eval(vi_l4)
        self.assertEqual(r_l4['L4']['state'], 'NO-NEW-RISK')

        vi_l6 = copy.deepcopy(self.normal_vi)
        vi_l6['index_one_session_returns'] = {'SPX': 'bad', 'NDX': -0.12}
        r_l6, _, _ = self._eval(vi_l6)
        self.assertEqual(r_l6['L6']['state'], 'HALT')
        self.assertEqual(r_l6['L6']['reason'], 'index_fall_10pct')

        vi_l6_trip = copy.deepcopy(self.normal_vi)
        vi_l6_trip['market_halt_level'] = 3
        _, _, st_l6 = self._eval(vi_l6_trip, session='2026-01-05')
        vi_o3_bad = copy.deepcopy(self.normal_vi)
        vi_o3_bad.update({'broker_cash': 90000.0, 'last_heartbeat': '2026-01-06T15:59:30Z'})
        r_l6_blocked, _, _ = self._eval(
            vi_o3_bad, session='2026-01-06', prior=st_l6,
            events=[{'type': 'rearm', 'row_id': 'L6', 'session': '2026-01-06'}]
        )
        self.assertEqual(r_l6_blocked['L6']['state'], 'HALT')
        self.assertTrue(r_l6_blocked['L6']['latched'])

        vi_nobk = copy.deepcopy(self.normal_vi)
        vi_nobk.pop('bankroll')
        r_nobk, _, _ = self._eval(vi_nobk)
        self.assertEqual(r_nobk['L3']['state'], 'DE-RISK')

    def test_v1_empty_five_session_history_and_v4_holiday_omitted_scope(self):
        """R4/V1/V4: empty five_session_history=[] preserves prior; V4 holiday stays at 9; omitted V4 kept in scopes."""
        prior = {}
        for idx, day in enumerate(('2026-01-13', '2026-01-14', '2026-01-15', '2026-01-16', '2026-01-19'), start=1):
            vi = copy.deepcopy(self.normal_vi)
            vi['funds'] = {'TQQQ': {
                **copy.deepcopy(self.normal_vi['funds']['TQQQ']),
                'fund_return': 0.005, 'index_return': 0.0, 'modelled_fee': 0.0,
                'modelled_financing': 0.0, 'five_session_history': [],
            }}
            rows, _, prior = self._eval(vi, session=day, prior=prior)
            if idx == 5:
                self.assertEqual(rows['V1']['state'], 'NO-NEW-RISK')
                self.assertTrue(rows['V1']['latched'])

        vi_hol = copy.deepcopy(self.normal_vi)
        vi_hol.update({'session_calendar_status': 'holiday', 'exchange_status': 'closed', 'last_heartbeat': '2026-01-19T15:59:30Z'})
        v4_9 = {'V4': {'TQQQ': {'clearing_counter': 9, 'last_session_below_threshold': '2026-01-16'}}}
        r_hol, _, s_hol = self._eval(vi_hol, session='2026-01-19', prior=v4_9)
        self.assertEqual(r_hol['V4']['state'], 'NO-NEW-RISK')
        self.assertEqual(r_hol['V4']['outputs']['TQQQ']['clearing_counter'], 9)
        self.assertEqual(s_hol['V4']['TQQQ']['clearing_counter'], 9)

        vi_omit = copy.deepcopy(self.normal_vi)
        vi_omit['funds'] = {'SOXL': copy.deepcopy(self.normal_vi['funds']['SOXL'])}
        v4_5 = {'V4': {'TQQQ': {'clearing_counter': 5, 'last_session_below_threshold': '2026-01-05'}}}
        r_omit, eff_omit, _ = self._eval(vi_omit, session='2026-01-06', prior=v4_5)
        self.assertEqual(eff_omit.get('fund:TQQQ'), 'NO-NEW-RISK')
        self.assertEqual(r_omit['V4']['state'], 'NO-NEW-RISK')

    def test_v6_canonical_precedence_missing_and_v7_missing_quotes(self):
        """R4/V6/V7: V6 missing inputs fail closed & canonical beats synthetic; V7 missing quotes fail closed."""
        vi_miss = copy.deepcopy(self.normal_vi)
        vi_miss['funds']['TQQQ'].pop('carrying_cost_measured')
        vi_miss['funds']['TQQQ'].pop('excess_return_shrunk')
        r_miss, _, _ = self._eval(vi_miss)
        self.assertTrue(r_miss['V6']['would_have_tripped'])
        self.assertTrue(r_miss['V6']['outputs']['notify'])

        vi_syn = copy.deepcopy(self.normal_vi)
        vi_syn['funds']['TQQQ'].update({
            'carrying_cost_measured': 0.10, 'excess_return_shrunk': 0.04,
            'v6_cost_per_unit_exposure': 0.001, 'v6_threshold': 0.5,
        })
        r_syn, _, _ = self._eval(vi_syn)
        self.assertTrue(r_syn['V6']['would_have_tripped'])
        self.assertEqual(r_syn['V6']['reason'], 'carrying_cost_exceeded')

        vi_v7 = copy.deepcopy(self.normal_vi)
        vi_v7['v7_spread_width'] = 0.02
        vi_v7['funds']['TQQQ'].pop('quote_staleness')
        vi_v7['funds']['TQQQ'].pop('spread_width')
        r_v7, _, _ = self._eval(vi_v7)
        self.assertTrue(r_v7['V7']['would_have_tripped'])

    def test_o3_shares_missing_pos_omitted_tol_and_o7_missing_heartbeat_fail_closed(self):
        """R4/O3/O7: O3 checks shares, missing both position values, and missing tolerance; O7 fails when both absent."""
        vi_sh = copy.deepcopy(self.normal_vi)
        vi_sh['funds']['TQQQ']['broker_position'] = 0
        self.assertEqual(self._eval(vi_sh)[0]['O3']['state'], 'HALT')

        vi_nv = copy.deepcopy(self.normal_vi)
        vi_nv['funds']['TQQQ'].pop('ledger_value')
        vi_nv['funds']['TQQQ'].pop('broker_value')
        self.assertEqual(self._eval(vi_nv)[0]['O3']['state'], 'HALT')

        vi_nt = copy.deepcopy(self.normal_vi)
        vi_nt.pop('reconciliation_tolerance')
        vi_nt['broker_cash'] = 99999.5
        self.assertEqual(self._eval(vi_nt)[0]['O3']['state'], 'HALT')

        vi_o7 = copy.deepcopy(self.normal_vi)
        vi_o7.pop('last_heartbeat')
        vi_o7.pop('scheduled_interval')
        self.assertEqual(self._eval(vi_o7)[0]['O7']['state'], 'NO-NEW-RISK')

    def test_o5_qty_price_derivation_canonical_settled_cash_and_whitelists(self):
        """R4/O5: qty*price cash check, settled_cash=0 beats o5_settled_cash=200, account_whitelist & BIL."""
        vi_qp = copy.deepcopy(self.normal_vi)
        vi_qp.update({'o5_collar': 0.05, 'o5_side': 'buy', 'settled_cash': 0.0, 'o5_order_size': 2, 'o5_order_price': 50.0, 'o5_reference_price': 50.0})
        r_qp, _, _ = self._eval(vi_qp)
        self.assertTrue(r_qp['O5']['would_have_tripped'])

        vi_sc = copy.deepcopy(self.normal_vi)
        vi_sc.update({'o5_collar': 0.05, 'o5_side': 'buy', 'settled_cash': 0.0, 'o5_settled_cash': 200.0, 'o5_order_value': 100.0})
        self.assertTrue(self._eval(vi_sc)[0]['O5']['would_have_tripped'])

        vi_acct = copy.deepcopy(self.normal_vi)
        vi_acct.update({'o5_collar': 0.05, 'o5_account': 'rogue_acct', 'o5_symbol': 'BIL'})
        self.assertTrue(self._eval(vi_acct)[0]['O5']['would_have_tripped'])

        vi_bil = copy.deepcopy(self.normal_vi)
        vi_bil.update({
            'o5_collar': 0.05, 'o5_account': 'synthetic_account_1', 'o5_symbol': 'BIL',
            'o5_side': 'buy', 'o5_order_size': 1, 'o5_order_value': 50.0, 'settled_cash': 200.0,
            'unit_price': 50.0, 'o5_reference_price': 50.0,
        })
        self.assertFalse(self._eval(vi_bil)[0]['O5']['would_have_tripped'])

    def test_intra_session_l5_o1_and_o2_status_whitelist(self):
        """R4/L5/O1/O2: L5/O1 persist within same session; O2 rejects 'n/a' calendar/exchange tokens."""
        vi_l5 = copy.deepcopy(self.normal_vi)
        vi_l5['market_halt_level'] = 1
        _, _, st_l5 = self._eval(vi_l5, session='2026-01-05')
        r_same, _, st_same = self._eval(copy.deepcopy(self.normal_vi), session='2026-01-05', prior=st_l5)
        self.assertEqual(r_same['L5']['state'], 'NO-NEW-RISK')
        vi_next = copy.deepcopy(self.normal_vi)
        vi_next['last_heartbeat'] = '2026-01-06T15:59:30Z'
        r_next, _, _ = self._eval(vi_next, session='2026-01-06', prior=st_same)
        self.assertEqual(r_next['L5']['state'], 'NORMAL')

        vi_stale = copy.deepcopy(self.normal_vi)
        vi_stale['source_records']['market_data']['age_sessions'] = 2
        _, _, st_o1 = self._eval(vi_stale, session='2026-01-05')
        r_o1_same, _, st_o1_same = self._eval(copy.deepcopy(self.normal_vi), session='2026-01-05', prior=st_o1)
        self.assertEqual(r_o1_same['O1']['state'], 'NO-NEW-RISK')
        self.assertEqual(st_o1_same['O1']['fresh_session_count'], 0)
        r_o1_next, _, st_o1_next = self._eval(vi_next, session='2026-01-06', prior=st_o1_same)
        self.assertEqual(r_o1_next['O1']['state'], 'NORMAL')
        self.assertEqual(st_o1_next['O1']['fresh_session_count'], 1)

        vi_o2 = copy.deepcopy(self.normal_vi)
        vi_o2.update({'session_calendar_status': 'n/a', 'exchange_status': 'n/a'})
        self.assertTrue(self._eval(vi_o2)[0]['O2']['would_have_tripped'])

    def test_j1_nan_cap_fails_closed(self):
        """R4/J1: Non-finite tier_joint_cap=NaN fails closed with finite 0.0 cap/headroom and True flags."""
        vi = copy.deepcopy(self.normal_vi)
        vi['tier_joint_cap'] = float('nan')
        r_j1 = self._eval(vi)[0]['J1']
        self.assertTrue(r_j1['would_have_tripped'])
        self.assertEqual(r_j1['outputs']['cap'], 0.0)
        self.assertEqual(r_j1['outputs']['headroom'], 0.0)
        self.assertTrue(r_j1['outputs']['above_cap'])
        self.assertTrue(r_j1['outputs']['above_trim_threshold'])

    def test_r5_unified_session_utc_midnight_dual_row_and_fund_rearm(self):
        """R5 (A): session > as_of[:10], reject row!=row_id, require date on account & fund V1/V2/V3 re-arms."""
        import copy

        # 1. L4, L5, O1 crossing UTC midnight on same trading session='2026-01-05' stay restricted
        vi_l4 = copy.deepcopy(self.normal_vi)
        vi_l4['one_session_loss'] = 0.05
        _, _, st_l4 = self._eval(vi_l4, session='2026-01-05')
        r_l4_mid, _, _ = engine.evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-06T00:05:00Z', 'shadow',
            copy.deepcopy(self.normal_vi), st_l4,
            [{'type': 'rearm', 'row': 'L4', 'session': '2026-01-05'}],
        )
        self.assertEqual(r_l4_mid['L4']['state'], 'NO-NEW-RISK')
        self.assertTrue(r_l4_mid['L4']['latched'])

        # L4 also refuses re-arm on market_closed holiday session even after trip date
        vi_l4_hol = copy.deepcopy(self.normal_vi)
        vi_l4_hol.update({'session_calendar_status': 'holiday', 'exchange_status': 'closed'})
        r_l4_hol, _, _ = self._eval(
            vi_l4_hol, session='2026-01-06', prior=st_l4,
            events=[{'type': 'rearm', 'row': 'L4', 'session': '2026-01-06'}],
        )
        self.assertEqual(r_l4_hol['L4']['state'], 'NO-NEW-RISK')

        vi_l5 = copy.deepcopy(self.normal_vi)
        vi_l5['market_halt_level'] = 1
        _, _, st_l5 = self._eval(vi_l5, session='2026-01-05')
        r_l5_mid, _, _ = engine.evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-06T00:05:00Z', 'shadow',
            copy.deepcopy(self.normal_vi), st_l5, [],
        )
        self.assertEqual(r_l5_mid['L5']['state'], 'NO-NEW-RISK')

        vi_stale = copy.deepcopy(self.normal_vi)
        vi_stale['source_records']['market_data']['age_sessions'] = 2
        _, _, st_o1 = self._eval(vi_stale, session='2026-01-05')
        r_o1_mid, _, _ = engine.evaluate(
            'fuse-eval-spec/v1', 'h', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-06T00:05:00Z', 'shadow',
            copy.deepcopy(self.normal_vi), st_o1, [],
        )
        self.assertEqual(r_o1_mid['O1']['state'], 'NO-NEW-RISK')
        self.assertEqual(r_o1_mid['O1']['reason'], 'clearing_period')

        # 2. Dual-row card row='O5', row_id='O7' cannot unlock either O5 or O7
        vi_dual = copy.deepcopy(self.normal_vi)
        vi_dual.update({'last_heartbeat': '2026-01-05T08:00:00Z', 'scheduled_interval': 3600, 'o5_collar': 0.05, 'o5_side': 'short'})
        st_dual = {}
        for _ in range(3):
            _, _, st_dual = self._eval(vi_dual, session='2026-01-05', prior=st_dual)
        vi_rec = copy.deepcopy(self.normal_vi)
        vi_rec.update({'last_heartbeat': '2026-01-06T15:59:30Z', 'scheduled_interval': 3600, 'o5_collar': 0.05})
        r_dual, _, _ = self._eval(
            vi_rec, session='2026-01-06', prior=st_dual,
            events=[{'type': 'rearm', 'row': 'O5', 'row_id': 'O7', 'session': '2026-01-06'}],
        )
        self.assertEqual(r_dual['O5']['state'], 'HALT')
        self.assertEqual(r_dual['O7']['state'], 'NO-NEW-RISK')

        # 3. V1, V2 (mismatch), V3 fund re-arms reject prior-day, undated, wrong-scope, account-scope cards
        vi_f = copy.deepcopy(self.normal_vi)
        vi_f['funds']['TQQQ']['fund_return'] = 0.05
        vi_f['funds']['TQQQ']['corporate_action'] = {'type': 'split', 'ratio': 2.0, 'adjustment_complete': True, 'exact_reconciliation': False}
        vi_f['funds']['TQQQ']['fund_event'] = 'exchange_halt'
        _, _, st_f = self._eval(vi_f, session='2026-01-05')

        for row_id in ('V1', 'V2', 'V3'):
            for bad_ev in (
                {'type': 'rearm', 'row': row_id, 'fund': 'TQQQ', 'session': '2026-01-05'},
                {'type': 'rearm', 'row': row_id, 'fund': 'TQQQ'},
                {'type': 'rearm', 'row': row_id, 'fund': 'TQQQ', 'scope': 'fund:SOXL', 'session': '2026-01-06'},
                {'type': 'rearm', 'row': row_id, 'fund': 'TQQQ', 'scope': 'account', 'session': '2026-01-06'},
                {'type': 'rearm', 'row': row_id, 'row_id': 'V4', 'fund': 'TQQQ', 'session': '2026-01-06'},
            ):
                r_bad, _, _ = self._eval(vi_rec, session='2026-01-06', prior=st_f, events=[bad_ev])
                self.assertTrue(r_bad[row_id]['latched'], f"{row_id} accepted bad card {bad_ev}")

            r_good, _, _ = self._eval(
                vi_rec, session='2026-01-06', prior=st_f,
                events=[{'type': 'rearm', 'row': row_id, 'fund': 'TQQQ', 'scope': 'fund:TQQQ', 'session': '2026-01-06'}],
            )
            self.assertEqual(r_good[row_id]['state'], 'NORMAL')
            self.assertEqual(r_good[row_id]['reason'], 'authorized_rearm')

    def test_r5_o8_kill_switch_latch_persistence_and_clear(self):
        """R5 (B): O8 kill_switch persists in next_row_state['O8'] until explicit Q4 owner clear/rearm."""
        import copy
        vi = copy.deepcopy(self.normal_vi)
        r1, eff1, st1 = self._eval(vi, session='2026-01-05', events=[{'type': 'kill_switch', 'session': '2026-01-05'}])
        self.assertEqual(r1['O8']['state'], 'HALT')
        self.assertEqual(st1['O8'], {'latched': True, 'trip_session': '2026-01-05'})
        self.assertEqual(eff1['account'], 'HALT')

        vi2 = copy.deepcopy(self.normal_vi)
        vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
        r2, eff2, st2 = self._eval(vi2, session='2026-01-06', prior=st1, events=[])
        self.assertEqual(r2['O8']['state'], 'HALT')
        self.assertTrue(r2['O8']['latched'])
        self.assertEqual(r2['O8']['reason'], 'latched_prior_trip')
        self.assertEqual(eff2['account'], 'HALT')
        self.assertEqual(st2['O8'], {'latched': True, 'trip_session': '2026-01-05'})

        # Undated / prior-date / fund-scoped clear must be refused
        for bad_ev in (
            {'type': 'kill_switch_clear'},
            {'type': 'kill_switch_clear', 'session': '2026-01-05'},
            {'type': 'kill_switch_clear', 'session': '2026-01-06', 'scope': 'fund:TQQQ'},
            {'type': 'rearm', 'row': 'O8', 'row_id': 'O6', 'session': '2026-01-06'},
        ):
            r_refuse, _, _ = self._eval(vi2, session='2026-01-06', prior=st2, events=[bad_ev])
            self.assertEqual(r_refuse['O8']['state'], 'HALT')
            self.assertTrue(r_refuse['O8']['latched'])

        r_clr, eff_clr, st_clr = self._eval(
            vi2, session='2026-01-06', prior=st2,
            events=[{'type': 'kill_switch_clear', 'session': '2026-01-06', 'scope': 'account'}],
        )
        self.assertEqual(r_clr['O8']['state'], 'NORMAL')
        self.assertEqual(r_clr['O8']['reason'], 'authorized_rearm')
        self.assertEqual(st_clr['O8'], {})
        self.assertEqual(eff_clr['account'], 'NORMAL')

        # Un-tripped session omits 'O8' from next_row_state
        _, _, st_clean = self._eval(vi, session='2026-01-05')
        self.assertNotIn('O8', st_clean)

    def test_r5_v2_queue_preserved_across_second_ca_mismatch_strict_hwm_and_nan(self):
        """R5 (C): Second CA mismatch keeps pending split, rejects string 'false' hwm_adjusted, sanitizes NaN mismatch."""
        import copy, json

        # 1. Split + distribution -> distribution fails with ledger NaN -> split remains pending even after V2 rearm
        vi1 = copy.deepcopy(self.normal_vi)
        vi1['funds']['TQQQ']['corporate_action'] = {'type': 'split', 'ratio': 2.0, 'adjustment_complete': False, 'exact_reconciliation': False}
        _, _, st1 = self._eval(vi1, session='2026-01-05')

        vi2 = copy.deepcopy(self.normal_vi)
        vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
        vi2['funds']['TQQQ']['corporate_action'] = {'type': 'distribution', 'adjustment_complete': False, 'exact_reconciliation': False}
        _, _, st2 = self._eval(vi2, session='2026-01-06', prior=st1)

        vi3_nan = copy.deepcopy(self.normal_vi)
        vi3_nan['last_heartbeat'] = '2026-01-07T15:59:30Z'
        vi3_nan['funds']['TQQQ']['ledger_value'] = float('nan')
        vi3_nan['funds']['TQQQ']['corporate_action'] = {'type': 'distribution', 'adjustment_complete': True, 'exact_reconciliation': True}
        _, _, st3_nan = self._eval(vi3_nan, session='2026-01-07', prior=st2)
        json.dumps(st3_nan, allow_nan=False)
        self.assertIsNone(st3_nan['V2']['latched_mismatches']['TQQQ']['ledger_value'])

        vi3 = copy.deepcopy(self.normal_vi)
        vi3['last_heartbeat'] = '2026-01-07T15:59:30Z'
        vi3['funds']['TQQQ']['corporate_action'] = {'type': 'distribution', 'adjustment_complete': True, 'exact_reconciliation': False}
        r3, _, st3 = self._eval(vi3, session='2026-01-07', prior=st2)
        self.assertEqual(r3['V2']['state'], 'HALT')
        self.assertEqual(r3['V2']['reason'], 'reconciliation_mismatch')
        self.assertEqual(st3['V2']['pending_adjustments']['TQQQ']['type'], 'split')

        # Step 4: Q4 rearm clears distribution mismatch latch ONLY; split still halts TQQQ!
        vi4 = copy.deepcopy(self.normal_vi)
        vi4['last_heartbeat'] = '2026-01-08T15:59:30Z'
        r4, eff4, st4 = self._eval(
            vi4, session='2026-01-08', prior=st3,
            events=[{'type': 'rearm', 'row': 'V2', 'fund': 'TQQQ', 'session': '2026-01-08'}],
        )
        self.assertEqual(r4['V2']['state'], 'HALT')
        self.assertEqual(r4['V2']['reason'], 'pending_corporate_action_carried_TQQQ')
        self.assertEqual(eff4['fund:TQQQ'], 'HALT')
        self.assertEqual(st4['V2']['pending_adjustments']['TQQQ']['type'], 'split')
        self.assertNotIn('latched_mismatches', st4['V2'])

        # Step 5: Reconciling split clears V2 cleanly; string "false" on hwm_adjusted fails closed
        vi_bad_hwm = copy.deepcopy(self.normal_vi)
        vi_bad_hwm['last_heartbeat'] = '2026-01-09T15:59:30Z'
        vi_bad_hwm['funds']['TQQQ']['corporate_action'] = {'type': 'split', 'ratio': 2.0, 'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': 'false'}
        r_bad_hwm, _, _ = self._eval(vi_bad_hwm, session='2026-01-09', prior=st4)
        self.assertEqual(r_bad_hwm['V2']['state'], 'HALT')
        self.assertTrue(r_bad_hwm['V2']['latched'])

        vi5 = copy.deepcopy(self.normal_vi)
        vi5['last_heartbeat'] = '2026-01-09T15:59:30Z'
        vi5['funds']['TQQQ']['corporate_action'] = {'type': 'split', 'ratio': 2.0, 'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': True}
        r5, eff5, _ = self._eval(vi5, session='2026-01-09', prior=st4)
        self.assertEqual(r5['V2']['state'], 'NORMAL')
        self.assertEqual(eff5['fund:TQQQ'], 'NORMAL')

    def test_r5_o9_live_value_binding_and_card_date_enforcement(self):
        """R5 (D): O9 requires Q4 card dates AND binds card target values to actual live validated_inputs."""
        import copy
        vi = copy.deepcopy(self.normal_vi)
        vi['max_loss_cap'] = 80000.0
        vi['o9_change_descriptors'] = {'param': 'max_loss_cap', 'from': 60000, 'to': 61000}
        card_61k = [{'type': 'parameter_change_card', 'session': '2026-01-05', 'change_descriptors': {'param': 'max_loss_cap', 'from': 60000, 'to': 61000}}]
        r_mismatch, _, _ = self._eval(vi, session='2026-01-05', events=card_61k)
        self.assertEqual(r_mismatch['O9']['state'], 'HALT')
        self.assertEqual(r_mismatch['O9']['reason'], 'unauthorized_change')

        # Undated parameter_change_card & tier_change_card must both reject
        vi_61 = copy.deepcopy(self.normal_vi)
        vi_61['max_loss_cap'] = 61000.0
        vi_61['o9_change_descriptors'] = {'param': 'max_loss_cap', 'from': 60000, 'to': 61000}
        r_undated_p, _, _ = self._eval(
            vi_61, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'change_descriptors': {'param': 'max_loss_cap', 'from': 60000, 'to': 61000}}],
        )
        self.assertEqual(r_undated_p['O9']['state'], 'HALT')

        vi_tc = copy.deepcopy(self.normal_vi)
        vi_tc.update({'tier': 'conservative', 'tier_change_event': {'from': 'balanced', 'to': 'conservative'}})
        r_undated_t, _, _ = self._eval(
            vi_tc, session='2026-01-05',
            events=[{'type': 'tier_change_card', 'from': 'balanced', 'to': 'conservative'}],
        )
        self.assertEqual(r_undated_t['O9']['state'], 'HALT')

        r_ok_p, _, _ = self._eval(vi_61, session='2026-01-05', events=card_61k)
        self.assertEqual(r_ok_p['O9']['state'], 'NORMAL')

    def test_r5_o5_sell_reducing_long_notional_settled_cash_and_whitelists(self):
        """R5 (E): O5 allows reducing sell of held shares, checks max(order_value, qty*unit_price), canonical settled_cash, strict account_whitelist."""
        import copy
        # Genuine reducing sell succeeds even 3x in one session with settled_cash=0
        st = {}
        for _ in range(3):
            vi_sell = copy.deepcopy(self.normal_vi)
            vi_sell.update({'o5_collar': 0.05, 'o5_side': 'sell', 'o5_symbol': 'TQQQ', 'qty': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 0.0, 'account': 'synthetic_account_1'})
            r_sell, eff_sell, st = self._eval(vi_sell, session='2026-01-05', prior=st)
            self.assertFalse(r_sell['O5']['would_have_tripped'])
            self.assertEqual(r_sell['O5']['state'], 'NORMAL')
            self.assertEqual(eff_sell['account'], 'NORMAL')

        # Overselling (>1000 shares) or short rejected
        for bad_kw in ({'o5_side': 'sell', 'o5_symbol': 'TQQQ', 'qty': 1001}, {'o5_side': 'short', 'o5_symbol': 'TQQQ', 'qty': 1}):
            vi_bad = copy.deepcopy(self.normal_vi)
            vi_bad.update({'o5_collar': 0.05, **bad_kw})
            self.assertTrue(self._eval(vi_bad)[0]['O5']['would_have_tripped'])

        # qty * unit_price beats deceptive o5_order_value=0 when settled_cash=0
        vi_notional = copy.deepcopy(self.normal_vi)
        vi_notional.update({'o5_collar': 0.05, 'o5_side': 'buy', 'o5_order_value': 0.0, 'qty': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 0.0})
        self.assertTrue(self._eval(vi_notional)[0]['O5']['would_have_tripped'])

        # Canonical settled_cash=200 wins over alias o5_settled_cash=0
        vi_sc_win = copy.deepcopy(self.normal_vi)
        vi_sc_win.update({'o5_collar': 0.05, 'o5_side': 'buy', 'o5_symbol': 'TQQQ', 'settled_cash': 200.0, 'o5_settled_cash': 0.0, 'o5_order_value': 100.0, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'account': 'synthetic_account_1'})
        self.assertFalse(self._eval(vi_sc_win)[0]['O5']['would_have_tripped'])

        # account_whitelist=None or unapproved account masked by o5_account must both fail
        vi_wl_none = copy.deepcopy(self.normal_vi)
        vi_wl_none.update({'o5_collar': 0.05, 'account_whitelist': None, 'account': 'rogue'})
        self.assertTrue(self._eval(vi_wl_none)[0]['O5']['would_have_tripped'])

        vi_mask = copy.deepcopy(self.normal_vi)
        vi_mask.update({'o5_collar': 0.05, 'account': 'rogue', 'o5_account': 'synthetic_account_1'})
        self.assertTrue(self._eval(vi_mask)[0]['O5']['would_have_tripped'])

    def test_r5_remaining_row_and_null_hardening(self):
        """R5 (F): L0/L1/L2 NaN/bool, L3 day-10 counter, L6 {} / 1-index, O3 empty funds, O4 null/malformed BIL, O6 blank, V4 hi-vol holiday & 2nd-fund outputs, V5 omitted escalated & None shortfall, V7 non-bool pause."""
        import copy

        # L0 bool & L1/L2 NaN bankroll fail closed
        vi_l0 = copy.deepcopy(self.normal_vi)
        vi_l0['proposed_exposure'] = True
        r_l0 = self._eval(vi_l0)[0]['L0']
        self.assertTrue(r_l0['would_have_tripped'])
        self.assertEqual(r_l0['reason'], 'missing_input')

        vi_nan_bk = copy.deepcopy(self.normal_vi)
        vi_nan_bk['bankroll'] = float('nan')
        r_nan_bk, _, _ = self._eval(vi_nan_bk)
        self.assertTrue(r_nan_bk['L1']['would_have_tripped'])
        self.assertEqual(r_nan_bk['L2']['state'], 'NO-NEW-RISK')

        # L3 day-10 without card computes 20 remaining days dynamically
        vi_l3 = copy.deepcopy(self.normal_vi)
        vi_l3['bankroll'] = 60000.0
        _, _, st_l3 = self._eval(vi_l3, session='2026-01-05')
        r_d10 = self._eval(copy.deepcopy(self.normal_vi), session='2026-01-15', prior=st_l3)[0]['L3']
        self.assertEqual(r_d10['outputs']['cooling_off_days_remaining'], 20)

        # L6 empty {} & 1-index dict fail closed HALT
        for bad_idx in ({}, {'SPX': 0.01}):
            vi_l6 = copy.deepcopy(self.normal_vi)
            vi_l6['index_one_session_returns'] = bad_idx
            self.assertEqual(self._eval(vi_l6)[0]['L6']['state'], 'HALT')

        # O3 empty funds fails closed so L6 cannot be cleared without positions
        vi_l6_trip = copy.deepcopy(self.normal_vi)
        vi_l6_trip['market_halt_level'] = 3
        _, _, st_l6 = self._eval(vi_l6_trip, session='2026-01-05')
        vi_empty_funds = copy.deepcopy(self.normal_vi)
        vi_empty_funds.update({'funds': {}, 'last_heartbeat': '2026-01-06T15:59:30Z'})
        r_l6_no_pos, _, _ = self._eval(
            vi_empty_funds, session='2026-01-06', prior=st_l6,
            events=[{'type': 'rearm', 'row_id': 'L6', 'session': '2026-01-06'}],
        )
        self.assertEqual(r_l6_no_pos['O3']['state'], 'HALT')
        self.assertEqual(r_l6_no_pos['L6']['state'], 'HALT')

        # Public evaluate() handles funds=None & pending_orders=None without AttributeError
        vi_nulls = copy.deepcopy(self.normal_vi)
        vi_nulls['funds'] = None
        vi_nulls['pending_orders'] = None
        rows_null, _, _ = self._eval(vi_nulls)
        self.assertEqual(len(rows_null), 24)

        # O4 preserves BIL lock across malformed pending_orders & unidentified initial timeout
        vi_bil = copy.deepcopy(self.normal_vi)
        vi_bil['pending_orders'] = {'BIL': {'order_id': 'ord_b1', 'status': 'pending', 'timeout': True}}
        _, _, st_bil1 = self._eval(vi_bil, session='2026-01-05')
        vi_bil_bad = copy.deepcopy(self.normal_vi)
        vi_bil_bad['pending_orders'] = {'BIL': 'malformed_payload'}
        r_b2, eff_b2, st_b2 = self._eval(vi_bil_bad, session='2026-01-06', prior=st_bil1)
        self.assertEqual(r_b2['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(eff_b2['symbol:BIL'], 'ORDER-UNKNOWN')
        self.assertEqual(st_b2['O4']['BIL']['original_order_id'], 'ord_b1')
        vi_bil_empty = copy.deepcopy(self.normal_vi)
        r_b3, eff_b3, _ = self._eval(vi_bil_empty, session='2026-01-07', prior=st_b2)
        self.assertEqual(eff_b3['symbol:BIL'], 'ORDER-UNKNOWN')

        vi_noid = copy.deepcopy(self.normal_vi)
        vi_noid['pending_orders'] = {'BIL': {'status': 'pending', 'timeout': True}}
        _, _, st_noid1 = self._eval(vi_noid, session='2026-01-05')
        _, eff_noid2, _ = self._eval(copy.deepcopy(self.normal_vi), session='2026-01-06', prior=st_noid1)
        self.assertEqual(eff_noid2['symbol:BIL'], 'ORDER-UNKNOWN')

        # O6 blank policy hashes fail closed
        vi_o6 = copy.deepcopy(self.normal_vi)
        vi_o6.update({'loaded_policy_hash': '', 'registered_policy_hash': ''})
        self.assertEqual(self._eval(vi_o6)[0]['O6']['state'], 'HALT')

        # V4 high-vol on holiday keeps counter=9; 2nd-fund SOXL-only V4 still emits outputs
        vi_hol_hi = copy.deepcopy(self.normal_vi)
        vi_hol_hi.update({'session_calendar_status': 'holiday', 'exchange_status': 'closed'})
        vi_hol_hi['funds']['TQQQ']['forecast_volatility'] = 0.90
        r_v4_hol, _, st_v4_hol = self._eval(vi_hol_hi, session='2026-01-19', prior={'V4': {'TQQQ': {'clearing_counter': 9, 'last_session_below_threshold': '2026-01-16'}}})
        self.assertEqual(st_v4_hol['V4']['TQQQ']['clearing_counter'], 9)

        vi_soxl_v4 = copy.deepcopy(self.normal_vi)
        vi_soxl_v4['funds']['SOXL']['forecast_volatility'] = 0.60
        r_soxl_v4 = self._eval(vi_soxl_v4)[0]['V4']
        self.assertIn('outputs', r_soxl_v4)
        self.assertEqual(r_soxl_v4['outputs']['SOXL']['clearing_counter'], 0)

        # V5 omitted escalated SOXL keeps fund:SOXL NO-NEW-RISK; missing shortfall returns None
        vi_v5_miss = copy.deepcopy(self.normal_vi)
        vi_v5_miss['funds'] = {'TQQQ': {**copy.deepcopy(self.normal_vi['funds']['TQQQ']), 'v5_tolerance': 0.01}}
        vi_v5_miss['funds']['TQQQ'].pop('shortfall_observed')
        r_v5_miss = self._eval(vi_v5_miss)[0]['V5']
        self.assertIsNone(r_v5_miss['outputs']['excess_shortfall'])

        vi_only_tqqq = copy.deepcopy(self.normal_vi)
        vi_only_tqqq['funds'] = {'TQQQ': copy.deepcopy(self.normal_vi['funds']['TQQQ'])}
        prior_v5_esc = {'V5': {'SOXL': {'consecutive_beyond_tolerance': 40, 'escalated': True, 'last_session': '2026-01-05'}}}
        r_v5_esc, eff_v5_esc, _ = self._eval(vi_only_tqqq, session='2026-01-06', prior=prior_v5_esc)
        self.assertEqual(r_v5_esc['V5']['state'], 'NO-NEW-RISK')
        self.assertEqual(eff_v5_esc['fund:SOXL'], 'NO-NEW-RISK')

        # V7 omitted/non-bool trading_pause fails closed
        vi_v7_tp = copy.deepcopy(self.normal_vi)
        vi_v7_tp['v7_spread_width'] = 0.02
        vi_v7_tp['funds']['TQQQ'].pop('trading_pause')
        r_v7_tp = self._eval(vi_v7_tp)[0]['V7']
        self.assertTrue(r_v7_tp['would_have_tripped'])
        self.assertEqual(r_v7_tp['reason'], 'missing_input')

    def test_r6_o5_order_size_and_null_account_fail_closed(self):
        """R6 P1-1: O5 resolves order_size uniformly for buy/sell and fails closed on null account/whitelist."""
        vi_buy = copy.deepcopy(self.normal_vi)
        vi_buy.update({
            'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
            'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 0.0,
        })
        r_buy, _, _ = self._eval(vi_buy)
        self.assertTrue(r_buy['O5']['would_have_tripped'])
        self.assertEqual(r_buy['O5']['reason'], 'pre_trade_limit_violation')

        # Reducing sell via spec-canonical order_size succeeds 3x without HALT
        st_sell = {}
        for _ in range(3):
            vi_sell = copy.deepcopy(self.normal_vi)
            vi_sell.update({
                'o5_collar': 0.05, 'side': 'sell', 'symbol': 'TQQQ',
                'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 0.0,
                'account': 'synthetic_account_1',
            })
            r_sell, eff_sell, st_sell = self._eval(vi_sell, session='2026-01-05', prior=st_sell)
            self.assertFalse(r_sell['O5']['would_have_tripped'])
            self.assertEqual(r_sell['O5']['state'], 'NORMAL')
            self.assertEqual(eff_sell['account'], 'NORMAL')

        # Explicit buy with account=None and account_whitelist=None (and account=None alone) must fail closed
        for extra in ({'account': None, 'account_whitelist': None}, {'account': None}):
            vi_null = copy.deepcopy(self.normal_vi)
            vi_null.update({
                'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
                'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 1000.0,
                **extra,
            })
            r_null, _, _ = self._eval(vi_null)
            self.assertTrue(r_null['O5']['would_have_tripped'])
            self.assertEqual(r_null['O5']['reason'], 'pre_trade_limit_violation')

    def test_r6_v2_enqueues_distinct_ca_during_active_mismatch_latch(self):
        """R6 P1-2: Announcing split while distribution mismatch is latched preserves split across distribution rearm."""
        vi1 = copy.deepcopy(self.normal_vi)
        vi1['funds']['TQQQ']['corporate_action'] = {
            'type': 'distribution', 'adjustment_complete': True, 'exact_reconciliation': False,
        }
        r1, _, st1 = self._eval(vi1, session='2026-01-05')
        self.assertEqual(r1['V2']['reason'], 'reconciliation_mismatch')

        # Step 2: while distribution mismatch is latched, split is announced without rearm -> enqueued!
        vi2 = copy.deepcopy(self.normal_vi)
        vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
        vi2['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2.0, 'adjustment_complete': False, 'exact_reconciliation': False,
        }
        r2, _, st2 = self._eval(vi2, session='2026-01-06', prior=st1)
        self.assertEqual(r2['V2']['reason'], 'latched_prior_mismatch')
        self.assertIn('latched_mismatches', st2['V2'])
        self.assertEqual(st2['V2']['pending_adjustments']['TQQQ']['type'], 'split')

        # Step 3: Q4 rearm clears distribution mismatch ONLY; carried split keeps fund:TQQQ HALT until reconciled
        vi3 = copy.deepcopy(self.normal_vi)
        vi3['last_heartbeat'] = '2026-01-07T15:59:30Z'
        r3, eff3, st3 = self._eval(
            vi3, session='2026-01-07', prior=st2,
            events=[{'type': 'rearm', 'row': 'V2', 'fund': 'TQQQ', 'session': '2026-01-07'}],
        )
        self.assertEqual(r3['V2']['state'], 'HALT')
        self.assertEqual(r3['V2']['reason'], 'pending_corporate_action_carried_TQQQ')
        self.assertEqual(eff3['fund:TQQQ'], 'HALT')
        self.assertNotIn('latched_mismatches', st3['V2'])
        self.assertEqual(st3['V2']['pending_adjustments']['TQQQ']['type'], 'split')

        # Step 4: Exact reconciliation for split clears V2 cleanly
        vi4 = copy.deepcopy(self.normal_vi)
        vi4['last_heartbeat'] = '2026-01-08T15:59:30Z'
        vi4['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2.0, 'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': True,
        }
        r4, eff4, st4 = self._eval(vi4, session='2026-01-08', prior=st3)
        self.assertEqual(r4['V2']['state'], 'NORMAL')
        self.assertEqual(eff4['fund:TQQQ'], 'NORMAL')
        self.assertEqual(st4.get('V2', {}), {})

    def test_r6_v2_explicit_null_hwm_adjusted_fails_closed(self):
        """R6 P1-3: Explicit hwm_adjusted=None in corporate_action or inputs must fail reconciliation -> HALT."""
        vi1 = copy.deepcopy(self.normal_vi)
        vi1['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2.0, 'adjustment_complete': False, 'exact_reconciliation': False,
        }
        _, _, st1 = self._eval(vi1, session='2026-01-05')

        for loc in ('ca', 'fund', 'top'):
            vi2 = copy.deepcopy(self.normal_vi)
            vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
            vi2['funds']['TQQQ']['corporate_action'] = {
                'type': 'split', 'ratio': 2.0, 'adjustment_complete': True, 'exact_reconciliation': True,
            }
            if loc == 'ca':
                vi2['funds']['TQQQ']['corporate_action']['hwm_adjusted'] = None
            elif loc == 'fund':
                vi2['funds']['TQQQ']['hwm_adjusted'] = None
            else:
                vi2['hwm_adjusted'] = None
            r2, eff2, _ = self._eval(vi2, session='2026-01-06', prior=st1)
            self.assertEqual(r2['V2']['state'], 'HALT')
            self.assertTrue(r2['V2']['latched'])
            self.assertEqual(r2['V2']['reason'], 'reconciliation_mismatch')
            self.assertEqual(eff2['fund:TQQQ'], 'HALT')

    def test_r6_o9_requires_target_checks_fund_scope_and_rejects_conflicting_row(self):
        """R6 P1-4: O9 rejects missing target, checks fund-level overrides against V7 runtime values, and rejects row!=row_id."""
        # 1. Missing target value ('from' only) fails closed even if card repeats it
        vi_notarget = copy.deepcopy(self.normal_vi)
        vi_notarget.update({'max_loss_cap': 80000.0, 'o9_change_descriptors': {'param': 'max_loss_cap', 'from': 60000}})
        r_nt, _, _ = self._eval(
            vi_notarget, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'change_descriptors': {'param': 'max_loss_cap', 'from': 60000}}],
        )
        self.assertEqual(r_nt['O9']['state'], 'HALT')
        self.assertEqual(r_nt['O9']['reason'], 'unauthorized_change')

        # 2. Fund-targeted card (v7_spread_width=0.02 for TQQQ) fails when funds['TQQQ']['v7_spread_width'] is silently 0.20
        vi_fund_ovr = copy.deepcopy(self.normal_vi)
        vi_fund_ovr['v7_spread_width'] = 0.02
        vi_fund_ovr['funds']['TQQQ']['v7_spread_width'] = 0.20
        vi_fund_ovr['funds']['TQQQ']['spread_width'] = 0.10
        vi_fund_ovr['o9_change_descriptors'] = {'param': 'v7_spread_width', 'fund': 'TQQQ', 'from': 0.01, 'to': 0.02}
        r_fo, _, _ = self._eval(
            vi_fund_ovr, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'fund': 'TQQQ', 'change_descriptors': {'param': 'v7_spread_width', 'fund': 'TQQQ', 'from': 0.01, 'to': 0.02}}],
        )
        self.assertEqual(r_fo['O9']['state'], 'HALT')

        # Account-level v7_spread_width=0.02 card must also fail if any fund overrides to 0.20
        vi_acct_ovr = copy.deepcopy(vi_fund_ovr)
        vi_acct_ovr['o9_change_descriptors'] = {'param': 'v7_spread_width', 'from': 0.01, 'to': 0.02}
        r_ao, _, _ = self._eval(
            vi_acct_ovr, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'change_descriptors': {'param': 'v7_spread_width', 'from': 0.01, 'to': 0.02}}],
        )
        self.assertEqual(r_ao['O9']['state'], 'HALT')

        # Exact fund-level match passes cleanly
        vi_fund_ok = copy.deepcopy(vi_fund_ovr)
        vi_fund_ok['funds']['TQQQ']['v7_spread_width'] = 0.02
        vi_fund_ok['funds']['TQQQ']['spread_width'] = 0.01
        r_ok, _, _ = self._eval(
            vi_fund_ok, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'fund': 'TQQQ', 'change_descriptors': {'param': 'v7_spread_width', 'from': 0.01, 'to': 0.02}}],
        )
        self.assertEqual(r_ok['O9']['state'], 'NORMAL')

        # 3. Conflicting row='O5', row_id='O7' on parameter_change_card / tier_change_card fails closed
        vi_conflict = copy.deepcopy(self.normal_vi)
        vi_conflict.update({'max_loss_cap': 80000.0, 'o9_change_descriptors': {'param': 'max_loss_cap', 'from': 60000, 'to': 80000}})
        r_cf, _, _ = self._eval(
            vi_conflict, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'row': 'O5', 'row_id': 'O7', 'session': '2026-01-05', 'change_descriptors': {'param': 'max_loss_cap', 'from': 60000, 'to': 80000}}],
        )
        self.assertEqual(r_cf['O9']['state'], 'HALT')

    def test_r6_o1_blocks_open_market_missing_index_returns_and_clamps_exposure(self):
        """R6 P1-5: Open-market index_one_session_returns=None triggers O1 NO-NEW-RISK & blocks exposure raise, preserving holiday O1 NORMAL."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        vi_open = copy.deepcopy(self.normal_vi)
        vi_open.update({'index_one_session_returns': None, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi_open['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_open['funds']['SOXL']['v5_tolerance'] = 0.01
        rows, eff, _ = self._eval(vi_open, session='2026-01-05')
        self.assertEqual(rows['O1']['state'], 'NO-NEW-RISK')
        self.assertEqual(rows['O1']['reason'], 'stale_or_missing_input')
        self.assertEqual(rows['L6']['state'], 'NORMAL')
        self.assertEqual(eff['account'], 'NO-NEW-RISK')
        self.assertEqual(compute_permitted_exposure(vi_open, rows, eff), 45000.0)

        # Holiday / closed sessions with index_one_session_returns=None preserve O1 == NORMAL
        vi_hol = copy.deepcopy(self.normal_vi)
        vi_hol.update({'session_calendar_status': 'holiday', 'exchange_status': 'closed', 'index_one_session_returns': None})
        rows_hol, _, _ = self._eval(vi_hol, session='2026-01-19')
        self.assertEqual(rows_hol['O1']['state'], 'NORMAL')

    def test_r6_v5_preserves_40_session_escalation_on_missing_shortfall_or_tolerance(self):
        """R6 P1-6: Active 40-session V5 escalation stays NO-NEW-RISK & keeps counter=40 on missing shortfall/tolerance."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        prior_esc = {'V5': {'TQQQ': {'consecutive_beyond_tolerance': 40, 'escalated': True, 'last_session': '2026-01-05'}}}
        for miss_kw in ({'shortfall_observed': None, 'v5_tolerance': 0.01}, {'shortfall_observed': 0.01, 'v5_tolerance': None}):
            vi = copy.deepcopy(self.normal_vi)
            vi.update({'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, 'o5_collar': 0.05, 'symbol': 'TQQQ'})
            vi['funds']['TQQQ'].update(miss_kw)
            vi['funds']['SOXL']['v5_tolerance'] = 0.01
            rows, eff, st = self._eval(vi, session='2026-01-06', prior=prior_esc)
            self.assertEqual(rows['V5']['state'], 'NO-NEW-RISK')
            self.assertTrue(rows['V5']['would_have_tripped'])
            self.assertEqual(rows['V5']['reason'], 'escalated_to_v1_treatment')
            self.assertIsNone(rows['V5']['outputs']['excess_shortfall'])
            self.assertEqual(rows['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 40)
            self.assertTrue(rows['V5']['outputs']['escalated_to_v1'])
            self.assertEqual(rows['V5']['outputs']['disposition'], 'escalated_to_v1')
            self.assertEqual(eff['fund:TQQQ'], 'NO-NEW-RISK')
            self.assertTrue(st['V5']['TQQQ']['escalated'])
            self.assertEqual(st['V5']['TQQQ']['consecutive_beyond_tolerance'], 40)
            self.assertEqual(compute_permitted_exposure(vi, rows, eff), 45000.0)

    def test_r7_o5_conflicting_qty_unbounded_buy_and_empty_whitelist(self):
        """R7 #1-#3: O5 rejects conflicting qty aliases, unbounded buys missing price/value, and empty account_whitelist=[]."""
        # 1. Conflicting qty aliases (order_size vs o5_order_size) fail closed for both buy & sell
        for kw in (
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 2, 'o5_order_size': 0, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 0.0},
            {'side': 'sell', 'symbol': 'TQQQ', 'order_size': 1001, 'o5_order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 0.0},
        ):
            vi = copy.deepcopy(self.normal_vi)
            vi.update({'o5_collar': 0.05, **kw})
            r, _, _ = self._eval(vi)
            self.assertTrue(r['O5']['would_have_tripped'], f"Expected O5 reject for conflicting qty {kw}")

        # 2. Explicit buy missing price & order_value fails closed even with settled_cash=0 or positive cash
        for sc_val in (0.0, 200.0):
            vi_unb = copy.deepcopy(self.normal_vi)
            vi_unb.update({'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ', 'order_size': 2, 'settled_cash': sc_val})
            r_unb, _, _ = self._eval(vi_unb)
            self.assertTrue(r_unb['O5']['would_have_tripped'])

        # 3. Empty account_whitelist=[] fails closed on explicit buy when account is omitted
        vi_empty_wl = copy.deepcopy(self.normal_vi)
        vi_empty_wl.update({
            'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
            'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0,
            'settled_cash': 200.0, 'account_whitelist': [],
        })
        r_ewl, _, _ = self._eval(vi_empty_wl)
        self.assertTrue(r_ewl['O5']['would_have_tripped'])
        self.assertEqual(r_ewl['O5']['reason'], 'pre_trade_limit_violation')

    def test_r7_v2_enqueues_same_type_different_details_and_no_hwm_masking(self):
        """R7 #4-#5: Same-type split(ratio=3) during split(ratio=2) mismatch survives rearm; fund hwm_adjusted=True never masks invalid top-level."""
        # 4. Split(ratio=2) mismatch -> Split(ratio=3) while latched -> rearm keeps HALT
        vi1 = copy.deepcopy(self.normal_vi)
        vi1['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2, 'adjustment_complete': True, 'exact_reconciliation': False,
        }
        _, _, st1 = self._eval(vi1, session='2026-01-05')

        vi2 = copy.deepcopy(self.normal_vi)
        vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
        vi2['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 3, 'adjustment_complete': True, 'exact_reconciliation': False,
        }
        r2, _, st2 = self._eval(vi2, session='2026-01-06', prior=st1)
        self.assertEqual(r2['V2']['reason'], 'latched_prior_mismatch')
        self.assertEqual(st2['V2']['pending_adjustments']['TQQQ']['ratio'], 3)

        vi3 = copy.deepcopy(self.normal_vi)
        vi3['last_heartbeat'] = '2026-01-07T15:59:30Z'
        r3, eff3, st3 = self._eval(
            vi3, session='2026-01-07', prior=st2,
            events=[{'type': 'rearm', 'row': 'V2', 'fund': 'TQQQ', 'session': '2026-01-07'}],
        )
        self.assertEqual(r3['V2']['state'], 'HALT')
        self.assertEqual(eff3['fund:TQQQ'], 'HALT')
        self.assertEqual(st3['V2']['pending_adjustments']['TQQQ']['ratio'], 3)

        # Ratio 2 cannot clear pending ratio 3; ratio 3 clears
        vi_wrong = copy.deepcopy(self.normal_vi)
        vi_wrong['last_heartbeat'] = '2026-01-08T15:59:30Z'
        vi_wrong['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2, 'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': True,
        }
        self.assertEqual(self._eval(vi_wrong, session='2026-01-08', prior=st3)[0]['V2']['state'], 'HALT')

        vi_right = copy.deepcopy(vi_wrong)
        vi_right['funds']['TQQQ']['corporate_action']['ratio'] = 3
        self.assertEqual(self._eval(vi_right, session='2026-01-08', prior=st3)[0]['V2']['state'], 'NORMAL')

        # 5. Top-level invalid hwm_adjusted is never masked by fund/CA hwm_adjusted=True
        _, _, st_pend = self._eval(
            {
                **copy.deepcopy(self.normal_vi),
                'funds': {
                    **copy.deepcopy(self.normal_vi['funds']),
                    'TQQQ': {
                        **copy.deepcopy(self.normal_vi['funds']['TQQQ']),
                        'corporate_action': {'type': 'split', 'ratio': 2.0, 'adjustment_complete': False, 'exact_reconciliation': False},
                    },
                },
            },
            session='2026-01-05',
        )
        for bad_top in (None, False, 'false', 1):
            vi_mask = copy.deepcopy(self.normal_vi)
            vi_mask['last_heartbeat'] = '2026-01-06T15:59:30Z'
            vi_mask['hwm_adjusted'] = bad_top
            vi_mask['funds']['TQQQ']['hwm_adjusted'] = True
            vi_mask['funds']['TQQQ']['corporate_action'] = {
                'type': 'split', 'ratio': 2.0, 'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': True,
            }
            r_m, eff_m, _ = self._eval(vi_mask, session='2026-01-06', prior=st_pend)
            self.assertEqual(r_m['V2']['state'], 'HALT')
            self.assertEqual(r_m['V2']['reason'], 'reconciliation_mismatch')
            self.assertEqual(eff_m['fund:TQQQ'], 'HALT')

    def test_r7_o9_tier_target_required_and_consumer_scope_binding(self):
        """R7 #6-#7: O9 requires target tier on tier changes, rejects TQQQ reconciliation_tolerance spoof vs O3, and requires all funds for account-level overrides."""
        # 6. Tier change missing target tier ('from' only) fails closed
        vi_t = copy.deepcopy(self.normal_vi)
        vi_t.update({'tier': 'aggressive', 'tier_change_event': {'from': 'balanced'}})
        r_t, _, _ = self._eval(
            vi_t, session='2026-01-05',
            events=[{'type': 'tier_change_card', 'from': 'balanced', 'session': '2026-01-05'}],
        )
        self.assertEqual(r_t['O9']['state'], 'HALT')
        self.assertEqual(r_t['O9']['reason'], 'unauthorized_change')

        # 7a. TQQQ-scoped card claiming reconciliation_tolerance=1 while top-level O3 tolerance=1000 fails closed
        vi_rec = copy.deepcopy(self.normal_vi)
        vi_rec['reconciliation_tolerance'] = 1000
        vi_rec['funds']['TQQQ']['reconciliation_tolerance'] = 1
        vi_rec['funds']['TQQQ']['ledger_value'] = 25500.0
        vi_rec['funds']['TQQQ']['broker_value'] = 25000.0
        vi_rec['o9_change_descriptors'] = {'param': 'reconciliation_tolerance', 'fund': 'TQQQ', 'from': 0, 'to': 1}
        r_rec, _, _ = self._eval(
            vi_rec, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'fund': 'TQQQ', 'change_descriptors': {'param': 'reconciliation_tolerance', 'fund': 'TQQQ', 'from': 0, 'to': 1}}],
        )
        self.assertEqual(r_rec['O9']['state'], 'HALT')

        # 7b. Account-level v5_tolerance=0.01 rejects when only TQQQ has it and SOXL/top-level omit it
        vi_part = copy.deepcopy(self.normal_vi)
        vi_part.pop('v5_tolerance', None)
        vi_part['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_part['o9_change_descriptors'] = {'param': 'v5_tolerance', 'from': 0.005, 'to': 0.01}
        r_part, _, _ = self._eval(
            vi_part, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'change_descriptors': {'param': 'v5_tolerance', 'from': 0.005, 'to': 0.01}}],
        )
        self.assertEqual(r_part['O9']['state'], 'HALT')

        # Passes cleanly when applied to top-level (or all funds)
        vi_full = copy.deepcopy(vi_part)
        vi_full['v5_tolerance'] = 0.01
        self.assertEqual(
            self._eval(
                vi_full, session='2026-01-05',
                events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'change_descriptors': {'param': 'v5_tolerance', 'from': 0.005, 'to': 0.01}}],
            )[0]['O9']['state'],
            'NORMAL',
        )

    def test_r7_o1_contradictory_market_closed_still_blocks_missing_index_returns(self):
        """R7 #8: market_closed=True cannot suppress O1 open-market index_one_session_returns=None guard."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        for cal_key in ('session_calendar_status', 'calendar_state'):
            vi = copy.deepcopy(self.normal_vi)
            vi.update({
                cal_key: 'open', 'exchange_status': 'open', 'market_closed': True,
                'index_one_session_returns': None, 'proposed_exposure': 50000.0,
                'v7_spread_width': 0.02, 'o5_collar': 0.05,
            })
            vi['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi['funds']['SOXL']['v5_tolerance'] = 0.01
            rows, eff, _ = self._eval(vi, session='2026-01-05')
            self.assertEqual(rows['O1']['state'], 'NO-NEW-RISK')
            self.assertEqual(rows['O1']['reason'], 'stale_or_missing_input')
            self.assertEqual(eff['account'], 'NO-NEW-RISK')
            self.assertEqual(compute_permitted_exposure(vi, rows, eff), 45000.0)

    def test_r8_o5_rearm_plus_bad_order_and_side_conflict_and_zero_order_value(self):
        """R8 #1-#2: O5 Q4 rearm still evaluates same-session orders; rejects conflicting side aliases & order_value=0 on order_size>0 buy."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        # Latch O5 with 3 violations
        vi_trip = copy.deepcopy(self.normal_vi)
        vi_trip.update({'o5_collar': 0.05, 'side': 'short'})
        st_o5 = {}
        for _ in range(3):
            _, _, st_o5 = self._eval(vi_trip, session='2026-01-05', prior=st_o5)
        self.assertTrue(st_o5['O5']['latched'])

        # 1. Rearm + same-session bad order (qty conflict, unbounded buy, empty whitelist) still trips O5 & clamps exposure
        rearm_ev = [{'type': 'rearm', 'row_id': 'O5', 'session': '2026-01-06', 'scope': 'account'}]
        for bad_kw in (
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 2, 'o5_order_size': 0, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 0.0},
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 2, 'settled_cash': 0.0},
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 200.0, 'account_whitelist': []},
        ):
            vi_r = copy.deepcopy(self.normal_vi)
            vi_r.update({'last_heartbeat': '2026-01-06T15:59:30Z', 'o5_collar': 0.05, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, **bad_kw})
            vi_r['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi_r['funds']['SOXL']['v5_tolerance'] = 0.01
            r, eff, _ = self._eval(vi_r, session='2026-01-06', prior=st_o5, events=rearm_ev)
            self.assertTrue(r['O5']['would_have_tripped'])
            self.assertEqual(r['O5']['rejection_count_this_session'], 1)
            self.assertEqual(compute_permitted_exposure(vi_r, r, eff), 45000.0)

        # 2a. Conflicting side='buy' + o5_side='sell' cannot skip settled_cash check
        vi_sc = copy.deepcopy(self.normal_vi)
        vi_sc.update({
            'o5_collar': 0.05, 'side': 'buy', 'o5_side': 'sell', 'symbol': 'TQQQ',
            'order_size': 2, 'settled_cash': 0.0, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02,
        })
        vi_sc['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_sc['funds']['SOXL']['v5_tolerance'] = 0.01
        r_sc, eff_sc, _ = self._eval(vi_sc)
        self.assertTrue(r_sc['O5']['would_have_tripped'])
        self.assertEqual(compute_permitted_exposure(vi_sc, r_sc, eff_sc), 45000.0)

        # 2b. Explicit buy with order_size>0 and deceptive order_value=0 fails closed
        vi_zov = copy.deepcopy(self.normal_vi)
        vi_zov.update({
            'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
            'order_size': 2, 'order_value': 0, 'settled_cash': 0.0,
            'proposed_exposure': 50000.0, 'v7_spread_width': 0.02,
        })
        vi_zov['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_zov['funds']['SOXL']['v5_tolerance'] = 0.01
        r_zov, eff_zov, _ = self._eval(vi_zov)
        self.assertTrue(r_zov['O5']['would_have_tripped'])
        self.assertEqual(compute_permitted_exposure(vi_zov, r_zov, eff_zov), 45000.0)

    def test_r8_v2_replay_mismatch_preserves_queue_and_distinguishes_effective_date(self):
        """R8 #3: Replaying split(ratio=2) mismatch does not clear queued split(ratio=3); different effective_date splits stay isolated."""
        # Case A: ratio=2 mismatch -> ratio=3 queued -> rearm -> replay ratio=2 mismatch -> rearm stays HALT!
        vi1 = copy.deepcopy(self.normal_vi)
        vi1['funds']['TQQQ']['corporate_action'] = {'type': 'split', 'ratio': 2, 'adjustment_complete': True, 'exact_reconciliation': False}
        _, _, st1 = self._eval(vi1, session='2026-01-05')

        vi2 = copy.deepcopy(self.normal_vi)
        vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
        vi2['funds']['TQQQ']['corporate_action'] = {'type': 'split', 'ratio': 3, 'adjustment_complete': True, 'exact_reconciliation': False}
        _, _, st2 = self._eval(vi2, session='2026-01-06', prior=st1)

        vi3 = copy.deepcopy(self.normal_vi)
        vi3['last_heartbeat'] = '2026-01-07T15:59:30Z'
        _, _, st3 = self._eval(vi3, session='2026-01-07', prior=st2, events=[{'type': 'rearm', 'row': 'V2', 'fund': 'TQQQ', 'session': '2026-01-07'}])
        self.assertEqual(st3['V2']['pending_adjustments']['TQQQ']['ratio'], 3)

        vi4 = copy.deepcopy(self.normal_vi)
        vi4['last_heartbeat'] = '2026-01-08T15:59:30Z'
        vi4['funds']['TQQQ']['corporate_action'] = {'type': 'split', 'ratio': 2, 'adjustment_complete': True, 'exact_reconciliation': False}
        r4, _, st4 = self._eval(vi4, session='2026-01-08', prior=st3)
        self.assertEqual(r4['V2']['state'], 'HALT')
        self.assertEqual(st4['V2']['pending_adjustments']['TQQQ']['ratio'], 3)

        vi5 = copy.deepcopy(self.normal_vi)
        vi5['last_heartbeat'] = '2026-01-09T15:59:30Z'
        r5, eff5, st5 = self._eval(vi5, session='2026-01-09', prior=st4, events=[{'type': 'rearm', 'row': 'V2', 'fund': 'TQQQ', 'session': '2026-01-09'}])
        self.assertEqual(r5['V2']['state'], 'HALT')
        self.assertEqual(eff5['fund:TQQQ'], 'HALT')
        self.assertEqual(st5['V2']['pending_adjustments']['TQQQ']['ratio'], 3)

        # Case B: Two splits with same ratio=2 but different effective_date cannot cross-clear
        vi_ed1 = copy.deepcopy(self.normal_vi)
        vi_ed1['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2, 'effective_date': '2026-01-08', 'adjustment_complete': False, 'exact_reconciliation': False,
        }
        _, _, st_ed1 = self._eval(vi_ed1, session='2026-01-05')

        vi_ed_old = copy.deepcopy(self.normal_vi)
        vi_ed_old['last_heartbeat'] = '2026-01-06T15:59:30Z'
        vi_ed_old['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2, 'effective_date': '2026-01-05', 'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': True,
        }
        r_ed, eff_ed, st_ed2 = self._eval(vi_ed_old, session='2026-01-06', prior=st_ed1)
        self.assertEqual(r_ed['V2']['state'], 'HALT')
        self.assertEqual(eff_ed['fund:TQQQ'], 'HALT')
        self.assertIn('pending_adjustments', st_ed2['V2'])

    def test_r8_o9_rearm_plus_unauthorized_change_and_no_limits_masking(self):
        """R8 #4-#5: O9 Q4 rearm still evaluates same-session changes; limits dict cannot mask missing consumer inputs."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        # 4. O9 HALT -> Q4 rearm + unauthorized {from: balanced} tier change -> HALT (0 exposure)
        vi_trip = copy.deepcopy(self.normal_vi)
        vi_trip['o9_change_descriptors'] = {'param': 'max_loss_cap', 'to': 80000}
        _, _, st_o9 = self._eval(vi_trip, session='2026-01-05')

        vi_rec = copy.deepcopy(self.normal_vi)
        vi_rec.update({
            'last_heartbeat': '2026-01-06T15:59:30Z', 'tier': 'aggressive',
            'tier_change_event': {'from': 'balanced'}, 'proposed_exposure': 50000.0,
            'v7_spread_width': 0.02, 'o5_collar': 0.05,
        })
        vi_rec['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_rec['funds']['SOXL']['v5_tolerance'] = 0.01
        r_re, eff_re, _ = self._eval(
            vi_rec, session='2026-01-06', prior=st_o9,
            events=[
                {'type': 'rearm', 'row_id': 'O9', 'session': '2026-01-06', 'scope': 'account'},
                {'type': 'tier_change_card', 'from': 'balanced', 'session': '2026-01-06'},
            ],
        )
        self.assertEqual(r_re['O9']['state'], 'HALT')
        self.assertEqual(eff_re['account'], 'HALT')
        self.assertEqual(compute_permitted_exposure(vi_rec, r_re, eff_re), 0.0)

        # 5. inputs['limits'] cannot mask missing SOXL v5_tolerance / v7_spread_width or missing top-level O3 reconciliation_tolerance
        for p_name, val, prev in (('v5_tolerance', 0.01, 0.005), ('v7_spread_width', 0.02, 0.01)):
            vi_lim = copy.deepcopy(self.normal_vi)
            vi_lim.pop(p_name, None)
            vi_lim['funds']['TQQQ'][p_name] = val
            vi_lim['limits'] = {p_name: val}
            vi_lim['o9_change_descriptors'] = {'param': p_name, 'from': prev, 'to': val}
            r_lim, _, _ = self._eval(
                vi_lim, session='2026-01-05',
                events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'change_descriptors': {'param': p_name, 'from': prev, 'to': val}}],
            )
            self.assertEqual(r_lim['O9']['state'], 'HALT')

        vi_rec_lim = copy.deepcopy(self.normal_vi)
        vi_rec_lim.pop('reconciliation_tolerance', None)
        vi_rec_lim['limits'] = {'reconciliation_tolerance': 1}
        vi_rec_lim['o9_change_descriptors'] = {'param': 'reconciliation_tolerance', 'from': 0, 'to': 1}
        r_rl, _, _ = self._eval(
            vi_rec_lim, session='2026-01-05',
            events=[{'type': 'parameter_change_card', 'session': '2026-01-05', 'change_descriptors': {'param': 'reconciliation_tolerance', 'from': 0, 'to': 1}}],
        )
        self.assertEqual(r_rl['O9']['state'], 'HALT')

    def test_r9_v2_omitted_fund_preserves_date_identities_and_string_action_id(self):
        """R9 #1-#2: Omitting fund from inputs keeps pending_action_identities (effective_date/ex_date); action_id '001' != '1'."""
        # 1. Omitted fund keeps effective_date & ex_date identity so Jan 5 replay cannot clear Jan 8 split
        for dkey in ('effective_date', 'ex_date'):
            vi1 = copy.deepcopy(self.normal_vi)
            vi1['funds']['TQQQ']['corporate_action'] = {
                'type': 'split', 'ratio': 2, dkey: '2026-01-08',
                'adjustment_complete': False, 'exact_reconciliation': False,
            }
            _, _, st1 = self._eval(vi1, session='2026-01-05')

            vi2 = copy.deepcopy(self.normal_vi)
            vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
            vi2['funds'] = {'SOXL': copy.deepcopy(self.normal_vi['funds']['SOXL'])}
            _, _, st2 = self._eval(vi2, session='2026-01-06', prior=st1)
            self.assertIn('TQQQ', st2['V2'].get('pending_action_identities', {}))

            vi3 = copy.deepcopy(self.normal_vi)
            vi3['last_heartbeat'] = '2026-01-07T15:59:30Z'
            vi3['funds']['TQQQ']['corporate_action'] = {
                'type': 'split', 'ratio': 2, dkey: '2026-01-05',
                'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': True,
            }
            r3, eff3, _ = self._eval(vi3, session='2026-01-07', prior=st2)
            self.assertEqual(r3['V2']['state'], 'HALT')
            self.assertEqual(eff3['fund:TQQQ'], 'HALT')

        # 2. String action_id="001" vs "1" are never float-coerced to equal
        vi_a1 = copy.deepcopy(self.normal_vi)
        vi_a1['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2, 'action_id': '001',
            'adjustment_complete': False, 'exact_reconciliation': False,
        }
        _, _, st_a1 = self._eval(vi_a1, session='2026-01-05')

        vi_a2 = copy.deepcopy(self.normal_vi)
        vi_a2['last_heartbeat'] = '2026-01-06T15:59:30Z'
        vi_a2['funds']['TQQQ']['corporate_action'] = {
            'type': 'split', 'ratio': 2, 'action_id': '1',
            'adjustment_complete': True, 'exact_reconciliation': True, 'hwm_adjusted': True,
        }
        r_a2, eff_a2, _ = self._eval(vi_a2, session='2026-01-06', prior=st_a1)
        self.assertEqual(r_a2['V2']['state'], 'HALT')
        self.assertEqual(eff_a2['fund:TQQQ'], 'HALT')

    def test_r9_o9_rejects_opaque_param_limits_card_even_with_rearm(self):
        """R9 #3: O9 rejects opaque {'param': 'limits', 'to': {...}} cards alongside Q4 rearm."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        vi_trip = copy.deepcopy(self.normal_vi)
        vi_trip['o9_change_descriptors'] = {'param': 'max_loss_cap', 'to': 80000}
        _, _, st_o9 = self._eval(vi_trip, session='2026-01-05')

        for p_dict in ({'reconciliation_tolerance': 1}, {'v5_tolerance': 0.01}, {'v7_spread_width': 0.02}):
            vi = copy.deepcopy(self.normal_vi)
            vi.update({
                'last_heartbeat': '2026-01-06T15:59:30Z',
                'reconciliation_tolerance': 10,
                'limits': p_dict,
                'o9_change_descriptors': {'param': 'limits', 'to': p_dict},
                'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
            })
            vi['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi['funds']['SOXL']['v5_tolerance'] = 0.01
            r, eff, _ = self._eval(
                vi, session='2026-01-06', prior=st_o9,
                events=[
                    {'type': 'rearm', 'row_id': 'O9', 'session': '2026-01-06', 'scope': 'account'},
                    {'type': 'parameter_change_card', 'session': '2026-01-06', 'change_descriptors': {'param': 'limits', 'to': p_dict}},
                ],
            )
            self.assertEqual(r['O9']['state'], 'HALT')
            self.assertEqual(eff['account'], 'HALT')
            self.assertEqual(compute_permitted_exposure(vi, r, eff), 0.0)

    def test_r9_o5_unified_alias_conflicts_and_nonpositive_order_size(self):
        """R9 #4-#6: O5 fails closed on conflicting order_value/symbol aliases and explicit order_size <= 0 even post-rearm."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        vi_trip = copy.deepcopy(self.normal_vi)
        vi_trip.update({'o5_collar': 0.05, 'side': 'short'})
        st_o5 = {}
        for _ in range(3):
            _, _, st_o5 = self._eval(vi_trip, session='2026-01-05', prior=st_o5)
        rearm_ev = [{'type': 'rearm', 'row_id': 'O5', 'session': '2026-01-06', 'scope': 'account'}]

        for bad_kw in (
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 200.0, 'o5_order_value': 100.0, 'order_value': 0.0},
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 200.0, 'o5_order_value': 100.0, 'order_value': 90.0},
            {'side': 'buy', 'symbol': 'UNLISTED', 'o5_symbol': 'TQQQ', 'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'settled_cash': 200.0},
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': -2, 'order_value': 100.0, 'settled_cash': 100.0},
            {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 0, 'order_value': 100.0, 'settled_cash': 100.0},
        ):
            vi = copy.deepcopy(self.normal_vi)
            vi.update({'last_heartbeat': '2026-01-06T15:59:30Z', 'o5_collar': 0.05, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, **bad_kw})
            vi['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi['funds']['SOXL']['v5_tolerance'] = 0.01
            r, eff, _ = self._eval(vi, session='2026-01-06', prior=st_o5, events=rearm_ev)
            self.assertTrue(r['O5']['would_have_tripped'], f"Expected reject for {bad_kw}")
            self.assertEqual(r['O5']['rejection_count_this_session'], 1)
            self.assertEqual(compute_permitted_exposure(vi, r, eff), 45000.0)

    def test_r9_o5_exact_decimal_notional_three_by_33_20_passes_three_times(self):
        """R9 #7: Valid qty=3, unit_price=33.20, order_value=99.60, settled_cash=200 passes 3x cleanly via exact Decimal arithmetic."""
        st = {}
        for _ in range(3):
            vi = copy.deepcopy(self.normal_vi)
            vi.update({
                'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
                'order_size': 3, 'unit_price': 33.20, 'o5_reference_price': 33.20,
                'order_value': 99.60, 'settled_cash': 200.0, 'account': 'synthetic_account_1',
            })
            r, eff, st = self._eval(vi, session='2026-01-05', prior=st)
            self.assertFalse(r['O5']['would_have_tripped'])
            self.assertEqual(r['O5']['state'], 'NORMAL')
            self.assertEqual(r['O5']['rejection_count_this_session'], 0)
            self.assertEqual(eff['account'], 'NORMAL')

    def test_r10_o5_sell_conflict_session_aliases_null_whitelist_and_permuted_whitelists(self):
        """R10 #1-#4: sell order_value conflict, session_order_count/turnover aliases, explicit symbol_whitelist=None, and order-insensitive valid whitelists."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        vi_trip = copy.deepcopy(self.normal_vi)
        vi_trip.update({'o5_collar': 0.05, 'side': 'short'})
        st_o5 = {}
        for _ in range(3):
            _, _, st_o5 = self._eval(vi_trip, session='2026-01-05', prior=st_o5)
        rearm_ev = [{'type': 'rearm', 'row_id': 'O5', 'session': '2026-01-06', 'scope': 'account'}]

        sell_conflict = {'side': 'sell', 'symbol': 'TQQQ', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'o5_order_value': 40.0}
        count_conflict = {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0, 'o5_max_orders_per_session': 5, 'session_order_count': 5, 'o5_orders_today': 0}
        turn_conflict = {'side': 'buy', 'symbol': 'TQQQ', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0, 'o5_max_turnover_per_session': 100.0, 'session_turnover': 200.0, 'o5_turnover_today': 0.0}
        null_wl = {'side': 'buy', 'symbol': 'TQQQ', 'symbol_whitelist': None, 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0}

        for kw in (sell_conflict, count_conflict, turn_conflict, null_wl):
            vi_norm = copy.deepcopy(self.normal_vi)
            vi_norm.update({'o5_collar': 0.05, **kw})
            r_norm, _, _ = self._eval(vi_norm, session='2026-01-05')
            self.assertTrue(r_norm['O5']['would_have_tripped'], f"Expected reject on normal path for {kw}")

            vi_rearm = copy.deepcopy(self.normal_vi)
            vi_rearm.update({'last_heartbeat': '2026-01-06T15:59:30Z', 'o5_collar': 0.05, 'proposed_exposure': 50000.0, 'v7_spread_width': 0.02, **kw})
            vi_rearm['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi_rearm['funds']['SOXL']['v5_tolerance'] = 0.01
            r_rearm, eff_rearm, _ = self._eval(vi_rearm, session='2026-01-06', prior=st_o5, events=rearm_ev)
            self.assertTrue(r_rearm['O5']['would_have_tripped'], f"Expected reject post-rearm for {kw}")
            self.assertEqual(r_rearm['O5']['rejection_count_this_session'], 1)
            self.assertEqual(compute_permitted_exposure(vi_rearm, r_rearm, eff_rearm), 45000.0)

        # Permuted equal symbol_whitelist and o5_symbol_whitelist MUST pass 3x cleanly
        st_perm = {}
        reversed_wl = list(reversed(self.normal_vi['symbol_whitelist']))
        for _ in range(3):
            vi_p = copy.deepcopy(self.normal_vi)
            vi_p.update({
                'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
                'o5_symbol_whitelist': reversed_wl,
                'order_size': 3, 'unit_price': 33.20, 'o5_reference_price': 33.20,
                'order_value': 99.60, 'settled_cash': 200.0, 'account': 'synthetic_account_1',
            })
            r_p, eff_p, st_perm = self._eval(vi_p, session='2026-01-05', prior=st_perm)
            self.assertFalse(r_p['O5']['would_have_tripped'])
            self.assertEqual(r_p['O5']['state'], 'NORMAL')
            self.assertEqual(eff_p['account'], 'NORMAL')

    def test_r11_f1_v5_escalation_persists_across_benign_and_clears_on_q4_rearm(self):
        """F1: V5 >=40 escalation stays NO-NEW-RISK on benign sessions until dated fund Q4 re-arm."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        prior_esc = {
            'V5': {'TQQQ': {'consecutive_beyond_tolerance': 40, 'escalated': True, 'last_session': '2026-03-06'}}
        }
        vi_benign = copy.deepcopy(self.normal_vi)
        vi_benign.update({
            'last_heartbeat': '2026-03-07T15:59:30Z', 'proposed_exposure': 50000.0,
            'target_fund': 'TQQQ', 'v5_tolerance': 0.003, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
        })
        vi_benign['funds']['TQQQ'].update({
            'shortfall_observed': 0.0005, 'shortfall_predicted': 0.0005, 'v5_tolerance': 0.003,
        })
        vi_benign['funds']['SOXL']['v5_tolerance'] = 0.003

        r_b, eff_b, st_b = self._eval(vi_benign, session='2026-03-07', prior=prior_esc)
        self.assertEqual(r_b['V5']['state'], 'NO-NEW-RISK')
        self.assertTrue(r_b['V5']['would_have_tripped'])
        self.assertFalse(r_b['V5']['latched'])
        self.assertEqual(r_b['V5']['reason'], 'escalated_to_v1_treatment')
        self.assertEqual(r_b['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 40)
        self.assertTrue(r_b['V5']['outputs']['escalated_to_v1'])
        self.assertEqual(r_b['V5']['outputs']['disposition'], 'escalated_to_v1')
        self.assertEqual(eff_b['fund:TQQQ'], 'NO-NEW-RISK')
        self.assertTrue(st_b['V5']['TQQQ']['escalated'])
        self.assertEqual(st_b['V5']['TQQQ']['consecutive_beyond_tolerance'], 40)
        self.assertEqual(compute_permitted_exposure(vi_benign, r_b, eff_b), 45000.0)

        # Subsequent excess open session still increments counter (40 -> 41)
        vi_excess = copy.deepcopy(vi_benign)
        vi_excess.update({'last_heartbeat': '2026-03-08T15:59:30Z'})
        vi_excess['funds']['TQQQ'].update({'shortfall_observed': 0.01, 'shortfall_predicted': 0.005})
        r_ex, eff_ex, st_ex = self._eval(vi_excess, session='2026-03-08', prior=st_b)
        self.assertEqual(r_ex['V5']['state'], 'NO-NEW-RISK')
        self.assertEqual(r_ex['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 41)
        self.assertEqual(st_ex['V5']['TQQQ']['consecutive_beyond_tolerance'], 41)
        self.assertEqual(eff_ex['fund:TQQQ'], 'NO-NEW-RISK')

        # Invalid/stale/wrong-fund/wrong-scope/undated Q4 cards must NOT clear V5 escalation
        for bad_ev in (
            {'type': 'rearm', 'row': 'V4', 'fund': 'TQQQ', 'session': '2026-03-09'},
            {'type': 'rearm', 'row': 'V5', 'fund': 'SOXL', 'session': '2026-03-09'},
            {'type': 'rearm', 'row': 'V5', 'fund': 'TQQQ', 'session': '2026-03-08'},
            {'type': 'rearm', 'row': 'V5', 'fund': 'TQQQ'},
            {'type': 'rearm', 'row': 'V5', 'fund': 'TQQQ', 'session': '2026-03-09', 'scope': 'account'},
        ):
            r_no, eff_no, st_no = self._eval(vi_benign, session='2026-03-09', prior=st_ex, events=[bad_ev])
            self.assertEqual(r_no['V5']['state'], 'NO-NEW-RISK', f"Unexpected V5 clear for {bad_ev}")
            self.assertEqual(eff_no['fund:TQQQ'], 'NO-NEW-RISK')
            self.assertTrue(st_no['V5']['TQQQ']['escalated'])

        # Valid dated fund-scoped Q4 re-arm clears V5 escalation completely
        vi_rearm = copy.deepcopy(vi_benign)
        vi_rearm['last_heartbeat'] = '2026-03-09T15:59:30Z'
        valid_ev = [{'type': 'rearm', 'row': 'V5', 'fund': 'TQQQ', 'session': '2026-03-09', 'scope': 'fund:TQQQ'}]
        r_clr, eff_clr, st_clr = self._eval(vi_rearm, session='2026-03-09', prior=st_ex, events=valid_ev)
        self.assertEqual(r_clr['V5']['state'], 'NORMAL')
        self.assertFalse(r_clr['V5']['would_have_tripped'])
        self.assertEqual(r_clr['V5']['reason'], 'authorized_rearm')
        self.assertEqual(r_clr['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 0)
        self.assertFalse(r_clr['V5']['outputs']['escalated_to_v1'])
        self.assertEqual(r_clr['V5']['outputs']['disposition'], 'authorized_rearm')
        self.assertEqual(eff_clr['fund:TQQQ'], 'NORMAL')
        self.assertNotIn('TQQQ', st_clr.get('V5', {}))
        self.assertEqual(compute_permitted_exposure(vi_rearm, r_clr, eff_clr), 50000.0)

        # Valid Q4 re-arm also clears omitted prior-escalated V5 fund (clean scope with SOXL, and V5: {} when funds={})
        vi_omitted = copy.deepcopy(vi_rearm)
        vi_omitted['funds'] = {'SOXL': copy.deepcopy(vi_rearm['funds']['SOXL'])}
        r_om, eff_om, st_om = self._eval(vi_omitted, session='2026-03-09', prior=st_ex, events=valid_ev)
        self.assertEqual(r_om['V5']['state'], 'NORMAL')
        self.assertEqual(r_om['V5']['reason'], 'authorized_rearm')
        self.assertEqual(eff_om['fund:TQQQ'], 'NORMAL')
        self.assertNotIn('TQQQ', st_om.get('V5', {}))

        vi_empty = copy.deepcopy(vi_rearm)
        vi_empty['funds'] = {}
        vi_empty['last_heartbeat'] = '2026-03-07T15:59:30Z'
        r_em, _, st_em = self._eval(
            vi_empty, session='2026-03-07', prior=prior_esc,
            events=[{'type': 'rearm', 'row': 'V5', 'fund': 'TQQQ', 'session': '2026-03-07', 'scope': 'fund:TQQQ'}],
        )
        self.assertEqual(r_em['V5']['state'], 'NORMAL')
        self.assertEqual(r_em['V5']['reason'], 'authorized_rearm')
        self.assertEqual(st_em['V5'], {})

    def test_r11_f5_v5_excludes_market_closed_and_preserves_unresolved_holiday(self):
        """F5: V5 ignores holiday/closed sessions for persistence while keeping unresolved tolerance fail-closed."""
        import json
        holiday_vi = json.loads(
            (repo_root / 'goldens' / 'scenarios.json').read_text(encoding='utf-8')
        )['scenarios']['holiday']['inputs']['validated_inputs']

        prior_39 = {
            'V5': {'TQQQ': {'consecutive_beyond_tolerance': 39, 'escalated': False, 'last_session': '2026-01-16'}}
        }
        vi_hol = copy.deepcopy(holiday_vi)
        vi_hol.update({'v5_tolerance': 0.003, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi_hol['funds']['TQQQ'].update({
            'shortfall_observed': 0.01, 'shortfall_predicted': 0.005, 'v5_tolerance': 0.003,
        })
        vi_hol['funds']['SOXL']['v5_tolerance'] = 0.003

        r_h, eff_h, st_h = self._eval(vi_hol, session='2026-01-19', prior=prior_39)
        self.assertEqual(r_h['V5']['state'], 'NORMAL')
        self.assertFalse(r_h['V5']['would_have_tripped'])
        self.assertEqual(r_h['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 39)
        self.assertFalse(r_h['V5']['outputs']['escalated_to_v1'])
        self.assertEqual(eff_h['fund:TQQQ'], 'NORMAL')
        self.assertEqual(
            st_h['V5']['TQQQ'],
            {'consecutive_beyond_tolerance': 39, 'escalated': False, 'last_session': '2026-01-16'},
        )

        # Fresh holiday with no prior V5 entry does NOT fabricate a holiday last_session
        r_fresh, _, st_fresh = self._eval(vi_hol, session='2026-01-19', prior={})
        self.assertFalse(r_fresh['V5']['would_have_tripped'])
        self.assertNotIn('TQQQ', st_fresh.get('V5', {}))

        # Unresolved v5_tolerance on holiday STILL fails closed as UNRESOLVED-FAIL-CLOSED (holiday.V5 oracle)
        vi_unres = copy.deepcopy(holiday_vi)
        r_unres, _, _ = self._eval(vi_unres, session='2026-01-19', prior={})
        self.assertEqual(r_unres['V5']['reason'], 'unresolved_fail_closed')
        self.assertEqual(r_unres['V5']['outputs']['disposition'], 'UNRESOLVED-FAIL-CLOSED')
        self.assertTrue(r_unres['V5']['would_have_tripped'])

        # Escalated fund on holiday stays NO-NEW-RISK and preserves prior last_session
        prior_40 = {
            'V5': {'TQQQ': {'consecutive_beyond_tolerance': 40, 'escalated': True, 'last_session': '2026-01-16'}}
        }
        r_esc, eff_esc, st_esc = self._eval(vi_hol, session='2026-01-19', prior=prior_40)
        self.assertEqual(r_esc['V5']['state'], 'NO-NEW-RISK')
        self.assertEqual(eff_esc['fund:TQQQ'], 'NO-NEW-RISK')
        self.assertEqual(st_esc['V5']['TQQQ']['last_session'], '2026-01-16')

    def test_r11_f2_o5_requires_whitelisted_account_when_order_present(self):
        """F2: O5 fails closed whenever an active order omits account/o5_account and latches HALT on 3rd reject."""
        st = {}
        for i in range(1, 4):
            vi_missing_acct = copy.deepcopy(self.normal_vi)
            vi_missing_acct.update({
                'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
                'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0,
                'order_value': 100.0, 'settled_cash': 200.0,
            })
            r, eff, st = self._eval(vi_missing_acct, session='2026-01-05', prior=st)
            self.assertTrue(r['O5']['would_have_tripped'])
            self.assertEqual(r['O5']['rejection_count_this_session'], i)
            if i == 3:
                self.assertEqual(r['O5']['state'], 'HALT')
                self.assertTrue(r['O5']['latched'])
                self.assertEqual(eff['account'], 'HALT')

        # Valid whitelisted account passes 3x cleanly
        st_ok = {}
        for acct_key in ('account', 'o5_account'):
            st_ok = {}
            for _ in range(3):
                vi_ok = copy.deepcopy(self.normal_vi)
                vi_ok.update({
                    'o5_collar': 0.05, 'side': 'buy', 'symbol': 'TQQQ',
                    'order_size': 2, 'unit_price': 50.0, 'o5_reference_price': 50.0,
                    'order_value': 100.0, 'settled_cash': 200.0,
                    acct_key: 'synthetic_account_1',
                })
                r_ok, eff_ok, st_ok = self._eval(vi_ok, session='2026-01-05', prior=st_ok)
                self.assertFalse(r_ok['O5']['would_have_tripped'])
                self.assertEqual(r_ok['O5']['state'], 'NORMAL')
                self.assertEqual(eff_ok['account'], 'NORMAL')

    def test_r11_f3_o5_projected_session_turnover_includes_order_notional(self):
        """F3: O5 rejects orders whose projected turnover exceeds max_turnover_per_session and allows exact boundary."""
        for kw in (
            {'side': 'buy', 'order_value': 50.0},
            {'side': 'buy', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0},
            {'side': 'buy', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 0.0},
            {'side': 'sell', 'order_value': 50.0, 'order_size': 1},
            {'side': 'sell', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0},
            {'side': 'sell', 'order_size': 1},
        ):
            vi_over = copy.deepcopy(self.normal_vi)
            vi_over.update({
                'o5_collar': 0.05, 'symbol': 'TQQQ', 'account': 'synthetic_account_1',
                'settled_cash': 200.0, 'session_turnover': 99990.0, 'max_turnover_per_session': 100000.0,
                **kw,
            })
            r_over, _, _ = self._eval(vi_over, session='2026-01-05')
            self.assertTrue(r_over['O5']['would_have_tripped'], f"Expected turnover reject for {kw}")

        for ok_kw in (
            {'side': 'buy', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0},
            {'side': 'buy', 'order_value': 50.0, 'unit_price': 50.0, 'o5_reference_price': 50.0},
            {'side': 'sell', 'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0},
        ):
            st_ok = {}
            for _ in range(3):
                vi_eq = copy.deepcopy(self.normal_vi)
                vi_eq.update({
                    'o5_collar': 0.05, 'symbol': 'TQQQ', 'account': 'synthetic_account_1',
                    'settled_cash': 200.0, 'session_turnover': 99950.0, 'max_turnover_per_session': 100000.0,
                    **ok_kw,
                })
                r_eq, eff_eq, st_ok = self._eval(vi_eq, session='2026-01-05', prior=st_ok)
                self.assertFalse(r_eq['O5']['would_have_tripped'], f"Expected exact turnover boundary pass for {ok_kw}")
                self.assertEqual(eff_eq['account'], 'NORMAL')

    def test_r11_f4_v7_evaluates_proposed_order_symbol_outside_funds(self):
        """F4: V7 evaluates o5_symbol/symbol outside funds (fails closed without quotes, passes with valid quotes)."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        vi_no_q = copy.deepcopy(self.normal_vi)
        vi_no_q.update({
            'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
            'account': 'synthetic_account_1', 'o5_symbol': 'BIL', 'side': 'buy',
            'order_size': 1, 'order_value': 50.0, 'settled_cash': 200.0,
            'unit_price': 50.0, 'o5_reference_price': 50.0,
        })
        vi_no_q['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_no_q['funds']['SOXL']['v5_tolerance'] = 0.01

        r_nq, eff_nq, _ = self._eval(vi_no_q)
        self.assertTrue(r_nq['V7']['would_have_tripped'])
        self.assertEqual(r_nq['V7']['reason'], 'missing_input')
        self.assertIn('symbol:BIL', eff_nq)
        self.assertEqual(compute_permitted_exposure(vi_no_q, r_nq, eff_nq), 45000.0)

        # Supplying valid quote data for BIL clears V7 and permits exposure raise
        vi_with_q = copy.deepcopy(vi_no_q)
        vi_with_q['quotes'] = {
            'BIL': {'quote_staleness': 0.05, 'spread_width': 0.0001, 'trading_pause': False, 'session_time': 'regular'}
        }
        r_wq, eff_wq, _ = self._eval(vi_with_q)
        self.assertFalse(r_wq['V7']['would_have_tripped'])
        self.assertEqual(r_wq['V7']['reason'], 'none')
        self.assertEqual(compute_permitted_exposure(vi_with_q, r_wq, eff_wq), 50000.0)

        # Per-symbol V7 scoping still permits BIL when only TQQQ is stale
        vi_tqqq_stale = copy.deepcopy(vi_with_q)
        vi_tqqq_stale['funds']['TQQQ']['quote_staleness'] = 5.0
        r_ts, eff_ts, _ = self._eval(vi_tqqq_stale)
        self.assertTrue(r_ts['V7']['would_have_tripped'])
        self.assertEqual(compute_permitted_exposure(vi_tqqq_stale, r_ts, eff_ts), 50000.0)

        # Malformed non-empty/blank proposed symbol still fails closed in V7
        vi_bad_sym = copy.deepcopy(vi_no_q)
        vi_bad_sym['o5_symbol'] = ''
        r_bs, eff_bs, _ = self._eval(vi_bad_sym)
        self.assertTrue(r_bs['V7']['would_have_tripped'])
        self.assertEqual(r_bs['V7']['reason'], 'invalid_input')
        self.assertEqual(compute_permitted_exposure(vi_bad_sym, r_bs, eff_bs), 45000.0)

    def test_r12_v1_five_session_history_bootstrap_appends_current_session(self):
        """R12 P1-1: V1 with 5 prior five_session_history items still evaluates and appends the current session."""
        vi = copy.deepcopy(self.normal_vi)
        vi.update({'last_heartbeat': '2026-01-10T15:59:30Z'})
        vi['funds']['TQQQ'].update({
            'fund_return': -0.0055,
            'index_return': 0.0,
            'modelled_fee': 0.0,
            'modelled_financing': 0.0,
            'five_session_history': [
                {'fund_return': 0.0, 'index_return': 0.0, 'modelled_fee': 0.0, 'modelled_financing': 0.0},
                {'fund_return': 0.0, 'index_return': 0.0, 'modelled_fee': 0.0, 'modelled_financing': 0.0},
                {'fund_return': -0.0055, 'index_return': 0.0, 'modelled_fee': 0.0, 'modelled_financing': 0.0},
                {'fund_return': -0.0055, 'index_return': 0.0, 'modelled_fee': 0.0, 'modelled_financing': 0.0},
                {'fund_return': -0.0055, 'index_return': 0.0, 'modelled_fee': 0.0, 'modelled_financing': 0.0},
            ],
        })
        rows, eff, st = self._eval(vi, session='2026-01-10', prior={})
        self.assertEqual(rows['V1']['state'], 'NO-NEW-RISK')
        self.assertTrue(rows['V1']['latched'])
        self.assertEqual(rows['V1']['reason'], 'tracking_deviation_exceeds_2_0pp')
        self.assertEqual(eff['fund:TQQQ'], 'NO-NEW-RISK')
        persisted = st['V1']['TQQQ']['session_returns']
        self.assertEqual(len(persisted), 5)
        self.assertEqual(persisted[0]['fund_return'], 0.0)
        self.assertEqual(persisted[-1]['session'], '2026-01-10')
        self.assertEqual(persisted[-1]['fund_return'], -0.0055)

    def test_r12_o4_malformed_payload_persists_and_clears_only_via_q4_rearm(self):
        """R12 P1-2: O4 malformed pending_orders without prior lock persists across empty pending_orders until Q4 re-arm."""
        vi1 = copy.deepcopy(self.normal_vi)
        vi1['pending_orders'] = {'TQQQ': 'malformed_payload'}
        r1, eff1, st1 = self._eval(vi1, session='2026-01-05', prior={})
        self.assertEqual(r1['O4']['state'], 'ORDER-UNKNOWN')
        self.assertTrue(r1['O4']['latched'])
        self.assertEqual(r1['O4']['reason'], 'missing_input')
        self.assertEqual(eff1['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st1['O4']['TQQQ']['original_order_id'], 'unidentified_order_TQQQ')

        # Subsequent evaluation with empty pending_orders={} MUST remain ORDER-UNKNOWN
        vi2 = copy.deepcopy(self.normal_vi)
        vi2['last_heartbeat'] = '2026-01-06T15:59:30Z'
        vi2['pending_orders'] = {}
        r2, eff2, st2 = self._eval(vi2, session='2026-01-06', prior=st1)
        self.assertEqual(r2['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(r2['O4']['reason'], 'awaiting_original_order_status')
        self.assertEqual(eff2['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st2['O4']['TQQQ']['original_order_id'], 'unidentified_order_TQQQ')

        # Invalid/undated/fund-scoped/wrong-symbol/stale Q4 rearm cards must NOT clear O4
        vi3 = copy.deepcopy(self.normal_vi)
        vi3['last_heartbeat'] = '2026-01-07T15:59:30Z'
        vi3['pending_orders'] = {}
        for bad_ev in (
            {'type': 'rearm', 'row': 'O4', 'symbol': 'TQQQ'},
            {'type': 'rearm', 'row': 'O4', 'symbol': 'TQQQ', 'session': '2026-01-06'},
            {'type': 'rearm', 'row': 'O4', 'fund': 'TQQQ', 'session': '2026-01-07'},
            {'type': 'rearm', 'row': 'O4', 'symbol': 'SOXL', 'session': '2026-01-07'},
        ):
            r_no, eff_no, _ = self._eval(vi3, session='2026-01-07', prior=st2, events=[bad_ev])
            self.assertEqual(eff_no['symbol:TQQQ'], 'ORDER-UNKNOWN', f"Unexpected O4 clear for {bad_ev}")
            self.assertEqual(r_no['O4']['state'], 'ORDER-UNKNOWN')

        # Valid Q4 rearm does NOT bypass active malformed payload in current session
        valid_ev = [{'type': 'rearm', 'row': 'O4', 'symbol': 'TQQQ', 'session': '2026-01-07', 'scope': 'symbol:TQQQ'}]
        vi3_mal = copy.deepcopy(vi3)
        vi3_mal['pending_orders'] = {'TQQQ': 'still_malformed'}
        _, eff_mal, st_mal = self._eval(vi3_mal, session='2026-01-07', prior=st2, events=valid_ev)
        self.assertEqual(eff_mal['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st_mal['O4']['TQQQ']['original_order_id'], 'unidentified_order_TQQQ')

        # Valid dated symbol-scoped Q4 rearm clears lock when pending_orders is clean
        r_clr, eff_clr, st_clr = self._eval(vi3, session='2026-01-07', prior=st2, events=valid_ev)
        self.assertEqual(r_clr['O4']['state'], 'NORMAL')
        self.assertFalse(r_clr['O4']['would_have_tripped'])
        self.assertEqual(r_clr['O4']['reason'], 'authorized_rearm')
        self.assertEqual(eff_clr['symbol:TQQQ'], 'NORMAL')
        self.assertEqual(st_clr['O4'], {})

    def test_r13_o5_dollar_max_size_missing_counters_and_mandatory_price_collar(self):
        """R13 O5 P1 #1-#3: dollar-order max_order_size, missing/null counters fail closed, and mandatory price collar."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        # 1. Dollar order (order_value=5000, price=ref=50, omit qty) must fail max_order_size=1 -> 3x HALT
        st1 = {}
        for i in range(1, 4):
            vi1 = copy.deepcopy(self.normal_vi)
            vi1.update({
                'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02,
                'o5_collar': 0.05, 'account': 'synthetic_account_1', 'symbol': 'TQQQ', 'side': 'buy',
                'order_value': 5000.0, 'unit_price': 50.0, 'o5_reference_price': 50.0,
                'max_order_size': 1, 'settled_cash': 10000.0,
            })
            vi1['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi1['funds']['SOXL']['v5_tolerance'] = 0.01
            r1, eff1, st1 = self._eval(vi1, session='2026-01-05', prior=st1)
            self.assertTrue(r1['O5']['would_have_tripped'])
            self.assertEqual(r1['O5']['rejection_count_this_session'], i)
            if i < 3:
                self.assertEqual(compute_permitted_exposure(vi1, r1, eff1), 45000.0)
            else:
                self.assertEqual(r1['O5']['state'], 'HALT')
                self.assertTrue(r1['O5']['latched'])
                self.assertEqual(eff1['account'], 'HALT')
                self.assertEqual(compute_permitted_exposure(vi1, r1, eff1), 0.0)

        # Also reject when explicit qty=1 is combined with order_value=5000 exceeding max_order_size=1 -> 3x HALT
        st1_dual = {}
        for i in range(1, 4):
            vi1_dual = copy.deepcopy(self.normal_vi)
            vi1_dual.update({
                'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02,
                'o5_collar': 0.05, 'account': 'synthetic_account_1', 'symbol': 'TQQQ', 'side': 'buy',
                'qty': 1, 'order_value': 5000.0, 'unit_price': 50.0, 'o5_reference_price': 50.0,
                'max_order_size': 1, 'settled_cash': 10000.0,
            })
            vi1_dual['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi1_dual['funds']['SOXL']['v5_tolerance'] = 0.01
            r1d, eff1d, st1_dual = self._eval(vi1_dual, session='2026-01-05', prior=st1_dual)
            self.assertTrue(r1d['O5']['would_have_tripped'])
            self.assertEqual(r1d['O5']['rejection_count_this_session'], i)
            if i < 3:
                self.assertEqual(compute_permitted_exposure(vi1_dual, r1d, eff1d), 45000.0)
            else:
                self.assertEqual(r1d['O5']['state'], 'HALT')
                self.assertTrue(r1d['O5']['latched'])
                self.assertEqual(eff1d['account'], 'HALT')
                self.assertEqual(compute_permitted_exposure(vi1_dual, r1d, eff1d), 0.0)

        # Dollar order within max_order_size=1 (order_value=50, price=50, both without and with qty=1) passes 3x cleanly
        for extra_qty in ({}, {'qty': 1}):
            st1_ok = {}
            for _ in range(3):
                vi1_ok = copy.deepcopy(self.normal_vi)
                vi1_ok.update({
                    'o5_collar': 0.05, 'account': 'synthetic_account_1', 'symbol': 'TQQQ', 'side': 'buy',
                    'order_value': 50.0, 'unit_price': 50.0, 'o5_reference_price': 50.0,
                    'max_order_size': 1, 'settled_cash': 10000.0, **extra_qty,
                })
                r_ok, eff_ok, st1_ok = self._eval(vi1_ok, session='2026-01-05', prior=st1_ok)
                self.assertFalse(r_ok['O5']['would_have_tripped'])
                self.assertEqual(eff_ok['account'], 'NORMAL')

        # 2. Missing or null session_order_count / session_turnover fail closed when cap set -> 3x HALT
        for cap_key, drop_key, null_mode in (
            ('max_orders_per_session', 'session_order_count', False),
            ('max_orders_per_session', 'session_order_count', True),
            ('max_turnover_per_session', 'session_turnover', False),
            ('max_turnover_per_session', 'session_turnover', True),
        ):
            st2 = {}
            for i in range(1, 4):
                vi2 = copy.deepcopy(self.normal_vi)
                vi2.update({
                    'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02,
                    'o5_collar': 0.05, 'account': 'synthetic_account_1', 'symbol': 'TQQQ', 'side': 'buy',
                    'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0,
                    'settled_cash': 200.0, cap_key: 1000.0 if 'turnover' in cap_key else 5,
                })
                vi2['funds']['TQQQ']['v5_tolerance'] = 0.01
                vi2['funds']['SOXL']['v5_tolerance'] = 0.01
                if null_mode:
                    vi2[drop_key] = None
                else:
                    vi2.pop(drop_key, None)
                r2, eff2, st2 = self._eval(vi2, session='2026-01-05', prior=st2)
                self.assertTrue(r2['O5']['would_have_tripped'], f"Expected reject for {cap_key} {drop_key} null={null_mode}")
                self.assertEqual(r2['O5']['rejection_count_this_session'], i)
                if i == 3:
                    self.assertEqual(r2['O5']['state'], 'HALT')
                    self.assertEqual(eff2['account'], 'HALT')

        # Without active order, missing counters do NOT spuriously trip max_orders / max_turnover
        vi_no_order = copy.deepcopy(self.normal_vi)
        vi_no_order.pop('session_order_count', None)
        vi_no_order.pop('session_turnover', None)
        vi_no_order.update({'o5_collar': 0.05, 'max_orders_per_session': 5, 'max_turnover_per_session': 1000.0})
        self.assertFalse(self._eval(vi_no_order)[0]['O5']['would_have_tripped'])

        # 3. Active order omitting unit_price / o5_reference_price fails collar check -> 3x HALT
        st3 = {}
        for i in range(1, 4):
            vi3 = copy.deepcopy(self.normal_vi)
            vi3.update({
                'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02,
                'o5_collar': 0.05, 'account': 'synthetic_account_1', 'symbol': 'TQQQ', 'side': 'buy',
                'order_size': 10, 'order_value': 500.0, 'settled_cash': 1000.0,
            })
            vi3['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi3['funds']['SOXL']['v5_tolerance'] = 0.01
            r3, eff3, st3 = self._eval(vi3, session='2026-01-05', prior=st3)
            self.assertTrue(r3['O5']['would_have_tripped'])
            self.assertEqual(r3['O5']['rejection_count_this_session'], i)
            if i == 3:
                self.assertEqual(r3['O5']['state'], 'HALT')
                self.assertTrue(r3['O5']['latched'])
                self.assertEqual(eff3['account'], 'HALT')

    def test_r15_malformed_pending_orders_missing_fund_vehicle_order_and_missing_order_symbol(self):
        """R15: malformed pending_orders list/None fails closed; non-BIL order target absent from funds fails V1/V4; O5 rejects active order omitting symbol."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        # 1. Malformed pending_orders collection (list / scalar / explicit None) fails O4 closed & blocks raise
        for bad_po in (['broker response unavailable'], 'unavailable', 123, None):
            vi1 = copy.deepcopy(self.normal_vi)
            vi1.update({'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
            vi1['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi1['funds']['SOXL']['v5_tolerance'] = 0.01
            vi1['pending_orders'] = bad_po
            r1, eff1, _ = self._eval(vi1, session='2026-01-05')
            self.assertEqual(r1['O4']['state'], 'ORDER-UNKNOWN')
            self.assertTrue(r1['O4']['would_have_tripped'])
            self.assertEqual(r1['O4']['reason'], 'malformed_pending_orders')
            self.assertEqual(eff1['symbol:TQQQ'], 'ORDER-UNKNOWN')
            self.assertEqual(eff1['symbol:SOXL'], 'ORDER-UNKNOWN')
            self.assertEqual(compute_permitted_exposure(vi1, r1, eff1), 45000.0)

        # Malformed pending_orders preserves prior O4 order lock & works when funds={}
        vi1_prior = copy.deepcopy(self.normal_vi)
        vi1_prior['pending_orders'] = ['broker response unavailable']
        r1_p, eff1_p, st1_p = self._eval(
            vi1_prior,
            session='2026-01-06',
            prior={'O4': {'TQQQ': {'original_order_id': 'ordA', 'status': 'unknown'}}},
        )
        self.assertEqual(r1_p['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(r1_p['O4']['reason'], 'malformed_pending_orders')
        self.assertEqual(eff1_p['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st1_p['O4']['TQQQ']['original_order_id'], 'ordA')

        vi1_empty = copy.deepcopy(self.normal_vi)
        vi1_empty['pending_orders'] = ['broker response unavailable']
        vi1_empty['funds'] = {}
        r1_empty, eff1_empty, st1_empty = self._eval(
            vi1_empty,
            session='2026-01-06',
            prior={'O4': {'TQQQ': {'original_order_id': 'ordA', 'status': 'unknown'}}},
        )
        self.assertEqual(r1_empty['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(r1_empty['O4']['reason'], 'malformed_pending_orders')
        self.assertEqual(eff1_empty['account'], 'HALT')
        self.assertEqual(st1_empty['O4']['TQQQ']['original_order_id'], 'ordA')

        # 2. Removing leveraged fund TQQQ from funds while keeping quotes['TQQQ'] triggers V1/V4 fail-closed on buy TQQQ
        vi2 = copy.deepcopy(self.normal_vi)
        vi2.update({
            'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
            'account': 'synthetic_account_1', 'side': 'buy', 'symbol': 'TQQQ',
            'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0,
            'quotes': {'TQQQ': {'quote_staleness': 0.05, 'spread_width': 0.0001, 'trading_pause': False, 'session_time': 'regular'}},
        })
        vi2['funds'].pop('TQQQ')
        vi2['funds']['SOXL']['v5_tolerance'] = 0.01
        r2, eff2, _ = self._eval(vi2)
        self.assertEqual(r2['V1']['state'], 'NO-NEW-RISK')
        self.assertTrue(r2['V1']['would_have_tripped'])
        self.assertEqual(r2['V4']['state'], 'NO-NEW-RISK')
        self.assertTrue(r2['V4']['would_have_tripped'])
        self.assertEqual(eff2['fund:TQQQ'], 'NO-NEW-RISK')
        self.assertEqual(compute_permitted_exposure(vi2, r2, eff2), 45000.0)

        # Cash ETF BIL outside funds with valid quotes['BIL'] still passes cleanly
        vi_bil_ok = copy.deepcopy(self.normal_vi)
        vi_bil_ok.update({
            'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
            'account': 'synthetic_account_1', 'side': 'buy', 'o5_symbol': 'BIL',
            'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0,
            'quotes': {'BIL': {'quote_staleness': 0.05, 'spread_width': 0.0001, 'trading_pause': False, 'session_time': 'regular'}},
        })
        vi_bil_ok['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_bil_ok['funds']['SOXL']['v5_tolerance'] = 0.01
        r_bil, eff_bil, _ = self._eval(vi_bil_ok)
        self.assertEqual(r_bil['V1']['state'], 'NORMAL')
        self.assertEqual(r_bil['V7']['state'], 'NORMAL')
        self.assertFalse(r_bil['O5']['would_have_tripped'])
        self.assertEqual(compute_permitted_exposure(vi_bil_ok, r_bil, eff_bil), 50000.0)

        # 3. Active order omitting symbol/o5_symbol fails O5 closed -> 3x HALT
        st3 = {}
        for i in range(1, 4):
            vi3 = copy.deepcopy(self.normal_vi)
            vi3.update({
                'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
                'account': 'synthetic_account_1', 'side': 'buy',
                'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0,
            })
            vi3['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi3['funds']['SOXL']['v5_tolerance'] = 0.01
            r3, eff3, st3 = self._eval(vi3, session='2026-01-05', prior=st3)
            self.assertTrue(r3['O5']['would_have_tripped'])
            self.assertEqual(r3['O5']['rejection_count_this_session'], i)
            if i < 3:
                self.assertEqual(compute_permitted_exposure(vi3, r3, eff3), 45000.0)
            else:
                self.assertEqual(r3['O5']['state'], 'HALT')
                self.assertTrue(r3['O5']['latched'])
                self.assertEqual(eff3['account'], 'HALT')
                self.assertEqual(compute_permitted_exposure(vi3, r3, eff3), 0.0)

    def test_r16_malformed_pending_orders_o4_durability_v5_missing_fund_and_symbol_whitespace(self):
        """R16 P1: O4 preserves fund timeouts under malformed pending_orders, V1-V5 stay durable on missing fund, & whitespace target clamps."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        # 1. pending_orders=None + funds['TQQQ']['o4_pending_order']={'order_id':'A','timed_out':True} records 'A' into next_row_state['O4']
        vi1a = copy.deepcopy(self.normal_vi)
        vi1a.update({'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi1a['funds']['TQQQ'].update({'v5_tolerance': 0.01, 'o4_pending_order': {'order_id': 'A', 'timed_out': True}})
        vi1a['funds']['SOXL']['v5_tolerance'] = 0.01
        vi1a['pending_orders'] = None
        r1a, eff1a, st1a = self._eval(vi1a, session='2026-01-05')
        self.assertEqual(r1a['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(r1a['O4']['reason'], 'malformed_pending_orders')
        self.assertEqual(eff1a['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st1a['O4']['TQQQ']['original_order_id'], 'A')

        # Next session pending_orders={} keeps ORDER-UNKNOWN on 'A' and clamps permitted exposure to 45000.0
        vi1b = copy.deepcopy(self.normal_vi)
        vi1b.update({'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi1b['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi1b['funds']['SOXL']['v5_tolerance'] = 0.01
        vi1b['pending_orders'] = {}
        for sr in vi1b['source_records'].values():
            sr['timestamp'] = '2026-01-06T15:59:00Z'
        r1b, eff1b, st1b = self._eval(vi1b, session='2026-01-06', prior=st1a)
        self.assertEqual(r1b['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(r1b['O4']['reason'], 'awaiting_original_order_status')
        self.assertEqual(eff1b['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st1b['O4']['TQQQ']['original_order_id'], 'A')
        self.assertEqual(compute_permitted_exposure(vi1b, r1b, eff1b), 45000.0)

        # Malformed pending_orders also refuses clearing prior O4 lock even with Q4 rearm or filled fund hint
        vi1c = copy.deepcopy(vi1a)
        vi1c['funds']['TQQQ']['o4_pending_order'] = {'order_id': 'A', 'status': 'filled'}
        rearm_o4 = [{'type': 'rearm', 'row': 'O4', 'symbol': 'TQQQ', 'session': '2026-01-06', 'scope': 'symbol:TQQQ'}]
        r1c, eff1c, st1c = self._eval(vi1c, session='2026-01-06', prior=st1a, events=rearm_o4)
        self.assertEqual(r1c['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(r1c['O4']['reason'], 'malformed_pending_orders')
        self.assertEqual(eff1c['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st1c['O4']['TQQQ']['original_order_id'], 'A')

        # 2. V5 count=39 preserved across TQQQ missing from funds (buy TQQQ) and across in-fund missing_input; advances 39->40 on recovery
        prior_durability = {
            'V1': {'TQQQ': {'session_returns': [{'session': '2026-01-05', 'fund_return': 0.01, 'expected_return': 0.01}]}},
            'V2': {
                'pending_adjustments': {'TQQQ': {'type': 'split', 'ratio': 2, 'awaiting_reconciliation': True}},
                'pending_action_identities': {'TQQQ': {'primary': {'type': 'split', 'ratio': 2, 'ex_date': '2026-01-08'}}},
            },
            'V3': {'TQQQ': {'latched': True, 'trip_session': '2026-01-05', 'details': {'reason': 'fund_event'}}},
            'V4': {'TQQQ': {'clearing_counter': 5, 'last_session_below_threshold': '2026-01-05'}},
            'V5': {'TQQQ': {'consecutive_beyond_tolerance': 39, 'escalated': False, 'last_session': '2026-01-05'}},
        }
        vi2_omit = copy.deepcopy(self.normal_vi)
        vi2_omit.update({
            'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
            'account': 'synthetic_account_1', 'side': 'buy', 'symbol': 'TQQQ',
            'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0,
            'quotes': {'TQQQ': {'quote_staleness': 0.05, 'spread_width': 0.0001, 'trading_pause': False, 'session_time': 'regular'}},
        })
        vi2_omit['funds'].pop('TQQQ')
        vi2_omit['funds']['SOXL']['v5_tolerance'] = 0.01
        r2a, _, st2a = self._eval(vi2_omit, session='2026-01-06', prior=prior_durability)
        self.assertEqual(r2a['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 39)
        self.assertEqual(st2a['V5']['TQQQ'], {'consecutive_beyond_tolerance': 39, 'escalated': False, 'last_session': '2026-01-05'})
        self.assertEqual(len(st2a['V1']['TQQQ']['session_returns']), 1)
        self.assertEqual(st2a['V2']['pending_action_identities']['TQQQ']['primary']['ex_date'], '2026-01-08')
        self.assertTrue(st2a['V3']['TQQQ']['latched'])
        self.assertEqual(st2a['V4']['TQQQ'], {'clearing_counter': 5, 'last_session_below_threshold': '2026-01-05'})

        # Restoring TQQQ on same session 2026-01-06 with excess advances V5 39 -> 40 -> NO-NEW-RISK
        vi2_rest = copy.deepcopy(self.normal_vi)
        vi2_rest.update({'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi2_rest['funds']['TQQQ'].update({'v5_tolerance': 0.01, 'shortfall_observed': 0.05, 'shortfall_predicted': 0.01})
        vi2_rest['funds']['SOXL']['v5_tolerance'] = 0.01
        for sr in vi2_rest['source_records'].values():
            sr['timestamp'] = '2026-01-06T19:59:00Z'
        r2b, eff2b, st2b = self._eval(
            vi2_rest, session='2026-01-06',
            prior={'V5': copy.deepcopy(st2a['V5'])},
        )
        self.assertEqual(r2b['V5']['state'], 'NO-NEW-RISK')
        self.assertEqual(r2b['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 40)
        self.assertTrue(r2b['V5']['outputs']['escalated_to_v1'])
        self.assertEqual(eff2b['fund:TQQQ'], 'NO-NEW-RISK')
        self.assertEqual(st2b['V5']['TQQQ']['consecutive_beyond_tolerance'], 40)
        self.assertEqual(compute_permitted_exposure(vi2_rest, r2b, eff2b), 45000.0)

        # In-fund shortfall_observed=None also preserves V5 count=39 rather than resetting to 0
        vi2_miss_sf = copy.deepcopy(self.normal_vi)
        vi2_miss_sf.update({'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi2_miss_sf['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi2_miss_sf['funds']['TQQQ'].pop('shortfall_observed')
        vi2_miss_sf['funds']['SOXL']['v5_tolerance'] = 0.01
        r2c, _, st2c = self._eval(vi2_miss_sf, session='2026-01-06', prior={'V5': copy.deepcopy(prior_durability['V5'])})
        self.assertEqual(r2c['V5']['reason'], 'missing_input')
        self.assertEqual(r2c['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 39)
        self.assertEqual(st2c['V5']['TQQQ'], {'consecutive_beyond_tolerance': 39, 'escalated': False, 'last_session': '2026-01-05'})

        # 3. Leading/trailing whitespace on order symbol (' TQQQ ') still triggers V1/V4 fail-closed clamp (45000.0)
        vi3_ws = copy.deepcopy(self.normal_vi)
        vi3_ws.update({
            'proposed_exposure': 50000.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05,
            'account': 'synthetic_account_1', 'side': 'buy', 'symbol': ' TQQQ ',
            'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0, 'order_value': 50.0, 'settled_cash': 200.0,
            'quotes': {'TQQQ': {'quote_staleness': 0.05, 'spread_width': 0.0001, 'trading_pause': False, 'session_time': 'regular'}},
        })
        vi3_ws['funds'].pop('TQQQ')
        vi3_ws['funds']['SOXL']['v5_tolerance'] = 0.01
        r3_ws, eff3_ws, _ = self._eval(vi3_ws, session='2026-01-05')
        self.assertFalse(r3_ws['O5']['would_have_tripped'])
        self.assertEqual(eff3_ws['account'], 'NORMAL')
        self.assertEqual(eff3_ws['fund:TQQQ'], 'NO-NEW-RISK')
        self.assertEqual(compute_permitted_exposure(vi3_ws, r3_ws, eff3_ws), 45000.0)

    def test_r17_v5_same_day_missing_unresolved_invalid_does_not_poison_last_session(self):
        """R17 P1: Unevaluated V5 ticks without prior state must not write last_session and block same-session counting."""
        from datetime import date, timedelta

        for mode_name in ('missing_shortfall', 'unresolved_tol', 'invalid_tol'):
            v0 = copy.deepcopy(self.normal_vi)
            v0.update({'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
            v0['funds']['TQQQ']['v5_tolerance'] = 0.01
            v0['funds']['SOXL']['v5_tolerance'] = 0.01
            if mode_name == 'missing_shortfall':
                v0['funds']['TQQQ'].pop('shortfall_observed', None)
            elif mode_name == 'unresolved_tol':
                v0['v5_tolerance'] = None
                v0['funds']['TQQQ']['v5_tolerance'] = None
            else:
                v0['v5_tolerance'] = -0.01
                v0['funds']['TQQQ']['v5_tolerance'] = -0.01

            r0, _, st = self._eval(v0, session='2026-01-05', prior={})
            self.assertNotIn('TQQQ', st.get('V5', {}), f"{mode_name} must not record last_session without prior state")
            self.assertEqual(r0['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 0)

            d0 = date(2026, 1, 5)
            last_r = None
            for idx in range(40):
                sess = (d0 + timedelta(days=idx)).isoformat()
                vx = copy.deepcopy(self.normal_vi)
                vx.update({'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
                vx['funds']['TQQQ'].update({'v5_tolerance': 0.01, 'shortfall_observed': 0.05, 'shortfall_predicted': 0.01})
                vx['funds']['SOXL']['v5_tolerance'] = 0.01
                for sr in vx['source_records'].values():
                    sr['timestamp'] = f'{sess}T15:59:00Z'
                last_r, eff_last, st = self._eval(vx, session=sess, prior=st)
            self.assertEqual(last_r['V5']['state'], 'NO-NEW-RISK', msg=mode_name)
            self.assertEqual(last_r['V5']['outputs']['consecutive_sessions_beyond_tolerance'], 40, msg=mode_name)
            self.assertTrue(last_r['V5']['outputs']['escalated_to_v1'], msg=mode_name)
            self.assertEqual(eff_last['fund:TQQQ'], 'NO-NEW-RISK', msg=mode_name)
            self.assertEqual(st['V5']['TQQQ']['consecutive_beyond_tolerance'], 40, msg=mode_name)

        # V1-V4 without prior state: missing/invalid tick1 does not block same-session tick2 evaluation
        vi_m = copy.deepcopy(self.normal_vi)
        vi_m.update({'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi_m['funds']['TQQQ'].update({'index_return': None, 'forecast_volatility': None, 'corporate_action': 'bad'})
        vi_m['funds']['SOXL']['v5_tolerance'] = 0.01
        _, _, st_m = self._eval(vi_m, session='2026-01-05', prior={})
        self.assertNotIn('TQQQ', st_m.get('V1', {}))
        self.assertNotIn('TQQQ', st_m.get('V4', {}))

        vi_rec = copy.deepcopy(self.normal_vi)
        vi_rec.update({'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi_rec['funds']['TQQQ'].update({'forecast_volatility': 0.60, 'fund_event': 'liquidation'})
        vi_rec['funds']['SOXL']['v5_tolerance'] = 0.01
        r_rec, _, st_rec = self._eval(vi_rec, session='2026-01-05', prior=st_m)
        self.assertEqual(r_rec['V4']['state'], 'NO-NEW-RISK')
        self.assertEqual(st_rec['V4']['TQQQ']['clearing_counter'], 0)
        self.assertTrue(st_rec['V3']['TQQQ']['latched'])

    def test_r18_invalid_market_halt_level_and_o5_missing_order_direction_fail_closed(self):
        """R18 Codex: Invalid market_halt_level fails L5/L6 closed and active O5 orders require explicit buy/sell side."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        # 1. Invalid/malformed market_halt_level fails L5 (NO-NEW-RISK) and L6 (HALT, latched) closed
        for bad_mhl in ('3', 'unavailable', True, False, -1, 4, 1.5, float('nan'), float('inf'), ['1']):
            vi_mhl = copy.deepcopy(self.normal_vi)
            vi_mhl.update({
                'proposed_exposure': 45500.0, 'v5_tolerance': 0.01,
                'v7_spread_width': 0.02, 'o5_collar': 0.05, 'market_halt_level': bad_mhl,
            })
            vi_mhl['funds']['TQQQ']['v5_tolerance'] = 0.01
            vi_mhl['funds']['SOXL']['v5_tolerance'] = 0.01
            r_m, eff_m, st_m = self._eval(vi_mhl, session='2026-01-05')
            self.assertEqual(r_m['L5']['state'], 'NO-NEW-RISK', msg=repr(bad_mhl))
            self.assertTrue(r_m['L5']['would_have_tripped'], msg=repr(bad_mhl))
            self.assertEqual(r_m['L5']['reason'], 'invalid_input', msg=repr(bad_mhl))
            self.assertEqual(r_m['L6']['state'], 'HALT', msg=repr(bad_mhl))
            self.assertTrue(r_m['L6']['latched'], msg=repr(bad_mhl))
            self.assertEqual(r_m['L6']['reason'], 'invalid_input', msg=repr(bad_mhl))
            self.assertEqual(eff_m['account'], 'HALT', msg=repr(bad_mhl))
            self.assertEqual(compute_permitted_exposure(vi_mhl, r_m, eff_m), 0.0, msg=repr(bad_mhl))
            self.assertTrue(st_m['L6']['latched'], msg=repr(bad_mhl))

        # Valid market_halt_level=0 and None stay NORMAL; same-day L5 trip survives an intermediate invalid tick
        vi_zero = copy.deepcopy(self.normal_vi)
        vi_zero.update({
            'proposed_exposure': 45500.0, 'v5_tolerance': 0.01,
            'v7_spread_width': 0.02, 'o5_collar': 0.05, 'market_halt_level': 0,
        })
        vi_zero['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_zero['funds']['SOXL']['v5_tolerance'] = 0.01
        r_z, eff_z, _ = self._eval(vi_zero, session='2026-01-05')
        self.assertEqual(r_z['L5']['state'], 'NORMAL')
        self.assertEqual(r_z['L6']['state'], 'NORMAL')
        self.assertEqual(compute_permitted_exposure(vi_zero, r_z, eff_z), 45500.0)

        vi_l5_1 = copy.deepcopy(vi_zero)
        vi_l5_1['market_halt_level'] = 1
        _, _, st_l5 = self._eval(vi_l5_1, session='2026-01-05')
        vi_l5_bad = copy.deepcopy(vi_zero)
        vi_l5_bad['market_halt_level'] = 'unavailable'
        _, _, st_bad = self._eval(vi_l5_bad, session='2026-01-05', prior=st_l5)
        rearm_l6 = [{'type': 'rearm', 'row': 'L6', 'session': '2026-01-05'}]
        r_same, _, _ = self._eval(vi_zero, session='2026-01-05', prior=st_bad, events=rearm_l6)
        self.assertEqual(r_same['L6']['state'], 'NORMAL')
        self.assertEqual(r_same['L5']['state'], 'NO-NEW-RISK')
        self.assertEqual(r_same['L5']['reason'], 'clearing_period')

        # 2. Active order omitting direction aliases fails O5 closed -> clamps 45000 & latches HALT on 3rd reject
        for extra_side in ({}, {'side': None}, {'o5_side': None}):
            st_dir = {}
            for i in range(1, 4):
                vi_dir = copy.deepcopy(self.normal_vi)
                vi_dir.update({
                    'proposed_exposure': 45500.0, 'v5_tolerance': 0.01,
                    'v7_spread_width': 0.02, 'o5_collar': 0.05,
                    'o5_symbol': 'TQQQ', 'account': 'synthetic_account_1',
                    'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0,
                    'order_value': 50.0, 'settled_cash': 200.0,
                    **extra_side,
                })
                vi_dir['funds']['TQQQ']['v5_tolerance'] = 0.01
                vi_dir['funds']['SOXL']['v5_tolerance'] = 0.01
                r_d, eff_d, st_dir = self._eval(vi_dir, session='2026-01-05', prior=st_dir)
                self.assertTrue(r_d['O5']['would_have_tripped'])
                self.assertEqual(r_d['O5']['rejection_count_this_session'], i)
                if i < 3:
                    self.assertEqual(compute_permitted_exposure(vi_dir, r_d, eff_d), 45000.0)
                else:
                    self.assertEqual(r_d['O5']['state'], 'HALT')
                    self.assertTrue(r_d['O5']['latched'])
                    self.assertEqual(eff_d['account'], 'HALT')
                    self.assertEqual(compute_permitted_exposure(vi_dir, r_d, eff_d), 0.0)

    def test_r19_codex_prior_state_v3_malformed_event_and_o4_terminal_before_timeout(self):
        """R19 Codex: Malformed prior_row_state raises ValueError, malformed fund_event fails DE-RISK, and terminal O4 avoids timeout."""
        sys.path.insert(0, str(repo_root / 'tools'))
        from check_exposure_invariants import compute_permitted_exposure

        # 1. None prior_row_state works; non-None non-dict prior_row_state fails closed via ValueError
        vi_ok = copy.deepcopy(self.normal_vi)
        vi_ok.update({'proposed_exposure': 45500.0, 'v5_tolerance': 0.01, 'v7_spread_width': 0.02, 'o5_collar': 0.05})
        vi_ok['funds']['TQQQ']['v5_tolerance'] = 0.01
        vi_ok['funds']['SOXL']['v5_tolerance'] = 0.01
        r_none, _, _ = engine.evaluate(
            'fuse-eval-spec/v1', 'test-hash', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi_ok, None, [],
        )
        self.assertEqual(r_none['O6']['state'], 'NORMAL')
        for bad_pr in ('unavailable', ['O6'], 123, True):
            with self.assertRaises(ValueError, msg=repr(bad_pr)):
                engine.evaluate(
                    'fuse-eval-spec/v1', 'test-hash', 'registered_policy_hash_v1',
                    '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi_ok, bad_pr, [],
                )

        # 2. Malformed/unrecognized fund_event fails V3 closed (DE-RISK, latched) and blocks exposure raises
        for bad_fe in ('unavailable', {'type': 'liquidation'}, '', 123, True):
            vi_fe = copy.deepcopy(vi_ok)
            vi_fe.update({
                'symbol': 'TQQQ', 'side': 'buy', 'account': 'synthetic_account_1',
                'order_size': 1, 'unit_price': 50.0, 'o5_reference_price': 50.0,
                'order_value': 50.0, 'settled_cash': 200.0,
            })
            vi_fe['funds']['TQQQ']['fund_event'] = bad_fe
            r_fe, eff_fe, st_fe = self._eval(vi_fe, session='2026-01-05')
            self.assertEqual(r_fe['V3']['state'], 'DE-RISK', msg=repr(bad_fe))
            self.assertTrue(r_fe['V3']['latched'], msg=repr(bad_fe))
            self.assertEqual(r_fe['V3']['reason'], 'invalid_input', msg=repr(bad_fe))
            self.assertEqual(eff_fe['fund:TQQQ'], 'DE-RISK', msg=repr(bad_fe))
            self.assertTrue(st_fe['V3']['TQQQ']['latched'], msg=repr(bad_fe))
            self.assertEqual(compute_permitted_exposure(vi_fe, r_fe, eff_fe), 45000.0, msg=repr(bad_fe))

            # When all funds carry bad fund_event, permitted exposure drops to 0.0
            vi_fe_all = copy.deepcopy(vi_fe)
            vi_fe_all['funds']['SOXL']['fund_event'] = bad_fe
            r_all, eff_all, _ = self._eval(vi_fe_all, session='2026-01-05')
            self.assertEqual(compute_permitted_exposure(vi_fe_all, r_all, eff_all), 0.0, msg=repr(bad_fe))

        # 3. O4 order already in recognized terminal status does not oscillate ORDER-UNKNOWN <-> NORMAL when timeout=True
        for term_status in ('filled', 'cancelled', 'canceled', 'rejected', 'expired'):
            vi_o4 = copy.deepcopy(vi_ok)
            vi_o4['pending_orders'] = {'TQQQ': {'order_id': 'synthetic_order_1', 'status': term_status, 'timeout': True}}
            r_t1, eff_t1, st_t1 = self._eval(vi_o4, session='2026-01-05', prior={})
            r_t2, eff_t2, st_t2 = self._eval(vi_o4, session='2026-01-05', prior=st_t1)
            self.assertEqual(r_t1['O4']['state'], 'NORMAL', msg=term_status)
            self.assertFalse(r_t1['O4']['would_have_tripped'], msg=term_status)
            self.assertEqual(r_t2['O4']['state'], 'NORMAL', msg=term_status)
            self.assertNotIn('TQQQ', st_t1.get('O4', {}), msg=term_status)
            self.assertNotIn('TQQQ', st_t2.get('O4', {}), msg=term_status)
            self.assertEqual(compute_permitted_exposure(vi_o4, r_t1, eff_t1), 45500.0, msg=term_status)
            self.assertEqual(compute_permitted_exposure(vi_o4, r_t2, eff_t2), 45500.0, msg=term_status)

        # Without valid order_id, status='filled' + timeout=True still fails closed as unidentified_order
        vi_o4_noid = copy.deepcopy(vi_ok)
        vi_o4_noid['pending_orders'] = {'TQQQ': {'status': 'filled', 'timeout': True}}
        r_noid, eff_noid, st_noid = self._eval(vi_o4_noid, session='2026-01-05')
        self.assertEqual(r_noid['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(eff_noid['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st_noid['O4']['TQQQ']['original_order_id'], 'unidentified_order_TQQQ')

        # Active prior O4 order A still rejects terminal status for different order B, and clears on terminal A
        prior_o4_a = {'O4': {'TQQQ': {'original_order_id': 'order_A', 'status': 'unknown'}}}
        vi_b = copy.deepcopy(vi_ok)
        vi_b['pending_orders'] = {'TQQQ': {'order_id': 'order_B', 'status': 'filled', 'timeout': True}}
        r_b, eff_b, st_b = self._eval(vi_b, session='2026-01-05', prior=prior_o4_a)
        self.assertEqual(r_b['O4']['state'], 'ORDER-UNKNOWN')
        self.assertEqual(eff_b['symbol:TQQQ'], 'ORDER-UNKNOWN')
        self.assertEqual(st_b['O4']['TQQQ']['original_order_id'], 'order_A')

        vi_a = copy.deepcopy(vi_ok)
        vi_a['pending_orders'] = {'TQQQ': {'order_id': 'order_A', 'status': 'filled', 'timeout': True}}
        r_a, eff_a, st_a = self._eval(vi_a, session='2026-01-05', prior=st_b)
        self.assertEqual(r_a['O4']['state'], 'NORMAL')
        self.assertEqual(r_a['O4']['reason'], 'original_order_terminal_status_received')
        self.assertEqual(eff_a['symbol:TQQQ'], 'NORMAL')
        self.assertEqual(st_a.get('O4', {}), {})


if __name__ == '__main__':
    unittest.main()
