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
        vi_bil.update({'o5_collar': 0.05, 'o5_account': 'synthetic_account_1', 'o5_symbol': 'BIL'})
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
            vi_sell.update({'o5_collar': 0.05, 'o5_side': 'sell', 'o5_symbol': 'TQQQ', 'qty': 1, 'settled_cash': 0.0})
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
        vi_sc_win.update({'o5_collar': 0.05, 'o5_side': 'buy', 'settled_cash': 200.0, 'o5_settled_cash': 0.0, 'o5_order_value': 100.0})
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


if __name__ == '__main__':
    unittest.main()
