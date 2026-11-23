"""Vehicle breaker rows V1-V7 per BRIEF-FUSE-1 §4.3 Table B.

All vehicle rows operate on 3× daily-reset funds.
Thresholds per §4.5 disposition register.
"""

from typing import Any, Dict, Optional
from . import state as st
from . import canonical_state as cst


def evaluate_V1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str) -> Dict[str, Any]:
    """V1: Tracking deviation exceeds thresholds → NO-NEW-RISK in that fund.

    Kind: breaker
    Scope: fund
    State contribution: NO-NEW-RISK
    Clearing: Owner re-arms after reconciliation
    Required inputs: fund_return, index_return, modelled_fee, modelled_financing
    Proposal thresholds per §4.5: 0.75pp (1 session), 2.0pp (5 sessions)
    """
    # Check for prior latch
    scope = f'fund:{fund}'
    prior_latch = st.get_latch(prior_state, 'V1', scope)
    if prior_latch and prior_latch['latched']:
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

        if not rearm:
            # Stay latched
            return {
                'state': 'NO-NEW-RISK',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip',
                'fund': fund
            }

    # Calculate one-session deviation from fund inputs
    fund_return = inputs.get('fund_return')
    index_return = inputs.get('index_return')
    modelled_fee = inputs.get('modelled_fee')
    modelled_financing = inputs.get('modelled_financing')

    # Event-trigger rows don't fail closed on missing inputs (Fix 4):
    # V1 requires affirmative evidence of tracking deviation exceeding threshold;
    # O1 carries the data-integrity trip for missing inputs
    if (fund_return is None or index_return is None or
        modelled_fee is None or modelled_financing is None):
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }

    try:
        fund_return = float(fund_return)
        index_return = float(index_return)
        modelled_fee = float(modelled_fee)
        modelled_financing = float(modelled_financing)
    except (TypeError, ValueError):
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }

    # Calculate one-session deviation: actual - (3× index - fee - financing)
    expected_return = 3.0 * index_return - modelled_fee - modelled_financing
    one_session_dev = fund_return - expected_return

    # For now, assume five-session deviation not available (would need history)
    # Treat as unresolved - only check one-session
    five_session_dev = None

    # Thresholds per §4.5 (proposal values)
    one_session_threshold = 0.0075  # 0.75 pp
    five_session_threshold = 0.020  # 2.0 pp

    # Check triggers (only one-session for now)
    triggered = abs(one_session_dev) > one_session_threshold
    if five_session_dev is not None:
        triggered = triggered or abs(five_session_dev) > five_session_threshold

    if not triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }

    # Trip and latch (SUC-13: specific reason string)
    return {
        'state': 'NO-NEW-RISK',
        'would_have_tripped': True,
        'kind': 'breaker',
        'latched': True,
        'reason': 'tracking_deviation_exceeds_0_75pp',
        'fund': fund
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

    # Check for prior mismatch latch
    # B1: Check BOTH standard latch format AND custom latched_mismatches format (SUC-02)
    prior_latch = st.get_latch(prior_state, 'V2', scope)
    has_standard_latch = prior_latch and prior_latch['latched']

    # Also check for latched_mismatches (custom V2 format)
    prior_v2 = prior_state.get('V2', {}) if prior_state else {}
    prior_mismatches = prior_v2.get('latched_mismatches', {})
    has_mismatch_latch = fund in prior_mismatches

    if has_standard_latch or has_mismatch_latch:
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

        adjustment_complete = corporate_action.get('adjustment_complete', False)
        exact_reconciliation = corporate_action.get('exact_reconciliation', False)

        # If adjustment complete and exact reconciliation, auto-clear (SUC-01 step 3)
        if adjustment_complete and exact_reconciliation and prior_pending:
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'exact_reconciliation_auto_clear',
                'fund': fund
            }
        elif adjustment_complete and exact_reconciliation:
            # No prior pending - benign
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'none',
                'fund': fund
            }

        # If adjustment complete but NOT exact reconciliation, latch
        if adjustment_complete and not exact_reconciliation:
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': True,
                'reason': 'reconciliation_mismatch',
                'fund': fund
            }

        # Action announced or detected → pending HALT (Fix 3: reason without fund suffix)
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': 'pending_corporate_action',
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

    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'V3', scope)
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            # Handle both list and dict formats
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get(scope, [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'V3' or event.get('row_id') == 'V3'):
                    rearm = True
                    break

        if not rearm:
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
                authorized_events: Optional[Dict[str, Any]], fund: str, session: str) -> Dict[str, Any]:
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
    forecast_volatility = inputs.get('forecast_volatility')
    long_run_volatility = inputs.get('long_run_volatility')

    # SUC-07: If NO volatility inputs at all, return None (no row emission)
    # This is handled by checking if volatility data is completely absent
    # For now, fail closed on missing inputs
    if forecast_volatility is None or long_run_volatility is None:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input',
            'fund': fund
        }

    try:
        forecast_volatility = float(forecast_volatility)
        long_run_volatility = float(long_run_volatility)
    except (TypeError, ValueError):
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
    if v5_tolerance is None:
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

    # Calculate excess shortfall
    if shortfall_observed is None or shortfall_predicted is None:
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
                'disposition': 'missing_data'
            }
        }

    try:
        v5_tolerance = float(v5_tolerance)
        shortfall_observed = float(shortfall_observed)
        shortfall_predicted = float(shortfall_predicted)
    except (TypeError, ValueError):
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
                'disposition': 'invalid_data'
            }
        }

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

    Kind: diagnostic
    Scope: fund
    State contribution: Diagnostic only (notify)
    """
    # Evaluate trigger
    cost_per_unit = inputs.get('v6_cost_per_unit_exposure')
    threshold = inputs.get('v6_threshold')

    # V6 is diagnostic only - with missing inputs, return benign (Fix 2: V6 does NOT trip)
    if cost_per_unit is None or threshold is None:
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

    try:
        cost_per_unit = float(cost_per_unit)
        threshold = float(threshold)
    except (TypeError, ValueError):
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

    # Check trigger
    exceeded = cost_per_unit > threshold

    return {
        'state': 'NORMAL',
        'would_have_tripped': exceeded,
        'kind': 'diagnostic',
        'latched': False,
        'reason': 'carrying_cost_exceeded' if exceeded else 'none',
        'fund': fund,
        'outputs': {
            'cost_per_unit_exposure': cost_per_unit,
            'threshold': threshold,
            'exceeded': exceeded,
            'notify': exceeded
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
    if v7_spread_width_threshold is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'fund': fund
        }

    # Check staleness (staleness > 1.0 means stale)
    quote_stale = quote_staleness is not None and quote_staleness > 1.0

    # Check spread width
    try:
        v7_spread_width_threshold = float(v7_spread_width_threshold)
        spread_too_wide = spread_width is not None and float(spread_width) > v7_spread_width_threshold
    except (TypeError, ValueError):
        spread_too_wide = True  # Fail closed on invalid

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
