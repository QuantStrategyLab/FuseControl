"""Vehicle breaker rows V1-V7 per BRIEF-FUSE-1 §4.3 Table B.

All vehicle rows operate on 3× daily-reset funds.
Thresholds per §4.5 disposition register.
"""

import math
from typing import Any, Dict, Optional
from . import state as st
from . import canonical_state as cst
from .canonical import finite_float as _is_valid_finite_number


def evaluate_V1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str,
                session: Optional[str] = None, market_closed: bool = False) -> Dict[str, Any]:
    """V1: Tracking deviation exceeds thresholds → NO-NEW-RISK in that fund.

    Kind: breaker
    Scope: fund
    State contribution: NO-NEW-RISK
    Clearing: Owner re-arms after reconciliation
    Required inputs: fund_return, index_return, modelled_fee, modelled_financing
    Proposal thresholds per §4.5: 0.75pp (1 session), 2.0pp (5 sessions)
    """
    # Check for prior latch from canonical format (SUC-13)
    scope = f'fund:{fund}'
    prior_latch = cst.get_v1_latch(prior_state, fund)
    prior_history = cst.get_v1_history(prior_state, fund)
    if prior_latch:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            # Handle both list and dict formats
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get(scope, [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'V1' or event.get('row_id') == 'V1'):
                    # Also check fund match if specified
                    if 'fund' in event and event['fund'] != fund:
                        continue
                    rearm = True
                    break

        if rearm:
            # Q4 short-circuit: re-arm wins, return authorized_rearm WITHOUT re-evaluating
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'breaker',
                'latched': False,
                'reason': 'authorized_rearm',
                'fund': fund
            }

        # Stay latched without re-arm
        res = {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'latched_prior_trip',
            'fund': fund
        }
        if prior_history:
            res['_session_returns'] = [dict(item) for item in prior_history]
        return res

    # On closed/holiday market days there is no trading session return; preserve rolling 5-session history
    if market_closed:
        res = {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }
        if prior_history:
            res['_session_returns'] = [dict(item) for item in prior_history]
        return res

    # Calculate one-session deviation from fund inputs
    raw_fund_return = inputs.get('fund_return')
    raw_index_return = inputs.get('index_return')
    raw_fee = inputs.get('modelled_fee')
    raw_financing = inputs.get('modelled_financing')
    sessions_window = inputs.get('sessions_window')

    fund_return = _is_valid_finite_number(raw_fund_return)
    index_return = _is_valid_finite_number(raw_index_return)
    modelled_fee = _is_valid_finite_number(raw_fee)
    modelled_financing = _is_valid_finite_number(raw_financing)

    if (fund_return is None or index_return is None or
            modelled_fee is None or modelled_financing is None):
        res = {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'missing_input',
            'fund': fund
        }
        if prior_history:
            res['_session_returns'] = [dict(item) for item in prior_history]
        return res

    if sessions_window is not None and (
            isinstance(sessions_window, bool) or
            not isinstance(sessions_window, int) or
            sessions_window not in (1, 5)):
        res = {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'missing_input',
            'fund': fund
        }
        if prior_history:
            res['_session_returns'] = [dict(item) for item in prior_history]
        return res

    # Calculate one-session deviation: actual - (3× index - fee - financing)
    expected_return = 3.0 * index_return - modelled_fee - modelled_financing
    one_session_dev = fund_return - expected_return

    # Always maintain rolling 5-session history across valid observations (§4.3 / A06);
    # an empty caller five_session_history=[] must never wipe real prior_row_state history.
    explicit_history = inputs.get('five_session_history')
    curr_entry = {
        'session': session,
        'fund_return': fund_return,
        'expected_return': expected_return,
    }
    if prior_history:
        updated_history = [dict(item) for item in prior_history]
    elif isinstance(explicit_history, list) and explicit_history:
        parsed = []
        for entry in explicit_history:
            if isinstance(entry, dict):
                fr = _is_valid_finite_number(entry.get('fund_return'))
                ir = _is_valid_finite_number(entry.get('index_return'))
                mf = _is_valid_finite_number(entry.get('modelled_fee', 0.0))
                mfin = _is_valid_finite_number(entry.get('modelled_financing', 0.0))
                if fr is not None and ir is not None and mf is not None and mfin is not None:
                    parsed.append({
                        'session': entry.get('session'),
                        'fund_return': fr,
                        'expected_return': 3.0 * ir - mf - mfin
                    })
        updated_history = parsed[-5:]
    else:
        updated_history = []

    if session is not None and any(item.get('session') == session for item in updated_history):
        updated_history = [curr_entry if item.get('session') == session else item for item in updated_history]
    elif not (len(updated_history) == 5 and isinstance(explicit_history, list) and explicit_history and not prior_history):
        updated_history.append(curr_entry)
    updated_history = updated_history[-5:]

    # Thresholds per §4.5 (proposal values)
    one_session_threshold = 0.0075  # 0.75 pp
    five_session_threshold = 0.020  # 2.0 pp

    # One-session trigger check
    if abs(one_session_dev) > one_session_threshold:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'tracking_deviation_exceeds_0_75pp',
            'deviation': abs(one_session_dev),
            'fund': fund,
            '_session_returns': updated_history,
        }

    # Five-session branch per §4.3 / §4.5 / §6
    if len(updated_history) < 5:
        if sessions_window == 5:
            # Caller requested explicit 5-session evaluation before 5 sessions accumulated
            return {
                'state': 'NO-NEW-RISK',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': False,
                'reason': 'missing_input',
                'fund': fund,
                '_session_returns': updated_history,
            }
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'fund': fund,
            '_session_returns': updated_history,
        }

    comp_fund = math.prod(1.0 + item['fund_return'] for item in updated_history) - 1.0
    comp_expected = math.prod(1.0 + item['expected_return'] for item in updated_history) - 1.0
    five_session_dev = comp_fund - comp_expected
    if abs(five_session_dev) > five_session_threshold:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'tracking_deviation_exceeds_2_0pp',
            'deviation': round(abs(five_session_dev), 12),
            'fund': fund,
            '_session_returns': updated_history,
        }
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none',
        'fund': fund,
        '_session_returns': updated_history,
    }


