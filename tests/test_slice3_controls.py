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

        # Authorized re-arm clears O7 latch cleanly
        vi3 = copy.deepcopy(self.normal_vi)
        vi3.update({'last_heartbeat': '2026-01-15T15:59:30Z', 'scheduled_interval': 3600})
        rows3, eff3, st3 = self._eval(vi3, session='2026-01-15', prior=st2, events=[{'type': 'rearm', 'row_id': 'O7'}])
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


if __name__ == '__main__':
    unittest.main()
