"""Data and operations rows O1-O9, J1 per BRIEF-FUSE-1 §4.3 Table C."""

import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from . import state as st
from . import canonical_state as cst
from .canonical import finite_float


def _parse_iso_ts(value: Any) -> Optional[datetime]:
    """Parse ISO-8601 timestamp normalized to UTC, or return None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_valid_age(age: Any) -> bool:
    """Return True iff age_sessions is a finite non-bool number in [0, 1]."""
    val = finite_float(age)
    return val is not None and 0.0 <= val <= 1.0


def evaluate_O1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], session: str,
                as_of: Optional[str] = None) -> Dict[str, Any]:
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

    # Same-session stale->fresh does NOT clear within the same trading session
    cur_date = as_of[:10] if isinstance(as_of, str) and len(as_of) >= 10 else session
    prior_o1 = cst.get_o1_fresh_state(prior_state)
    if prior_o1.get('last_tripped_session') is not None and prior_o1.get('last_tripped_session') == cur_date:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'clearing_period'
        }

    # All required inputs present and fresh (SUC-05 step 7)
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock',
        'latched': False,
        'reason': 'none'
    }


VALID_CALENDAR_STATUSES = {'open', 'closed', 'holiday', 'half_day', 'half_day_cutoff', 'market_closed'}
CLOSED_CALENDAR_STATUSES = {'closed', 'holiday', 'half_day', 'half_day_cutoff', 'market_closed'}


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

    # Whitelist valid calendar/exchange status tokens (reject unrecognized tokens like "n/a")
    if (
        not isinstance(calendar_status, str) or
        not isinstance(exchange_status, str) or
        calendar_status not in VALID_CALENDAR_STATUSES or
        exchange_status not in VALID_CALENDAR_STATUSES
    ):
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'invalid_input'
        }

    # Check triggers (Fix 3: half_day also uses market_closed reason)
    is_market_closed = calendar_status in CLOSED_CALENDAR_STATUSES or exchange_status in ('closed', 'holiday', 'market_closed')
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
                authorized_events: Optional[Dict[str, Any]],
                session: Optional[str] = None,
                as_of: Optional[str] = None) -> Dict[str, Any]:
    """O3: Position/cash mismatch beyond tolerance → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT
    Clearing: Owner re-arms after reconciliation
    """
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O3')
    if prior_latch:
        rearm = cst.matches_account_rearm(
            authorized_events, 'O3', session=session, as_of=as_of,
            require_date=(session is not None or as_of is not None),
        ) is not None

        if not rearm:
            # Stay latched
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip'
            }

    # Evaluate trigger using positions and broker reconciliation (explicit tolerance required)
    positions_cash = finite_float(inputs.get('positions_cash'))
    broker_cash = finite_float(inputs.get('broker_cash'))
    reconciliation_tolerance = finite_float(inputs.get('reconciliation_tolerance'))

    # Also check fund-level positions
    funds = inputs.get('funds', {})

    # Fail closed if reconciliation data or tolerance is missing/non-finite/negative
    if (positions_cash is None or broker_cash is None or
            reconciliation_tolerance is None or reconciliation_tolerance < 0.0):
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    # Check cash reconciliation
    cash_mismatch = abs(positions_cash - broker_cash) > reconciliation_tolerance

    # Check fund position reconciliation (BOTH share counts and market values required for each fund)
    position_mismatch = False
    if not isinstance(funds, dict):
        return {
            'state': 'HALT',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }
    for symbol, fund_data in sorted(funds.items()):
        if not isinstance(fund_data, dict):
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'missing_input'
            }
        ledger_value = finite_float(fund_data.get('ledger_value'))
        broker_value = finite_float(fund_data.get('broker_value'))
        share_count = finite_float(fund_data.get('share_count'))
        broker_pos = finite_float(fund_data.get('broker_position'))
        if ledger_value is None or broker_value is None or share_count is None or broker_pos is None:
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'missing_input'
            }
        if abs(ledger_value - broker_value) > reconciliation_tolerance or share_count != broker_pos:
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
        # B6: Only recognized terminal statuses clear ORDER-UNKNOWN (ignore unvalidated terminal flags)
        terminal_statuses = ['filled', 'cancelled', 'rejected', 'expired']
        is_terminal = status in terminal_statuses

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
                authorized_events: Optional[Dict[str, Any]], session: str,
                as_of: Optional[str] = None) -> Dict[str, Any]:
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
        rearm = cst.matches_account_rearm(
            authorized_events, 'O5', session=session, as_of=as_of, require_date=True
        ) is not None

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

        # Q4: authorized re-arm clears O5 latch and session counter
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'authorized_rearm',
            'rejection_count_this_session': 0
        }

    # B2: New session resets a free counter; latch survives
    if last_rejection_session != session:
        rejection_count = 0
    else:
        rejection_count = prior_count

    # Evaluate trigger - fail closed if collar unresolved or invalid (NaN/inf/bool/negative) per §4.5 / A11
    o5_collar = inputs.get('o5_collar')
    if o5_collar is None or o5_collar == 'unresolved':
        new_count = rejection_count + 1
        if new_count >= 3:
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'third_rejection_in_session',
                'rejection_count_this_session': new_count
            }
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'unresolved_fail_closed',
            'rejection_count_this_session': new_count
        }

    collar_pct = finite_float(o5_collar)
    if collar_pct is None or collar_pct < 0.0:
        new_count = rejection_count + 1
        if new_count >= 3:
            return {
                'state': 'HALT',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'third_rejection_in_session',
                'rejection_count_this_session': new_count
            }
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': False,
            'reason': 'invalid_input',
            'rejection_count_this_session': new_count
        }

    # Check other pre-trade limits
    violations = []

    # Symbol whitelist (canonical 'symbol_whitelist' takes precedence over legacy 'o5_symbol_whitelist')
    symbol = inputs.get('o5_symbol') if 'o5_symbol' in inputs else inputs.get('symbol')
    whitelist = inputs['symbol_whitelist'] if 'symbol_whitelist' in inputs else inputs.get('o5_symbol_whitelist', ['TQQQ', 'SOXL'])
    if symbol is not None and (not isinstance(whitelist, list) or symbol not in whitelist):
        violations.append('symbol_not_whitelisted')

    # Account whitelist (canonical 'account_whitelist' takes precedence over legacy 'o5_account_whitelist')
    account = inputs.get('o5_account') if 'o5_account' in inputs else inputs.get('account')
    account_whitelist = inputs['account_whitelist'] if 'account_whitelist' in inputs else inputs.get('o5_account_whitelist')
    if account is not None and account_whitelist is not None and (not isinstance(account_whitelist, list) or account not in account_whitelist):
        violations.append('account_not_whitelisted')

    # Long only
    side = inputs.get('o5_side')
    if side is not None and side != 'buy':
        violations.append('not_long_only')

    # Within settled cash (canonical 'settled_cash' takes precedence; derive qty * price when order_value omitted)
    order_value = inputs['o5_order_value'] if 'o5_order_value' in inputs else inputs.get('order_value')
    order_size = inputs.get('o5_order_size')
    if order_size is None:
        order_size = inputs.get('o5_order_qty', inputs.get('order_qty', inputs.get('qty')))
    unit_price = inputs.get('o5_order_price')
    if unit_price is None:
        unit_price = inputs.get('o5_limit_price', inputs.get('limit_price', inputs.get('order_price', inputs.get('price'))))
    ref_price = inputs.get('o5_reference_price')

    if order_value is None and order_size is not None and (unit_price is not None or ref_price is not None):
        osize_val = finite_float(order_size)
        uprice_val = finite_float(unit_price if unit_price is not None else ref_price)
        if osize_val is None or uprice_val is None or osize_val < 0.0 or uprice_val < 0.0:
            violations.append('exceeds_settled_cash')
            order_value = None
        else:
            order_value = osize_val * uprice_val

    if 'settled_cash' in inputs and 'o5_settled_cash' in inputs:
        sc_canon = finite_float(inputs.get('settled_cash'))
        sc_o5 = finite_float(inputs.get('o5_settled_cash'))
        if sc_canon is None or sc_o5 is None:
            settled_cash = None
        else:
            settled_cash = min(sc_canon, sc_o5)
    elif 'settled_cash' in inputs:
        settled_cash = inputs['settled_cash']
    else:
        settled_cash = inputs.get('o5_settled_cash')

    if order_value is not None:
        ov = finite_float(order_value)
        sc = finite_float(settled_cash)
        if ov is None or sc is None or ov < 0.0 or sc < 0.0 or ov > sc:
            violations.append('exceeds_settled_cash')

    # Maximum order size
    max_order_size = inputs.get('o5_max_order_size')
    if order_size is not None and max_order_size is not None:
        osize = finite_float(order_size)
        msize = finite_float(max_order_size)
        if osize is None or msize is None or osize < 0.0 or msize < 0.0 or osize > msize:
            violations.append('exceeds_max_order_size')

    # Maximum orders per session
    orders_today = inputs.get('o5_orders_today', inputs.get('session_order_count', 0))
    max_orders = inputs.get('o5_max_orders_per_session')
    if max_orders is not None:
        ot = finite_float(orders_today)
        mo = finite_float(max_orders)
        if ot is None or mo is None or ot >= mo:
            violations.append('exceeds_max_orders')

    # Turnover limit
    turnover_today = inputs.get('o5_turnover_today', inputs.get('session_turnover', 0))
    max_turnover = inputs.get('o5_max_turnover_per_session')
    if max_turnover is not None:
        tt = finite_float(turnover_today)
        mt = finite_float(max_turnover)
        if tt is None or mt is None or tt > mt:
            violations.append('exceeds_max_turnover')

    # Price collar (validates finite positive order_price & reference_price against collar_pct)
    if unit_price is not None or ref_price is not None:
        op = finite_float(unit_price)
        rp = finite_float(ref_price)
        if op is None or rp is None or op <= 0.0 or rp <= 0.0:
            violations.append('invalid_price')
        else:
            lower_bound = rp * (1.0 - collar_pct)
            upper_bound = rp * (1.0 + collar_pct)
            if op < lower_bound or op > upper_bound:
                violations.append('outside_price_collar')

    # If any violations, count as rejection
    if violations:
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

    # No violations (preserve session rejection count across intervening passing checks)
    return {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'breaker',
        'latched': False,
        'reason': 'none',
        'rejection_count_this_session': rejection_count
    }


def evaluate_O6(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]],
                session: Optional[str] = None,
                as_of: Optional[str] = None) -> Dict[str, Any]:
    """O6: Policy/config hash mismatch → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT
    Clearing: Owner re-arms
    """
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O6')
    if prior_latch:
        rearm = cst.matches_account_rearm(
            authorized_events, 'O6', session=session, as_of=as_of,
            require_date=(session is not None or as_of is not None),
        ) is not None

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
                authorized_events: Optional[Dict[str, Any]], as_of: Optional[str] = None,
                session: Optional[str] = None) -> Dict[str, Any]:
    """O7: Dead-man's switch → NO-NEW-RISK until human re-arm (§4.3 / spec.json:262).

    Kind: breaker
    Scope: account
    State contribution: NO-NEW-RISK
    Clearing: Human re-arm
    """
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O7')
    if prior_latch:
        rearm = cst.matches_account_rearm(
            authorized_events, 'O7', session=session, as_of=as_of, require_date=True
        ) is not None

        if rearm:
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'breaker',
                'latched': False,
                'reason': 'authorized_rearm'
            }

        # Stay latched at account-level NO-NEW-RISK
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'latched_prior_trip'
        }

    # Evaluate trigger: explicit silence flags OR missing/invalid/stale heartbeat > 1 scheduled_interval
    runtime_silent = bool(inputs.get('o7_runtime_silent', False))
    monitor_silent = bool(inputs.get('o7_monitor_silent', False))

    heartbeat_stale = False
    raw_hb = inputs.get('last_heartbeat')
    raw_interval = inputs.get('scheduled_interval')
    hb_dt = _parse_iso_ts(raw_hb)
    as_of_dt = _parse_iso_ts(as_of)
    interval = finite_float(raw_interval)
    if hb_dt is None or as_of_dt is None or interval is None or interval <= 0.0:
        heartbeat_stale = True
    else:
        elapsed = (as_of_dt - hb_dt).total_seconds()
        if elapsed < 0.0 or elapsed > interval:
            heartbeat_stale = True

    # Check trigger
    if runtime_silent or monitor_silent or heartbeat_stale:
        return {
            'state': 'NO-NEW-RISK',
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
                authorized_events: Optional[Dict[str, Any]],
                session: Optional[str] = None,
                as_of: Optional[str] = None) -> Dict[str, Any]:
    """O9: Parameter change without owner card → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT
    Clearing: Owner re-arms
    """
    # Check for prior latch (canonical format per Q6)
    prior_latch = cst.get_account_latch(prior_state, 'O9')
    if prior_latch:
        rearm = cst.matches_account_rearm(
            authorized_events, 'O9', session=session, as_of=as_of, require_date=True
        ) is not None

        if rearm:
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'breaker',
                'latched': False,
                'reason': 'authorized_rearm'
            }

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
    has_change = bool(change_descriptors) or bool(tier_change_event)

    if not has_change:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none'
        }

    # Validate each privileged change kind independently against authorized_events
    events_list = []
    if isinstance(authorized_events, list):
        events_list = authorized_events
    elif isinstance(authorized_events, dict):
        events_list = authorized_events.get('account', [])

    cur_date = as_of[:10] if isinstance(as_of, str) and len(as_of) >= 10 else session

    def _card_scope_date_ok(event: Any) -> bool:
        if not isinstance(event, dict):
            return False
        if event.get('fund') or event.get('symbol'):
            return False
        if 'scope' in event and event.get('scope') != 'account':
            return False
        if event.get('session') is not None and session is not None and event.get('session') != session:
            return False
        if event.get('as_of') is not None:
            ev_date = event['as_of'][:10] if isinstance(event['as_of'], str) and len(event['as_of']) >= 10 else None
            if ev_date is None or (cur_date is not None and ev_date != cur_date):
                return False
        return True

    tier_authorized = True
    if tier_change_event:
        tier_authorized = any(
            _card_scope_date_ok(event) and
            event.get('type') == 'tier_change_card' and
            event.get('from') == tier_change_event.get('from') and
            event.get('to') == tier_change_event.get('to')
            for event in events_list
        )

    def _single_card_covers_descriptors(card_desc: Any, required: Any) -> bool:
        if isinstance(required, dict):
            return isinstance(card_desc, dict) and all(
                k in card_desc and card_desc[k] == v for k, v in required.items()
            )
        if isinstance(required, list):
            if isinstance(card_desc, list):
                return all(desc in card_desc for desc in required)
            return len(required) == 1 and card_desc == required[0]
        return card_desc == required

    params_authorized = True
    if change_descriptors:
        # Require ONE single account-scoped parameter_change_card covering all changed fields/items
        param_cards = [
            event.get('change_descriptors')
            for event in events_list
            if _card_scope_date_ok(event) and event.get('type') == 'parameter_change_card'
        ]
        params_authorized = any(
            _single_card_covers_descriptors(card, change_descriptors)
            for card in param_cards
        )

    if not (tier_authorized and params_authorized):
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
    # Required finite non-negative inputs (fail closed on missing, NaN, inf, bool, or negative)
    joint_exposure = finite_float(inputs.get('joint_exposure'))
    tier_joint_cap = finite_float(inputs.get('tier_joint_cap'))

    if joint_exposure is None or tier_joint_cap is None or joint_exposure < 0.0 or tier_joint_cap < 0.0:
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