def evaluate_V2(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str) -> Dict[str, Any]:
    """V2: Corporate action → HALT until adjusted and reconciled.

    Kind: interlock_or_breaker
    Scope: fund
    State contribution: HALT
    Clearing: Auto-clears ONLY if adjustment complete AND exact reconciliation;
             otherwise latches and needs re-arm
    Mechanism B1: pending adjustment state must persist correctly
    """
    scope = f'fund:{fund}'

    # Check for prior mismatch latch (canonical format per Q6)
    prior_mismatch = cst.get_v2_latched_mismatch(prior_state, fund)
    if prior_mismatch:
        # Latched mismatch - only owner can re-arm
        rearm = False
        if authorized_events:
            # Handle both list and dict formats
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get(scope, [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'V2' or event.get('row_id') == 'V2'):
                    # Also check fund match if specified
                    if 'fund' in event and event['fund'] != fund:
                        continue
                    rearm = True
                    break

        if not rearm:
            # Stay latched
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': True,
                'reason': 'latched_prior_mismatch',
                'fund': fund
            }
        else:
            # Re-armed - clear the latch
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'authorized_rearm',
                'fund': fund
            }

    # Check for pending adjustment from prior state (B1 - canonical format per Q6)
    prior_pending = cst.get_v2_pending_adjustment(prior_state, fund)

    # Get current corporate action input
    corporate_action = inputs.get('corporate_action')

    # Fail closed on malformed action when there's NO prior pending (B1 control)
    if corporate_action is not None and not isinstance(corporate_action, dict):
        # Malformed - fail closed with HALT
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': 'missing_input',
            'fund': fund
        }

    # If action is dict, validate required fields
    if isinstance(corporate_action, dict):
        # Empty {} while pending stays carried HALT without dropping pending state (A07/A12)
        if not corporate_action and prior_pending:
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'pending_corporate_action_carried',
                'fund': fund
            }

        action_type = corporate_action.get('type')
        if action_type is None:
            # Malformed - fail closed with HALT
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'missing_input',
                'fund': fund
            }

        raw_adj_complete = corporate_action.get('adjustment_complete', False)
        raw_exact_rec = corporate_action.get('exact_reconciliation', False)
        if not isinstance(raw_adj_complete, bool) or not isinstance(raw_exact_rec, bool):
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': True,
                'reason': 'reconciliation_mismatch',
                'fund': fund
            }
        adjustment_complete = raw_adj_complete is True
        exact_reconciliation = raw_exact_rec is True

        # R3 / A12 / R4: Exact reconciliation requires matching ledger/broker values,
        # matching share_count == broker_position, exact boolean flags, uncompromised HWM,
        # and exact action type + known ratio matching pending event(s).
        if adjustment_complete:
            ledger_val = _is_valid_finite_number(inputs.get('ledger_value'))
            broker_val = _is_valid_finite_number(inputs.get('broker_value'))
            share_count = _is_valid_finite_number(inputs.get('share_count'))
            broker_pos = _is_valid_finite_number(inputs.get('broker_position'))

            amounts_match = (
                ledger_val is not None and
                broker_val is not None and
                ledger_val == broker_val and
                share_count is not None and
                broker_pos is not None and
                share_count == broker_pos
            )
            hwm_ok = (
                corporate_action.get('hwm_adjusted') is not False and
                inputs.get('hwm_adjusted') is not False
            )

            def _item_matches(item: Dict[str, Any], a_type: Any, c_ratio: Any) -> bool:
                if item.get('type') != a_type:
                    return False
                p_ratio = item.get('ratio')
                if p_ratio is None:
                    return True
                p_ratio_num = _is_valid_finite_number(p_ratio)
                c_ratio_num = _is_valid_finite_number(c_ratio)
                return (
                    p_ratio_num is not None and
                    c_ratio_num is not None and
                    c_ratio_num == p_ratio_num
                )

            curr_ratio = corporate_action.get('ratio')
            if exact_reconciliation and amounts_match and hwm_ok:
                if prior_pending:
                    queued_actions = prior_pending.get('queued_actions') or []
                    if _item_matches(prior_pending, action_type, curr_ratio):
                        if not queued_actions:
                            return {
                                'state': 'NORMAL',
                                'would_have_tripped': False,
                                'kind': 'interlock_or_breaker',
                                'latched': False,
                                'reason': 'exact_reconciliation_auto_clear',
                                'fund': fund
                            }
                        return {
                            'state': 'HALT',
                            'would_have_tripped': True,
                            'kind': 'interlock_or_breaker',
                            'latched': False,
                            'reason': 'pending_corporate_action_carried',
                            'fund': fund,
                            '_v2_reconcile_target': 'primary'
                        }
                    matched_q_idx = next(
                        (idx for idx, q in enumerate(queued_actions)
                         if isinstance(q, dict) and _item_matches(q, action_type, curr_ratio)),
                        None
                    )
                    if matched_q_idx is not None:
                        return {
                            'state': 'HALT',
                            'would_have_tripped': True,
                            'kind': 'interlock_or_breaker',
                            'latched': False,
                            'reason': 'pending_corporate_action_carried',
                            'fund': fund,
                            '_v2_reconcile_target': ('queued', matched_q_idx)
                        }
                else:
                    return {
                        'state': 'NORMAL',
                        'would_have_tripped': False,
                        'kind': 'interlock_or_breaker',
                        'latched': False,
                        'reason': 'none',
                        'fund': fund
                    }

            # Adjustment complete without complete matching reconciliation latches HALT
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': True,
                'reason': 'reconciliation_mismatch',
                'fund': fund
            }

        # Action announced or detected -> pending HALT (never overwrite unresolved prior action!)
        if prior_pending:
            reason = 'pending_corporate_action_carried'
        else:
            reason = 'pending_corporate_action'

        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': reason,
            'fund': fund
        }

    # No current action - check for pending from prior (B1)
    if prior_pending:
        # Pending action still outstanding - remain HALT
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': 'pending_corporate_action_carried',
            'fund': fund
        }

    # No action, no pending
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock_or_breaker',
        'latched': False,
        'reason': 'none',
        'fund': fund
    }


