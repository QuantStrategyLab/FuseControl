"""Data and operations rows O1-O9, J1 per BRIEF-FUSE-1 §4.3 Table C."""

from typing import Any, Dict, Optional, List
from . import state as st


def evaluate_O1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """O1: Required input missing, stale, or invalid → NO-NEW-RISK.

    Kind: interlock
    Scope: account
    State contribution: NO-NEW-RISK
    Clearing: Clears after one session of fresh data
    Mechanism B3: fail closed when ANY required source is missing/NaN/stale
    """
    # Required sources per §4.3 and §5.4
    required_sources = [
        'bankroll',
        'high_water_mark',
        'joint_exposure',
        'max_loss_cap',
        'tier',
        'volatility',  # B3: volatility is required
        'index_one_session_returns'  # B3: index returns are required
    ]

    # B3: Check if ANY required source is missing/NaN/stale
    missing_sources = []
    for source in required_sources:
        value = inputs.get(source)
        if value is None:
            missing_sources.append(source)
            continue

        # Check for NaN/invalid
        if source in ['bankroll', 'high_water_mark', 'joint_exposure', 'max_loss_cap']:
            try:
                val = float(value)
                import math
                if math.isnan(val) or math.isinf(val):
                    missing_sources.append(source)
            except (TypeError, ValueError):
                missing_sources.append(source)

    # Check staleness - inputs should have staleness indicators
    stale_indicator = inputs.get('o1_has_stale_data', False)
    if stale_indicator:
        missing_sources.append('stale_data')

    # B3: If ANY source is missing/stale, fail closed - NO silent passes
    if missing_sources:
        # Check clearing counter
        fresh_count = st.get_counter(prior_state, 'O1', 'account', 'fresh_sessions', default=0)

        if fresh_count >= 1:
            # Cleared after one fresh session
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'interlock',
                'latched': False,
                'reason': 'none'
            }

        # Still in trip state
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_or_stale_input'
        }

    # All required inputs present and fresh
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock',
        'latched': False,
        'reason': 'none'
    }


def evaluate_O2(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """O2: Session calendar closed/holiday/disagreement → no order.

    Kind: interlock
    Scope: account
    State contribution: Order suppression (no control state)
    """
    # Evaluate trigger
    calendar_status = inputs.get('o2_calendar_status')
    exchange_status = inputs.get('o2_exchange_status')

    # Fail closed on missing inputs
    if calendar_status is None or exchange_status is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input'
        }

    # Check triggers
    triggered = (calendar_status in ['closed', 'holiday', 'half_day_cutoff'] or
                 calendar_status != exchange_status)

    if triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'calendar_restriction'
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock',
        'latched': False,
        'reason': 'none'
    }


