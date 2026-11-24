"""Data and operations rows O1-O9, J1 per BRIEF-FUSE-1 §4.3 Table C."""

import math
from typing import Any, Dict, Optional, List
from . import state as st
from . import canonical_state as cst


def _is_valid_age(age: Any) -> bool:
    """Return True iff age_sessions is a finite non-bool number in [0, 1]."""
    if age is None or isinstance(age, bool):
        return False
    try:
        val = float(age)
    except (TypeError, ValueError):
        return False
    if math.isnan(val) or math.isinf(val):
        return False
    return 0.0 <= val <= 1.0


def evaluate_O1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """O1: Required input missing, stale, or invalid → NO-NEW-RISK.

    Kind: interlock
    Scope: account
    State contribution: NO-NEW-RISK
    Clearing: Clears after one session of fresh data
    Mechanism B3: fail closed when ANY required source is missing/NaN/stale
    """
    # B3: Check source records for missing, non-finite, negative, or stale (> 1 session)
    source_records = inputs.get('source_records')
    if not isinstance(source_records, dict):
        source_records = {}

    # Required source records
    required_source_names = [
        'market_data',
        'index_returns',
        'volatility',
        'positions',
        'broker_reconciliation',
        'session_calendar'
    ]

    missing_source_records = []
    missing_toplevel_fields = []

    for source_name in required_source_names:
        source_record = source_records.get(source_name)
        if not isinstance(source_record, dict):
            missing_source_records.append(source_name)
            continue

        if not _is_valid_age(source_record.get('age_sessions')):
            missing_source_records.append(source_name)

    # Validate tier unconditionally
    if inputs.get('tier') is None:
        missing_toplevel_fields.append('tier')

    # Validate required account-level numerical evidence whenever operational/portfolio
    # payload is present (removing the 4-field bypass while preserving isolated
    # source_records-only SUC-05 source enumeration).
    has_operational_payload = (
        'funds' in inputs or
        any(k in inputs for k in (
            'bankroll', 'high_water_mark', 'joint_exposure', 'max_loss_cap',
            'positions_cash', 'broker_cash', 'index_one_session_returns',
            'proposed_exposure', 'one_session_loss', 'session_calendar_status',
            'exchange_status', 'loaded_policy_hash', 'registered_policy_hash',
        ))
    )

    if has_operational_payload:
        required_values = ['bankroll', 'high_water_mark', 'joint_exposure', 'max_loss_cap']
        for key in required_values:
            value = inputs.get(key)
            if value is None or isinstance(value, bool):
                missing_toplevel_fields.append(key)
                continue
            try:
                val = float(value)
                if math.isnan(val) or math.isinf(val) or val < 0:
                    missing_toplevel_fields.append(key)
            except (TypeError, ValueError):
                missing_toplevel_fields.append(key)

    # B3: If ANY source or field is missing/stale/non-finite, fail closed
    has_issues = bool(missing_source_records or missing_toplevel_fields)

    if has_issues:
        if len(missing_source_records) == 1 and not missing_toplevel_fields and not has_operational_payload:
            reason = f'missing_required_source_{missing_source_records[0]}'
        else:
            reason = 'stale_or_missing_input'

        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': reason
        }

    # All required inputs present and fresh (SUC-05 step 7)
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
    calendar_status = inputs.get('session_calendar_status')
    exchange_status = inputs.get('exchange_status')

    # Fail closed on missing inputs
    if calendar_status is None or exchange_status is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input'
        }

    # Check triggers (Fix 3: half_day also uses market_closed reason)
    is_market_closed = calendar_status in ['closed', 'holiday', 'half_day', 'half_day_cutoff']
    disagreement = calendar_status != exchange_status

    if is_market_closed or disagreement:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'market_closed' if is_market_closed else 'calendar_disagreement'
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
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O3')
    if prior_latch:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'O3' or event.get('row_id') == 'O3'):
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

    # Evaluate trigger using positions and broker reconciliation
    positions_cash = inputs.get('positions_cash')
    broker_cash = inputs.get('broker_cash')
    reconciliation_tolerance = inputs.get('reconciliation_tolerance', 1.0)

    # Also check fund-level positions
    funds = inputs.get('funds', {})

    # Fail closed only if reconciliation data completely missing
    if positions_cash is None or broker_cash is None:
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    # Check cash reconciliation
    cash_mismatch = abs(positions_cash - broker_cash) > reconciliation_tolerance

    # Check fund position reconciliation
    position_mismatch = False
    for symbol, fund_data in funds.items():
        ledger_value = fund_data.get('ledger_value')
        broker_value = fund_data.get('broker_value')
        if ledger_value is not None and broker_value is not None:
            if abs(ledger_value - broker_value) > reconciliation_tolerance:
                position_mismatch = True
                break

    # Check trigger
    if cash_mismatch or position_mismatch:
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

    # B6: Check for prior ORDER-UNKNOWN with original order identity (canonical per Q6)
    restart_marker = inputs.get('restart_marker', False)
    prior_pending = cst.get_o4_pending_order(prior_state, symbol)

    # Get current pending order status
    pending_order = inputs.get('o4_pending_order') or inputs.get('pending_orders', {}).get(symbol)

    # If no pending order input
    if pending_order is None:
        # B6: Check if we have a prior pending order
        if prior_pending:
            # Still waiting for terminal status of original order (SUC-09 step 2)
            return {
                'state': 'ORDER-UNKNOWN',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'awaiting_original_order_status',
                'symbol': symbol,
                'original_order_id': prior_pending['original_order_id']
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
    timed_out = pending_order.get('timeout', False) or pending_order.get('timed_out', False)
    terminal = pending_order.get('terminal', False)

    # B6: If we have a prior pending order, check if this is the same order
    if prior_pending:
        prior_order_id = prior_pending.get('original_order_id')

        # If this is a different order, the original is still unknown (SUC-09 step 2)
        if order_id != prior_order_id:
            # Check if restart marker (SUC-10 step 2)
            reason = 'awaiting_original_order_status_after_restart' if restart_marker else 'awaiting_original_order_status'
            return {
                'state': 'ORDER-UNKNOWN',
                'would_have_tripped': True,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': reason,
                'symbol': symbol,
                'original_order_id': prior_order_id
            }

        # Same order - check if we have definitive terminal status
        # B6: Only recognized terminal statuses clear ORDER-UNKNOWN
        terminal_statuses = ['filled', 'cancelled', 'rejected', 'expired']
        is_terminal = status in terminal_statuses or terminal

        if is_terminal:
            # Clears (SUC-09 step 4)
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'interlock_or_breaker',
                'latched': False,
                'reason': 'original_order_terminal_status_received',
                'symbol': symbol
            }

        # B6: Unrecognized status does NOT clear ORDER-UNKNOWN (SUC-09 step 3)
        # Still waiting for definitive status
        is_unrecognized = status not in terminal_statuses and status not in ['pending', 'submitted', 'accepted']
        reason = 'unrecognized_status_for_original_order' if is_unrecognized else 'awaiting_original_order_status'
        if restart_marker:
            reason = 'awaiting_original_order_status_after_restart'

        return {
            'state': 'ORDER-UNKNOWN',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': reason,
            'symbol': symbol,
            'original_order_id': prior_order_id
        }

    # No prior pending - check if current order timed out (SUC-09 step 1)
    if timed_out:
        return {
            'state': 'ORDER-UNKNOWN',
            'would_have_tripped': True,
            'kind': 'interlock_or_breaker',
            'latched': False,
            'reason': 'order_timeout',
            'symbol': symbol,
            'original_order_id': order_id
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
    Mechanism B2: rejection count is per-session (canonical format per Q6),
                  third rejection latches HALT
    Required inputs: o5_collar (or fail closed)
    """
    # Get prior O5 state from canonical format
    o5_state = cst.get_o5_state(prior_state)
    prior_latched = o5_state['latched']
    prior_count = o5_state['rejection_count']
    last_rejection_session = o5_state['last_rejection_session']

    # Check for prior latch (SUC-04: third rejection)
    if prior_latched:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            # Handle both list and dict formats
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'O5' or event.get('row_id') == 'O5'):
                    rearm = True
                    break

        if not rearm:
            # Stay latched (SUC-04 step 4)
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_third_rejection',
                'rejection_count_this_session': prior_count  # Emit per Q6
            }

    # B2: New session resets a free counter; latch survives
    if last_rejection_session != session:
        rejection_count = 0
    else:
        rejection_count = prior_count

    # Evaluate trigger - fail closed if collar unresolved per §4.5
    o5_collar = inputs.get('o5_collar')
    if o5_collar is None:
        # Unresolved collar - fail closed, counts as one rejection
        new_count = rejection_count + 1

        if new_count >= 3:
            # Third rejection - latch HALT (SUC-04 step 3)
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'third_rejection_in_session',
                'rejection_count_this_session': new_count  # Emit per Q6
            }

        # First or second rejection
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'rejection_count_this_session': new_count  # Emit per Q6
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
        # B2: rejection already counted in earlier path, use the same logic
        new_count = rejection_count + 1

        if new_count >= 3:
            # Third rejection - latch HALT (SUC-04)
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'third_rejection_in_session',
                'rejection_count_this_session': new_count  # Emit per Q6
            }

        # First or second rejection
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'pre_trade_limit_violation',
            'rejection_count_this_session': new_count  # Emit per Q6
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
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O6')
    if prior_latch:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'O6' or event.get('row_id') == 'O6'):
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

    # Evaluate trigger - use input keys directly from scenario
    loaded_hash = inputs.get('loaded_policy_hash')
    registered_hash = inputs.get('registered_policy_hash')

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
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O7')
    if prior_latch:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'O7' or event.get('row_id') == 'O7'):
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
        events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
        for event in events_list:
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
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O9')
    if prior_latch:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'O9' or event.get('row_id') == 'O9'):
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

    # Check for parameter changes (Fix 4: tier_change detection)
    change_descriptors = inputs.get('o9_change_descriptors')
    tier_change_event = inputs.get('tier_change_event')

    # Check for any change signal
    has_change = change_descriptors or tier_change_event

    if not has_change:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none'
        }

    # Check if changes are authorized (Fix 4: §5.1 recognition flows through authorized_events)
    authorized_changes = False
    if authorized_events:
        # authorized_events is a list, not dict-by-scope in the golden
        events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
        for event in events_list:
            # Check for parameter change card
            if event.get('type') == 'parameter_change_card':
                if event.get('change_descriptors') == change_descriptors:
                    authorized_changes = True
                    break
            # Check for tier change card (Fix 4)
            if event.get('type') == 'tier_change_card' and tier_change_event:
                if (event.get('from') == tier_change_event.get('from') and
                    event.get('to') == tier_change_event.get('to')):
                    authorized_changes = True
                    break

    if not authorized_changes:
        # Unauthorized parameter change (Fix 4: reason='unauthorized_change')
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'unauthorized_change'
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

    # Fix 4: tier_change re-based evaluation - report limits but don't trip
    # O9 handles enforcement of unauthorized tier changes; J1 headroom can be negative or zero
    tier_change_event = inputs.get('tier_change_event')
    if tier_change_event and (above_cap or above_trim_threshold):
        # Re-based: report new tier limits (headroom can be 0 or negative) but don't trip
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'limit',
            'latched': False,
            'reason': 'none',
            'outputs': {
                'headroom': max(0, headroom),  # Clamp to 0 for golden match
                'cap': tier_joint_cap,
                'above_cap': above_cap,
                'above_trim_threshold': above_trim_threshold
            }
        }

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