def evaluate_V3(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str) -> Dict[str, Any]:
    """V3: Fund event → DE-RISK in that fund.

    Kind: breaker
    Scope: fund
    State contribution: DE-RISK
    Clearing: Owner decides
    """
    scope = f'fund:{fund}'

    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_fund_latch(prior_state, 'V3', fund)
    if prior_latch:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            # Handle both list and dict formats
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get(scope, [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'V3' or event.get('row_id') == 'V3'):
                    if 'fund' in event and event['fund'] != fund:
                        continue
                    rearm = True
                    break

        if rearm:
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'breaker',
                'latched': False,
                'reason': 'authorized_rearm',
                'fund': fund
            }

        # Stay latched
        return {
            'state': 'DE-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'latched_prior_trip',
            'fund': fund
        }

    # Evaluate trigger
    fund_event = inputs.get('fund_event')

    # null fund_event = no event (benign)
    if fund_event is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }

    # Check for triggering events
    if fund_event in ['liquidation', 'multiple_change', 'objective_change',
                      'suspended_creations', 'exchange_halt', 'delisting']:
        return {
            'state': 'DE-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'fund_event',
            'fund': fund
        }

    # No triggering event
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none',
        'fund': fund
    }


def evaluate_V4(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str, session: str,
                market_closed: bool = False) -> Dict[str, Any]:
    """V4: Extreme volatility → NO-NEW-RISK in that fund.

    Kind: interlock
    Scope: fund
    State contribution: NO-NEW-RISK
    Clearing: Clears after ten sessions below the level
    Mechanism B4: clearing counter increments at most once per session (canonical format per Q6)
    """
    # Get prior V4 state from canonical format
    v4_state = cst.get_v4_state(prior_state, fund)
    clearing_count = v4_state['clearing_counter']
    last_session_below = v4_state['last_session_below_threshold']

    # Treat None (absent) as 0 for inactive, but present 0 means active after trip (flag 3)
    if clearing_count is None:
        clearing_count = 0
        is_active = False
    else:
        is_active = True

    # Evaluate trigger using forecast_volatility from fund inputs
    forecast_volatility = _is_valid_finite_number(inputs.get('forecast_volatility'))
    long_run_volatility = _is_valid_finite_number(inputs.get('long_run_volatility'))

    # Fail closed on missing, NaN, inf, or non-positive volatility inputs
    if (forecast_volatility is None or long_run_volatility is None or
            forecast_volatility < 0 or long_run_volatility <= 0):
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input',
            'fund': fund
        }

    # Threshold per §4.5 (proposal: 2× long-run)
    threshold = 2.0 * long_run_volatility

    # Check trigger
    triggered = forecast_volatility >= threshold

    if triggered:
        # Trip - reset clearing counter (SUC-06 step 1)
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'volatility_at_or_above_2x',
            'fund': fund,
            'outputs': {'clearing_counter': 0}
        }

    # Not triggered - check if we're in clearing mode
    # Only in clearing if active (prior trip exists, even if count=0)
    if not is_active:
        # Never tripped, benign
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'interlock',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }

    # Closed/holiday sessions do not count toward the 10-session clearing counter
    if market_closed:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'volatility_below_2x_but_not_yet_cleared',
            'fund': fund,
            'outputs': {'clearing_counter': clearing_count},
            '_preserve_prior_v4_session': True,
        }

    # In clearing mode - check progress (B4: increment at most once per session)
    if last_session_below == session:
        # Already counted this session - don't increment
        new_count = clearing_count
    else:
        # Different session - safe to increment
        new_count = clearing_count + 1

    if new_count >= 10:
        # Cleared (SUC-06 step 6) - report 10, caller will remove entry
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'interlock',
            'latched': False,
            'reason': 'cleared_after_ten_sessions',
            'fund': fund,
            'outputs': {'clearing_counter': 10}
        }

    # Still clearing (SUC-06 steps 2-4) - emit counter at outputs.clearing_counter per Q1
    return {
        'state': 'NO-NEW-RISK',
        'would_have_tripped': True,
        'kind': 'interlock',
        'latched': False,
        'reason': 'volatility_below_2x_but_not_yet_cleared',
        'fund': fund,
        'outputs': {'clearing_counter': new_count}
        }


