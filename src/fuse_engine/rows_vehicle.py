"""Vehicle breaker rows V1-V7 per BRIEF-FUSE-1 §4.3 Table B.

All vehicle rows operate on 3× daily-reset funds.
Thresholds per §4.5 disposition register.
"""

from typing import Any, Dict, Optional
from . import state as st


def evaluate_V1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str) -> Dict[str, Any]:
    """V1: Tracking deviation exceeds thresholds → NO-NEW-RISK in that fund.

    Kind: breaker
    Scope: fund
    State contribution: NO-NEW-RISK
    Clearing: Owner re-arms after reconciliation
    Required inputs: v1_one_session_deviation, v1_five_session_deviation (or fail closed)
    """
    # Check for prior latch
    scope = f'fund:{fund}'
    prior_latch = st.get_latch(prior_state, 'V1', scope)
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            fund_events = authorized_events.get(scope, [])
            for event in fund_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'V1':
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

    # Evaluate trigger - fail closed if unresolved per §4.5
    one_session_dev = inputs.get('v1_one_session_deviation')
    five_session_dev = inputs.get('v1_five_session_deviation')

    # Fail closed on missing/unresolved inputs
    if one_session_dev is None or five_session_dev is None:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'unresolved_fail_closed',
            'fund': fund
        }

    try:
        one_session_dev = float(one_session_dev)
        five_session_dev = float(five_session_dev)
    except (TypeError, ValueError):
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'unresolved_fail_closed',
            'fund': fund
        }

    # Thresholds per §4.5 (proposal values)
    one_session_threshold = 0.0075  # 0.75 pp
    five_session_threshold = 0.020  # 2.0 pp

    # Check triggers
    triggered = (abs(one_session_dev) > one_session_threshold or
                 abs(five_session_dev) > five_session_threshold)

    if not triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }

    # Trip and latch
    return {
        'state': 'NO-NEW-RISK',
        'would_have_tripped': True,
        'kind': 'breaker',
        'latched': True,
        'reason': 'tracking_deviation',
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
    prior_latch = st.get_latch(prior_state, 'V2', scope)
    if prior_latch and prior_latch['latched']:
        # Latched mismatch - only owner can re-arm
        rearm = False
        if authorized_events:
            fund_events = authorized_events.get(scope, [])
            for event in fund_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'V2':
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

    # Check for pending adjustment from prior state (B1)
    prior_pending = None
    if prior_state:
        v2_state = prior_state.get('V2_pending', {})
        prior_pending = v2_state.get(fund)

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

        # If adjustment complete and exact reconciliation, auto-clear
        if adjustment_complete and exact_reconciliation:
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

        # Action announced or detected → pending HALT
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
            fund_events = authorized_events.get(scope, [])
            for event in fund_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'V3':
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

    # Fail closed on missing input
    if fund_event is None:
        return {
            'state': 'DE-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input',
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
    Mechanism B4: clearing counter increments at most once per session
    """
    scope = f'fund:{fund}'

    # Get prior counter (B4: session-keyed to prevent multiple increments per session)
    clearing_count = st.get_counter(prior_state, 'V4', scope, 'clearing_sessions', session=session, default=0)
    # Also track the last session we incremented in
    last_increment_session = st.get_prior_state(prior_state, 'V4_last_increment_session', {}).get(scope)

    # Evaluate trigger - fail closed if unresolved per §4.5
    forecast_volatility = inputs.get('v4_forecast_volatility')

    # Fail closed on missing/unresolved input
    if forecast_volatility is None:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'fund': fund
        }

    try:
        forecast_volatility = float(forecast_volatility)
    except (TypeError, ValueError):
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'fund': fund
        }

    # Threshold per §4.5 (proposal: 2× long-run, ≈48% for Nasdaq-100)
    long_run_volatility = 0.24  # ~24% long-run
    threshold = 2.0 * long_run_volatility  # 48%

    # Check trigger
    triggered = forecast_volatility >= threshold

    if triggered:
        # Trip - reset clearing counter
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'extreme_volatility',
            'fund': fund
        }

    # Not triggered - check clearing progress (B4: increment at most once per session)
    if last_increment_session == session:
        # Already incremented this session - return current count
        new_count = clearing_count
    else:
        # Different session or first time - safe to increment
        new_count = clearing_count + 1

    if new_count >= 10:
        # Cleared
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'interlock',
            'latched': False,
            'reason': 'none',
            'fund': fund
        }

    # Still clearing
    return {
        'state': 'NO-NEW-RISK',
        'would_have_tripped': True,
        'kind': 'interlock',
        'latched': False,
        'reason': 'clearing_period',
        'fund': fund
    }


def evaluate_V5(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], fund: str, session: str) -> Dict[str, Any]:
    """V5: Decay monitor → notify; if persists for 40 sessions, escalate to V1.

    Kind: diagnostic (with stateful escalation)
    Scope: fund
    State contribution: Diagnostic only until escalation; then NO-NEW-RISK
    Clearing: Diagnostic (stateful escalation)
    Mechanism B5: persistence counter counts consecutive beyond-tolerance sessions,
                  escalates to V1 treatment at 40 sessions
    """
    scope = f'fund:{fund}'

    # Get prior persistence counter
    persistence_count = st.get_counter(prior_state, 'V5', scope, 'persistence_sessions', default=0)
    prior_escalated = st.get_prior_state(prior_state, 'V5_escalated', {}).get(scope, False)

    # Evaluate trigger - fail closed if tolerance unresolved per §4.5
    v5_tolerance = inputs.get('v5_tolerance')
    excess_shortfall = inputs.get('v5_excess_shortfall')

    # Fail closed on unresolved tolerance
    if v5_tolerance is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'diagnostic',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'fund': fund,
            'outputs': {
                'excess_shortfall': 0.0,
                'consecutive_sessions_beyond_tolerance': 0,
                'escalated_to_v1': False,
                'disposition': 'unresolved'
            }
        }

    # Fail closed on missing excess_shortfall
    if excess_shortfall is None:
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
        excess_shortfall = float(excess_shortfall)
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

    # Check if beyond tolerance
    beyond_tolerance = excess_shortfall > v5_tolerance

    if beyond_tolerance:
        # Increment persistence counter
        new_count = persistence_count + 1
    else:
        # Reset counter
        new_count = 0

    # B5: Escalate to V1 treatment at 40 sessions (two months per §4.3)
    escalated = new_count >= 40

    # Determine state contribution
    if escalated:
        state = 'NO-NEW-RISK'
        disposition = 'escalated_to_v1'
    elif beyond_tolerance:
        state = 'NORMAL'
        disposition = 'beyond_tolerance'
    else:
        state = 'NORMAL'
        disposition = 'benign'

    return {
        'state': state,
        'would_have_tripped': beyond_tolerance or escalated,
        'kind': 'diagnostic',
        'latched': False,
        'reason': 'persistent_decay' if escalated else ('decay_excess' if beyond_tolerance else 'none'),
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

    # Fail closed on missing inputs
    if cost_per_unit is None or threshold is None:
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
    Required inputs: v7_spread_width (or fail closed)
    """
    # Evaluate trigger - fail closed if unresolved per §4.5
    quote_stale = inputs.get('v7_quote_stale')
    spread_too_wide = inputs.get('v7_spread_too_wide')
    single_stock_pause = inputs.get('v7_single_stock_pause')
    outside_regular_session = inputs.get('v7_outside_regular_session')
    v7_spread_width = inputs.get('v7_spread_width')

    # Fail closed on unresolved spread width
    if v7_spread_width is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'fund': fund
        }

    # Check any trigger
    triggered = (quote_stale or spread_too_wide or single_stock_pause or outside_regular_session)

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