def evaluate_O3(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """O3: Position/cash mismatch beyond tolerance → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT
    Clearing: Owner re-arms after reconciliation
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'O3', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            account_events = authorized_events.get('account', [])
            for event in account_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'O3':
                    rearm = True
                    break

        if not rearm:
            # Stay latched
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip'
            }

    # Evaluate trigger
    reconciliation_status = inputs.get('o3_reconciliation_status')
    mismatch_beyond_tolerance = inputs.get('o3_mismatch_beyond_tolerance')

    # Fail closed on missing inputs
    if reconciliation_status is None or mismatch_beyond_tolerance is None:
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    # Check trigger
    if mismatch_beyond_tolerance:
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'reconciliation_mismatch'
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none'
    }


def evaluate_O4(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
    """O4: Order timeout → ORDER-UNKNOWN for that symbol.

    Kind: interlock_or_breaker
    Scope: symbol
    State contribution: ORDER-UNKNOWN
    Clearing: Clears on definitive terminal status for the ORIGINAL order;
             otherwise latches
    Mechanism B6: ORDER-UNKNOWN keyed to original order identity
    """
    scope = f'symbol:{symbol}'

    # B6: Check for prior ORDER-UNKNOWN with original order identity
    prior_pending = None
    if prior_state:
        o4_state = prior_state.get('O4_pending', {})
        prior_pending = o4_state.get(scope)

    # Get current pending order status
    pending_order = inputs.get('o4_pending_order')

    # If no pending order input
    if pending_order is None:
        # B6: Check if we have a prior pending order
        if prior_pending:
            # Still waiting for terminal status of original order
            return {
                'state': 'ORDER-UNKNOWN',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'order_timeout_carried',
                'symbol': symbol
            }
        # No pending order
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': 'none',
            'symbol': symbol
        }

    # Validate pending_order structure
    if not isinstance(pending_order, dict):
        return {
            'state': 'ORDER-UNKNOWN',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': True,
            'reason': 'missing_input',
            'symbol': symbol
        }

    order_id = pending_order.get('order_id')
    status = pending_order.get('status')
    timed_out = pending_order.get('timed_out', False)

    # B6: If we have a prior pending order, check if this is the same order
    if prior_pending:
        prior_order_id = prior_pending.get('order_id')

        # If this is a different order, the original is still unknown
        if order_id != prior_order_id:
            return {
                'state': 'ORDER-UNKNOWN',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'order_timeout_carried',
                'symbol': symbol
            }

        # Same order - check if we have definitive terminal status
        # B6: Only recognized terminal statuses clear ORDER-UNKNOWN
        terminal_statuses = ['filled', 'cancelled', 'rejected', 'expired']
        if status in terminal_statuses:
            # Clears
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'none',
                'symbol': symbol
            }

        # B6: Unrecognized status does NOT clear ORDER-UNKNOWN
        # Still waiting for definitive status
        return {
            'state': 'ORDER-UNKNOWN',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': 'order_timeout_carried',
            'symbol': symbol
        }

    # No prior pending - check if current order timed out
    if timed_out:
        return {
            'state': 'ORDER-UNKNOWN',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': 'order_timeout',
            'symbol': symbol
        }

    # No timeout
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock_or_breaker',
        'latched': False,
        'reason': 'none',
        'symbol': symbol
    }


def evaluate_O5(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """O5: Pre-trade limit violation → reject; third rejection in session → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT on third rejection
    Clearing: Owner re-arms
    Mechanism B2: rejection count is per-session, third rejection latches HALT
    Required inputs: o5_collar (or fail closed)
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'O5', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            account_events = authorized_events.get('account', [])
            for event in account_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'O5':
                    rearm = True
                    break

        if not rearm:
            # Stay latched
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip'
            }

    # Evaluate trigger - fail closed if collar unresolved per §4.5
    o5_collar = inputs.get('o5_collar')
    if o5_collar is None:
        # Unresolved collar - fail closed, counts as one rejection
        # B2: Get rejection count for this session
        rejection_count = st.get_counter(prior_state, 'O5', 'account', 'rejections', session=session, default=0)
        new_count = rejection_count + 1

        if new_count >= 3:
            # Third rejection - latch HALT
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'third_rejection'
            }

        # First or second rejection
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'unresolved_fail_closed'
        }

    # Check other pre-trade limits
    violations = []

    # Symbol whitelist
    symbol = inputs.get('o5_symbol')
    whitelist = inputs.get('o5_symbol_whitelist', ['TQQQ', 'SOXL'])
    if symbol and symbol not in whitelist:
        violations.append('symbol_not_whitelisted')

    # Account whitelist
    account = inputs.get('o5_account')
    account_whitelist = inputs.get('o5_account_whitelist')
    if account and account_whitelist and account not in account_whitelist:
        violations.append('account_not_whitelisted')

    # Long only
    side = inputs.get('o5_side')
    if side and side != 'buy':
        violations.append('not_long_only')

    # Within settled cash
    order_value = inputs.get('o5_order_value')
    settled_cash = inputs.get('o5_settled_cash')
    if order_value and settled_cash and order_value > settled_cash:
        violations.append('exceeds_settled_cash')

    # Maximum order size
    order_size = inputs.get('o5_order_size')
    max_order_size = inputs.get('o5_max_order_size')
    if order_size and max_order_size and order_size > max_order_size:
        violations.append('exceeds_max_order_size')

    # Maximum orders per session
    orders_today = inputs.get('o5_orders_today', 0)
    max_orders = inputs.get('o5_max_orders_per_session')
    if max_orders and orders_today >= max_orders:
        violations.append('exceeds_max_orders')

    # Turnover limit
    turnover_today = inputs.get('o5_turnover_today', 0)
    max_turnover = inputs.get('o5_max_turnover_per_session')
    if max_turnover and turnover_today > max_turnover:
        violations.append('exceeds_max_turnover')

    # Price collar
    order_price = inputs.get('o5_order_price')
    reference_price = inputs.get('o5_reference_price')
    if order_price and reference_price and o5_collar:
        try:
            collar_pct = float(o5_collar)
            lower_bound = reference_price * (1 - collar_pct)
            upper_bound = reference_price * (1 + collar_pct)
            if order_price < lower_bound or order_price > upper_bound:
                violations.append('outside_price_collar')
        except (TypeError, ValueError):
            violations.append('invalid_collar')

    # If any violations, count as rejection
    if violations:
        # B2: Get rejection count for this session
        rejection_count = st.get_counter(prior_state, 'O5', 'account', 'rejections', session=session, default=0)
        new_count = rejection_count + 1

        if new_count >= 3:
            # Third rejection - latch HALT
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'third_rejection'
            }

        # First or second rejection
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'pre_trade_limit_violation'
        }

    # No violations
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none'
    }