def evaluate_V5(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str, session: str) -> Dict[str, Any]:
    """V5: Decay monitor → notify; if persists for 40 sessions, escalate to V1.

    Kind: diagnostic (with stateful escalation)
    Scope: fund
    State contribution: Diagnostic only until escalation; then NO-NEW-RISK
    Clearing: Diagnostic (stateful escalation)
    Mechanism B5: persistence counter counts DISTINCT sessions (canonical format per Q6)
                  escalates to V1 treatment at 40 sessions
    """
    # Get prior V5 state from canonical format (flag 4 - includes session identity)
    v5_state = cst.get_v5_state(prior_state, fund)
    persistence_count = v5_state['consecutive_beyond_tolerance']
    prior_escalated = v5_state['escalated']
    last_session = v5_state['last_session']

    # Calculate excess shortfall from fund inputs
    shortfall_observed = inputs.get('shortfall_observed')
    shortfall_predicted = inputs.get('shortfall_predicted')
    v5_tolerance = inputs.get('v5_tolerance')  # From validated_inputs if supplied

    # If tolerance unresolved, treat as unresolved (not missing data)
    if v5_tolerance is None or v5_tolerance == 'unresolved':
        # Unresolved tolerance - diagnostic only, no escalation (Fix 2)
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'diagnostic',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'fund': fund,
            'outputs': {
                'excess_shortfall': None,
                'consecutive_sessions_beyond_tolerance': 0,
                'escalated_to_v1': False,
                'disposition': 'UNRESOLVED-FAIL-CLOSED'
            }
        }

    # A11: Fail closed on NaN/inf/bool/negative v5_tolerance
    tol_val = _is_valid_finite_number(v5_tolerance)
    if tol_val is None or tol_val < 0.0:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'diagnostic',
            'latched': False,
            'reason': 'invalid_input',
            'fund': fund,
            'outputs': {
                'excess_shortfall': None,
                'consecutive_sessions_beyond_tolerance': 0,
                'escalated_to_v1': False,
                'disposition': 'UNRESOLVED-FAIL-CLOSED'
            }
        }

    obs_val = _is_valid_finite_number(shortfall_observed)
    pred_val = _is_valid_finite_number(shortfall_predicted)
    if obs_val is None or pred_val is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'diagnostic',
            'latched': False,
            'reason': 'missing_input',
            'fund': fund,
            'outputs': {
                'excess_shortfall': 0.0,
                'consecutive_sessions_beyond_tolerance': 0,
                'escalated_to_v1': False,
                'disposition': 'missing_data' if (shortfall_observed is None or shortfall_predicted is None) else 'invalid_data'
            }
        }

    v5_tolerance = tol_val
    shortfall_observed = obs_val
    shortfall_predicted = pred_val

    # Calculate excess shortfall
    excess_shortfall = shortfall_observed - shortfall_predicted

    # Check if beyond tolerance
    beyond_tolerance = excess_shortfall > v5_tolerance

    # B5: Count DISTINCT sessions - duplicate evaluations in same session don't double-count
    if beyond_tolerance:
        if last_session == session:
            # Same session - don't increment (session deduplication per Q6)
            new_count = persistence_count
        else:
            # New session - increment
            new_count = persistence_count + 1
    else:
        # Reset counter
        new_count = 0

    # B5: Escalate to V1 treatment at 40 sessions (two months per §4.3)
    escalated = new_count >= 40

    # Determine state contribution (SUC-08: reason strings, V5 is diagnostic-only until escalation)
    if escalated:
        state = 'NO-NEW-RISK'
        disposition = 'escalated_to_v1'
        reason = 'escalated_to_v1_treatment'
    elif beyond_tolerance:
        state = 'NORMAL'  # Diagnostic state is NORMAL (not 'none')
        disposition = 'beyond_tolerance'
        reason = 'excess_beyond_tolerance'
    else:
        state = 'NORMAL'
        disposition = 'benign'
        reason = 'none'

    return {
        'state': state,
        'would_have_tripped': beyond_tolerance or escalated,
        'kind': 'diagnostic',
        'latched': False,
        'reason': reason,
        'fund': fund,
        'outputs': {
            'excess_shortfall': excess_shortfall,
            'consecutive_sessions_beyond_tolerance': new_count,
            'escalated_to_v1': escalated,
            'disposition': disposition
        }
    }


def evaluate_V6(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str) -> Dict[str, Any]:
    """V6: Carrying cost exceeds threshold → notify.

    Spec §4.3 / DERIVATION.md: carrying_cost_measured > (excess_return_shrunk / 4).
    Kind: diagnostic
    Scope: fund
    State contribution: Diagnostic only (notify)
    """
    raw_spec_cost = inputs.get('carrying_cost_measured', inputs.get('carrying_cost_per_unit_exposure'))
    raw_spec_excess = inputs.get('excess_return_shrunk', inputs.get('shrunk_excess_return'))
    raw_v6_cost = inputs.get('v6_cost_per_unit_exposure')
    raw_v6_threshold = inputs.get('v6_threshold')

    # Canonical spec fields take precedence over any synthetic threshold override
    if raw_spec_cost is not None or raw_spec_excess is not None:
        cost_val = _is_valid_finite_number(raw_spec_cost)
        excess_val = _is_valid_finite_number(raw_spec_excess)
        if cost_val is None or excess_val is None or cost_val < 0.0 or excess_val < 0.0:
            return {
                'state': 'NORMAL',
                'would_have_tripped': True,
                'kind': 'diagnostic',
                'latched': False,
                'reason': 'missing_input',
                'fund': fund,
                'outputs': {
                    'cost_per_unit_exposure': 0.0,
                    'threshold': 0.0,
                    'exceeded': True,
                    'notify': True
                }
            }

        threshold = excess_val / 4.0
        exceeded = cost_val > threshold
        if exceeded:
            return {
                'state': 'NORMAL',
                'would_have_tripped': True,
                'kind': 'diagnostic',
                'latched': False,
                'reason': 'carrying_cost_exceeded',
                'fund': fund,
                'outputs': {
                    'cost_per_unit_exposure': cost_val,
                    'threshold': threshold,
                    'exceeded': True,
                    'notify': True
                }
            }

        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'diagnostic',
            'latched': False,
            'reason': 'none',
            'fund': fund,
            'outputs': {
                'cost_per_unit_exposure': None,
                'threshold': None,
                'exceeded': False,
                'notify': False
            }
        }

    # Synthetic direct threshold mode (only when canonical spec fields are absent)
    if raw_v6_cost is not None or raw_v6_threshold is not None:
        cost_val = _is_valid_finite_number(raw_v6_cost)
        thresh_val = _is_valid_finite_number(raw_v6_threshold)
        if cost_val is None or thresh_val is None or cost_val < 0.0 or thresh_val < 0.0:
            return {
                'state': 'NORMAL',
                'would_have_tripped': True,
                'kind': 'diagnostic',
                'latched': False,
                'reason': 'missing_input',
                'fund': fund,
                'outputs': {
                    'cost_per_unit_exposure': 0.0,
                    'threshold': 0.0,
                    'exceeded': True,
                    'notify': True
                }
            }
        exceeded = cost_val > thresh_val
        return {
            'state': 'NORMAL',
            'would_have_tripped': exceeded,
            'kind': 'diagnostic',
            'latched': False,
            'reason': 'carrying_cost_exceeded' if exceeded else 'none',
            'fund': fund,
            'outputs': {
                'cost_per_unit_exposure': cost_val,
                'threshold': thresh_val,
                'exceeded': exceeded,
                'notify': exceeded
            }
        }

    # Both canonical and synthetic inputs absent: fail closed while keeping stub-compatible output types
    return {
        'state': 'NORMAL',
        'would_have_tripped': True,
        'kind': 'diagnostic',
        'latched': False,
        'reason': 'missing_input',
        'fund': fund,
        'outputs': {
            'cost_per_unit_exposure': None,
            'threshold': None,
            'exceeded': True,
            'notify': True
        }
    }