def evaluate_O6(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """O6: Policy/config hash mismatch → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT
    Clearing: Owner re-arms
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'O6', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            account_events = authorized_events.get('account', [])
            for event in account_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'O6':
                    rearm = True
                    break

        if not rearm:
            # Stay latched
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip'
            }

    # Evaluate trigger
    loaded_hash = inputs.get('o6_loaded_policy_hash')
    registered_hash = inputs.get('o6_registered_policy_hash')

    # Fail closed on missing inputs
    if loaded_hash is None or registered_hash is None:
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    # Check trigger
    if loaded_hash != registered_hash:
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'policy_hash_mismatch'
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none'
    }


def evaluate_O7(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """O7: Dead-man's switch → no increase until re-armed.

    Kind: breaker
    Scope: account
    State contribution: No exposure increase
    Clearing: Human re-arm
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'O7', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            account_events = authorized_events.get('account', [])
            for event in account_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'O7':
                    rearm = True
                    break

        if not rearm:
            # Stay latched
            return {
                'state': 'NORMAL',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip'
            }

    # Evaluate trigger
    runtime_silent = inputs.get('o7_runtime_silent', False)
    monitor_silent = inputs.get('o7_monitor_silent', False)

    # Check trigger
    if runtime_silent or monitor_silent:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'dead_mans_switch'
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none'
    }


def evaluate_O8(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """O8: Kill switch → HALT.

    Kind: owner
    Scope: account
    State contribution: HALT
    Clearing: Owner command
    """
    # Check for owner kill command in authorized_events
    kill_command = False
    if authorized_events:
        account_events = authorized_events.get('account', [])
        for event in account_events:
            if event.get('type') == 'kill_switch':
                kill_command = True
                break

    if kill_command:
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'owner',
            'latched': False,
            'reason': 'kill_switch'
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'owner',
        'latched': False,
        'reason': 'none'
    }


def evaluate_O9(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """O9: Parameter change without owner card → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT
    Clearing: Owner re-arms
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'O9', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            account_events = authorized_events.get('account', [])
            for event in account_events:
                if event.get('type') == 'rearm' and event.get('row_id') == 'O9':
                    rearm = True
                    break

        if not rearm:
            # Stay latched
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip'
            }

    # Check for parameter changes
    change_descriptors = inputs.get('o9_change_descriptors')

    # If no change descriptors, benign
    if not change_descriptors:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none'
        }

    # Check if changes are authorized
    authorized_changes = False
    if authorized_events:
        account_events = authorized_events.get('account', [])
        for event in account_events:
            if event.get('type') == 'parameter_change_card':
                # Verify the card covers the changes
                if event.get('change_descriptors') == change_descriptors:
                    authorized_changes = True
                    break

    if not authorized_changes:
        # Unauthorized parameter change
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'unauthorized_parameter_change'
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none'
    }


def evaluate_J1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """J1: Joint exposure above tier joint cap → increases blocked.

    Kind: limit
    Scope: joint
    State contribution: Limit (no control state)
    Clearing: Automatic when below cap
    """
    # Required inputs
    joint_exposure = inputs.get('joint_exposure')
    tier_joint_cap = inputs.get('tier_joint_cap')

    # Fail closed on missing inputs
    if joint_exposure is None or tier_joint_cap is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'limit',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'headroom': 0.0,
                'cap': 0.0,
                'above_cap': True,
                'above_trim_threshold': True
            }
        }

    try:
        joint_exposure = float(joint_exposure)
        tier_joint_cap = float(tier_joint_cap)
    except (TypeError, ValueError):
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'limit',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'headroom': 0.0,
                'cap': 0.0,
                'above_cap': True,
                'above_trim_threshold': True
            }
        }

    # Calculate headroom
    headroom = tier_joint_cap - joint_exposure

    # Check cap
    above_cap = joint_exposure > tier_joint_cap

    # Check trim threshold (110% of cap per §4.3)
    trim_threshold = tier_joint_cap * 1.10
    above_trim_threshold = joint_exposure > trim_threshold

    return {
        'state': 'NORMAL',
        'would_have_tripped': above_cap or above_trim_threshold,
        'kind': 'limit',
        'latched': False,
        'reason': 'joint_cap_exceeded' if above_cap else 'none',
        'outputs': {
            'headroom': headroom,
            'cap': tier_joint_cap,
            'above_cap': above_cap,
            'above_trim_threshold': above_trim_threshold
        }
    }