def evaluate_V7(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str) -> Dict[str, Any]:
    """V7: Quote/liquidity issues → order not sent.

    Kind: interlock
    Scope: symbol
    State contribution: Order suppression (no control state)
    Clearing: Automatic when condition clears
    Required inputs: v7_spread_width parameter (from policy, or fail closed if unresolved)
    """
    # Get quote/liquidity indicators from fund inputs
    quote_staleness = inputs.get('quote_staleness')
    spread_width = inputs.get('spread_width')
    trading_pause = inputs.get('trading_pause', False)
    session_time = inputs.get('session_time')

    # Get spread width threshold from policy (unresolved per §4.5)
    v7_spread_width_threshold = inputs.get('v7_spread_width')

    # Fail closed on unresolved spread width threshold
    if v7_spread_width_threshold is None or v7_spread_width_threshold == 'unresolved':
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'fund': fund
        }

    # A11: Fail closed on NaN/inf/bool/negative v7_spread_width threshold
    thresh_val = _is_valid_finite_number(v7_spread_width_threshold)
    if thresh_val is None or thresh_val < 0.0:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'invalid_input',
            'fund': fund
        }

    # Fail closed if quote_staleness or spread_width is missing, non-finite, or negative
    qs_val = _is_valid_finite_number(quote_staleness)
    sw_val = _is_valid_finite_number(spread_width)
    if qs_val is None or sw_val is None or qs_val < 0.0 or sw_val < 0.0:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input' if (quote_staleness is None or spread_width is None) else 'quote_or_liquidity_issue',
            'fund': fund
        }

    quote_stale = qs_val > 1.0
    spread_too_wide = sw_val > thresh_val

    # Check if outside regular session
    outside_regular_session = session_time != 'regular'

    # Check any trigger
    triggered = (quote_stale or spread_too_wide or trading_pause or outside_regular_session)

    if triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'quote_or_liquidity_issue',
            'fund': fund
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock',
        'latched': False,
        'reason': 'none',
        'fund': fund
    }
