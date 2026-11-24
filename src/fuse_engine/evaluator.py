"""FUSE-1 reference engine evaluator.

Implements the §5.1 signature with all 24 rows fully evaluated.
"""

import copy
import hashlib
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from . import rows_loss
from . import rows_vehicle
from . import rows_ops
from . import state as st
from . import canonical_state as cst
from .canonical import finite_float


@lru_cache(maxsize=1)
def compute_engine_hash() -> str:
    """Compute canonical SHA-256 of sorted src/fuse_engine/*.py source bytes (§5.3)."""
    engine_dir = Path(__file__).resolve().parent
    hasher = hashlib.sha256()
    for py_file in sorted(engine_dir.glob('*.py')):
        hasher.update(py_file.read_bytes())
    return hasher.hexdigest()


def _fund_sort_key(symbol: str) -> tuple[int, str]:
    """Deterministic canonical fund order preserving [TQQQ, SOXL] legacy order (§0.4)."""
    if symbol == 'TQQQ':
        return (0, symbol)
    if symbol == 'SOXL':
        return (1, symbol)
    return (2, symbol)


# The 24 named row IDs per §4.3
ROW_IDS = [
    "L0", "L1", "L2", "L3", "L4", "L5", "L6",
    "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8", "O9",
    "J1"
]


def evaluate(
    spec_version: str,
    engine_hash: str,
    policy_hash: str,
    session: str,
    as_of: str,
    mode: str,
    validated_inputs: Dict[str, Any],
    prior_row_state: Optional[Dict[str, Any]],
    authorized_events: Optional[Dict[str, Any]]
) -> tuple[Dict[str, Any], Dict[str, str], Dict[str, Any]]:
    """Evaluate all 24 breaker rows and return effective state.

    Args:
        spec_version: Version of the breaker specification
        engine_hash: SHA-256 of the canonical engine bundle
        policy_hash: Hash of the loaded policy configuration
        session: Session identifier (YYYY-MM-DD)
        as_of: Evaluation timestamp (ISO 8601)
        mode: Enforcement mode ('shadow' in FUSE-1)
        validated_inputs: All required inputs for breaker evaluation
        prior_row_state: State from previous evaluation (latches, counters)
        authorized_events: Human re-arms, tier changes, owner commands

    Returns:
        (rows_by_ID, effective_state_by_scope, next_row_state) tuple where:
        - rows_by_ID: dict with 24 row IDs, each with state/would_have_tripped/kind/latched/reason + outputs
        - effective_state_by_scope: precedence-resolved state per scope
        - next_row_state: complete successor state for next evaluation
    """
    # A10 / Brief §0.4: FUSE-1 operates exclusively in read-only shadow mode
    if mode != 'shadow':
        raise ValueError(f"FUSE-1 operates in shadow mode only; forbidden mode={mode!r}")

    # §5.3: Always bind authentic canonical engine hash; reject mismatched 64-hex pinned digests
    canonical_engine_hash = compute_engine_hash()
    if (
        isinstance(engine_hash, str) and
        len(engine_hash) == 64 and
        all(c in '0123456789abcdefABCDEF' for c in engine_hash) and
        engine_hash.lower() != canonical_engine_hash
    ):
        raise ValueError(
            f"engine_hash mismatch: caller={engine_hash}, actual={canonical_engine_hash}"
        )

    # Initialize outputs
    if prior_row_state is None:
        prior_row_state = {}
    if authorized_events is None:
        authorized_events = {}

    # Initialize next_row_state
    next_row_state = st.init_next_state()

    # Get funds from inputs (sorted canonically for dict-order independence)
    funds = validated_inputs.get('funds', {})
    fund_symbols = sorted(funds.keys(), key=_fund_sort_key)

    # Build scopes: enumerate symbols from funds, pending_orders, AND durable O4 (Q6 wiring)
    # Use deterministic sorted ordering (A07.4: avoid PYTHONHASHSEED-dependent set iteration)
    all_symbols_set = set(fund_symbols)
    pending_orders = validated_inputs.get('pending_orders', {})
    all_symbols_set.update(pending_orders.keys())
    # Add symbols from durable O4 state
    if prior_row_state and 'O4' in prior_row_state:
        all_symbols_set.update(prior_row_state['O4'].keys())
    all_symbols = sorted(all_symbols_set)

    # Also track any prior restricted funds (V1/V2/V3/V4) omitted from current funds dict (A07.2 / A08)
    prior_latched_funds = set()
    if prior_row_state:
        for fn, fstate in prior_row_state.get('V1', {}).items():
            if isinstance(fstate, dict) and fstate.get('latched') and fn not in funds:
                prior_latched_funds.add(fn)
        for fn, mstate in prior_row_state.get('V2', {}).get('latched_mismatches', {}).items():
            if mstate and fn not in funds:
                prior_latched_funds.add(fn)
        for fn, pstate in prior_row_state.get('V2', {}).get('pending_adjustments', {}).items():
            if pstate and fn not in funds:
                prior_latched_funds.add(fn)
        for fn, v3state in prior_row_state.get('V3', {}).items():
            if isinstance(v3state, dict) and v3state.get('latched') and fn not in funds:
                prior_latched_funds.add(fn)
        for fn, v4state in prior_row_state.get('V4', {}).items():
            if isinstance(v4state, dict) and v4state.get('clearing_counter') is not None and fn not in funds:
                prior_latched_funds.add(fn)

    scopes = ['account']
    for symbol in fund_symbols:
        scopes.append(f'fund:{symbol}')
    for symbol in sorted(prior_latched_funds):
        scopes.append(f'fund:{symbol}')
    for symbol in all_symbols:
        scopes.append(f'symbol:{symbol}')
    scopes.append('joint')

    # Initialize rows_by_ID
    rows_by_ID = {}

    # ==== LOSS ROWS (L0-L6) - Account scope ====

    # L0 - exposure limit
    l0_result = rows_loss.evaluate_L0(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['L0'] = l0_result

    # L1 - drawdown D/3 interlock
    l1_result = rows_loss.evaluate_L1(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['L1'] = l1_result

    # L2 - drawdown 2D/3 breaker (canonical format per Q6)
    l2_result = rows_loss.evaluate_L2(validated_inputs, prior_row_state, authorized_events, session=session, as_of=as_of)
    rows_by_ID['L2'] = l2_result
    if l2_result['latched']:
        # Preserve original trip_session if already latched (§4.4 rule 3: persistence)
        prior_latch = cst.get_l2_latch(prior_row_state)
        trip_session = prior_latch['trip_session'] if prior_latch else session
        cst.set_l2_latch(next_row_state, trip_session)
    elif l2_result['reason'] == 'authorized_rearm':
        # Q4: clear latch on authorized re-arm - serialize as {"L2":{}}
        cst.clear_l2_latch(next_row_state)

    # L3 - drawdown D breaker (canonical format per Q6; A07.3 durable loss_record & trip_session)
    l3_result = rows_loss.evaluate_L3(validated_inputs, prior_row_state, authorized_events, session=session, as_of=as_of)
    rows_by_ID['L3'] = l3_result
    if l3_result['latched']:
        # Preserve original trip_session, cooling_off_until, and loss_record if already latched
        prior_latch = cst.get_l3_latch(prior_row_state)
        if prior_latch:
            trip_session = prior_latch['trip_session']
            cooling_off_until = prior_latch.get('cooling_off_until', trip_session)
            loss_record = prior_latch.get('loss_record')
        else:
            trip_session = session
            try:
                cooling_off_until = (date.fromisoformat(session) + timedelta(days=30)).isoformat()
            except ValueError:
                cooling_off_until = session
            hwm_raw = validated_inputs.get('high_water_mark')
            bk_raw = validated_inputs.get('bankroll')
            hwm_val = finite_float(hwm_raw)
            bk_val = finite_float(bk_raw)
            dd = (hwm_val - bk_val) / hwm_val if (hwm_val is not None and bk_val is not None and hwm_val > 0.0) else None
            loss_record = {
                'bankroll': bk_val,
                'high_water_mark': hwm_val,
                'tier': validated_inputs.get('tier'),
                'drawdown': dd
            }
        cst.set_l3_latch(next_row_state, trip_session, cooling_off_until, loss_record)
    elif l3_result['reason'] == 'authorized_rearm':
        # Q4: clear lock after cooling-off, preserve loss_record
        prior_latch = cst.get_l3_latch(prior_row_state)
        loss_record = prior_latch['loss_record'] if prior_latch and 'loss_record' in prior_latch else {}
        cst.clear_l3_lock(next_row_state, loss_record)
    elif prior_row_state and isinstance(prior_row_state.get('L3'), dict) and prior_row_state['L3'].get('loss_record') is not None:
        # Loss record is never cleared (§4.3 L3)
        cst.clear_l3_lock(next_row_state, prior_row_state['L3']['loss_record'])

    # L4 - one-session loss D/10 breaker (canonical per Q6; A07.3 preserve original trip_session)
    l4_result = rows_loss.evaluate_L4(validated_inputs, prior_row_state, authorized_events, session=session, as_of=as_of)
    rows_by_ID['L4'] = l4_result
    if l4_result['latched']:
        prior_latch = cst.get_account_latch(prior_row_state, 'L4')
        trip_session = prior_latch['trip_session'] if prior_latch and prior_latch.get('trip_session') else session
        cst.set_account_latch(next_row_state, 'L4', trip_session)
    elif l4_result['reason'] == 'authorized_rearm':
        next_row_state['L4'] = {}

    # L5 - market halt L1/L2 interlock (persists through remainder of trading session)
    l5_result = rows_loss.evaluate_L5(validated_inputs, prior_row_state, authorized_events, session, as_of=as_of)
    rows_by_ID['L5'] = l5_result
    prior_l5 = cst.get_l5_state(prior_row_state)
    l5_cur_date = as_of[:10] if isinstance(as_of, str) and len(as_of) >= 10 else session
    if l5_result['reason'] == 'market_halt_level_1_or_2':
        cst.set_l5_active_trip(next_row_state, l5_cur_date)
    elif l5_result['reason'] == 'clearing_period':
        cst.set_l5_active_trip(next_row_state, prior_l5['trip_session'] or l5_cur_date)
    elif prior_l5['active']:
        next_row_state['L5'] = {}
    else:
        cst.set_l5_fresh_count(next_row_state, prior_l5['fresh_session_count'] + 1)

    # Pre-compute O3 reconciliation state so L6 re-arm refuses if O3 reconciliation fails
    o3_result = rows_ops.evaluate_O3(validated_inputs, prior_row_state, authorized_events, session=session, as_of=as_of)
    o3_failed = o3_result['would_have_tripped'] or o3_result['state'] != 'NORMAL'

    # L6 - market halt L3 or 10% index fall breaker (canonical per Q6; rearm requires reconciliation)
    l6_result = rows_loss.evaluate_L6(
        validated_inputs, prior_row_state, authorized_events,
        session=session, as_of=as_of, o3_failed=o3_failed
    )
    rows_by_ID['L6'] = l6_result
    if l6_result['latched']:
        prior_latch = cst.get_account_latch(prior_row_state, 'L6')
        trip_session = prior_latch['trip_session'] if prior_latch and prior_latch.get('trip_session') else session
        cst.set_account_latch(next_row_state, 'L6', trip_session)
    elif l6_result['reason'] == 'authorized_rearm':
        next_row_state['L6'] = {}

    # ==== VEHICLE ROWS (V1-V7) - Fund/symbol scope ====

    # Initialize fund-level outputs
    v1_outputs = {}
    v2_outputs = {}
    v3_outputs = {}
    v4_outputs = {}
    v5_outputs = {}
    v6_outputs = {}
    v7_outputs = {}

    market_closed = (
        validated_inputs.get('session_calendar_status') in ('holiday', 'closed', 'market_closed') or
        validated_inputs.get('exchange_status') in ('holiday', 'closed')
    )

    for symbol in fund_symbols:
        fund_inputs = funds[symbol]

        # V1 - tracking deviation (canonical format per Q6; 1-session and 5-session per §4.3/§6)
        v1_result = rows_vehicle.evaluate_V1(
            fund_inputs, prior_row_state, authorized_events, symbol,
            session=session, market_closed=market_closed
        )
        session_returns = v1_result.pop('_session_returns', None)
        v1_outputs[symbol] = v1_result
        if session_returns is not None:
            cst.set_v1_history(next_row_state, symbol, session_returns)
        if v1_result['latched']:
            # Preserve original trip_session and deviation if already latched (§4.4 rule 3)
            prior_latch = cst.get_v1_latch(prior_row_state, symbol)
            if prior_latch:
                trip_session = prior_latch['trip_session']
                deviation = prior_latch['deviation']
            else:
                trip_session = session
                deviation = v1_result.get('deviation', 0.0)
            cst.set_v1_latch(next_row_state, symbol, trip_session, deviation)
        elif v1_result['reason'] == 'authorized_rearm':
            # Q4: clear latch on authorized re-arm - serialize as {"V1":{}}
            cst.clear_v1_latch(next_row_state, symbol)

        # V2 - corporate action
        v2_result = rows_vehicle.evaluate_V2(fund_inputs, prior_row_state, authorized_events, symbol)
        v2_reconcile_target = v2_result.pop('_v2_reconcile_target', None)
        v2_outputs[symbol] = v2_result

        # B1: Store V2 latches and mismatch details (SUC-02) - canonical format per Q6
        if v2_result['latched']:
            # For new reconciliation_mismatch, store mismatch details
            if v2_result['reason'] == 'reconciliation_mismatch':
                corporate_action = fund_inputs.get('corporate_action', {})
                lv = fund_inputs.get('ledger_value')
                bv = fund_inputs.get('broker_value')
                try:
                    mismatch_amt = abs(float(lv) - float(bv)) if (lv is not None and bv is not None) else None
                except (TypeError, ValueError):
                    mismatch_amt = None
                mismatch_details = {
                    'type': corporate_action.get('type') if isinstance(corporate_action, dict) else 'unknown',
                    'ledger_value': lv,
                    'broker_value': bv,
                    'mismatch': mismatch_amt
                }
                cst.set_v2_latched_mismatch(next_row_state, symbol, mismatch_details)
                if cst.get_v2_pending_adjustment(prior_row_state, symbol):
                    cst.clear_v2_pending_adjustment(next_row_state, symbol)
            # For persisting latch (latched_prior_mismatch), carry forward details
            elif v2_result['reason'] == 'latched_prior_mismatch':
                prior_mismatch = cst.get_v2_latched_mismatch(prior_row_state, symbol)
                if prior_mismatch:
                    cst.set_v2_latched_mismatch(next_row_state, symbol, prior_mismatch)
        else:
            # Clear latch on re-arm (Q4 short-circuit)
            if v2_result['reason'] == 'authorized_rearm':
                cst.clear_v2_latched_mismatch(next_row_state, symbol)

        # Update pending state (B1 canonical format per Q6; never overwrite unresolved prior action)
        prior_pending = cst.get_v2_pending_adjustment(prior_row_state, symbol)
        if v2_result['reason'] in ['pending_corporate_action', 'pending_corporate_action_carried']:
            corporate_action = fund_inputs.get('corporate_action')
            if v2_reconcile_target == 'primary' and prior_pending:
                q_list = list(prior_pending.get('queued_actions') or [])
                promoted = q_list.pop(0)
                new_pending = {
                    'type': promoted.get('type'),
                    'ratio': promoted.get('ratio'),
                    'awaiting_reconciliation': True
                }
                if q_list:
                    new_pending['queued_actions'] = q_list
                cst.set_v2_pending_adjustment(next_row_state, symbol, new_pending)
            elif isinstance(v2_reconcile_target, tuple) and v2_reconcile_target[0] == 'queued' and prior_pending:
                new_pending = copy.deepcopy(prior_pending)
                q_list = list(new_pending.get('queued_actions') or [])
                idx_to_pop = v2_reconcile_target[1]
                if 0 <= idx_to_pop < len(q_list):
                    q_list.pop(idx_to_pop)
                if q_list:
                    new_pending['queued_actions'] = q_list
                else:
                    new_pending.pop('queued_actions', None)
                cst.set_v2_pending_adjustment(next_row_state, symbol, new_pending)
            elif prior_pending:
                new_pending = copy.deepcopy(prior_pending)
                if isinstance(corporate_action, dict) and corporate_action.get('type'):
                    inc_type = corporate_action.get('type')
                    inc_ratio = corporate_action.get('ratio')
                    matches_primary = (inc_type == new_pending.get('type') and inc_ratio == new_pending.get('ratio'))
                    q_list = list(new_pending.get('queued_actions') or [])
                    matches_queued = any(
                        isinstance(q, dict) and q.get('type') == inc_type and q.get('ratio') == inc_ratio
                        for q in q_list
                    )
                    if not matches_primary and not matches_queued:
                        q_list.append({'type': inc_type, 'ratio': inc_ratio})
                        new_pending['queued_actions'] = q_list
                cst.set_v2_pending_adjustment(next_row_state, symbol, new_pending)
            elif isinstance(corporate_action, dict) and corporate_action.get('type'):
                pending = {
                    'type': corporate_action.get('type'),
                    'ratio': corporate_action.get('ratio'),
                    'awaiting_reconciliation': True
                }
                cst.set_v2_pending_adjustment(next_row_state, symbol, pending)
        elif v2_result['reason'] in ('exact_reconciliation_auto_clear', 'authorized_rearm'):
            # Clear pending on exact reconciliation or authorized re-arm (Q4)
            cst.clear_v2_pending_adjustment(next_row_state, symbol)
        elif v2_result['reason'] != 'reconciliation_mismatch':
            if prior_pending:
                cst.set_v2_pending_adjustment(next_row_state, symbol, copy.deepcopy(prior_pending))

        # V3 - fund event (canonical format per Q6)
        v3_result = rows_vehicle.evaluate_V3(fund_inputs, prior_row_state, authorized_events, symbol)
        v3_outputs[symbol] = v3_result
        if v3_result['latched']:
            # Preserve original trip_session if already latched (§4.4 rule 3: persistence)
            prior_latch = cst.get_fund_latch(prior_row_state, 'V3', symbol)
            trip_session = prior_latch['trip_session'] if prior_latch else session
            details = {'reason': v3_result['reason'], 'fund_event': v3_result.get('fund_event')}
            cst.set_fund_latch(next_row_state, 'V3', symbol, trip_session, details)
        elif v3_result['reason'] == 'authorized_rearm':
            if 'V3' not in next_row_state:
                next_row_state['V3'] = {}

        # V4 - extreme volatility (B4 canonical format per Q6; closed/holiday skips increment)
        v4_result = rows_vehicle.evaluate_V4(
            fund_inputs, prior_row_state, authorized_events, symbol, session,
            market_closed=market_closed
        )
        preserve_v4_session = v4_result.pop('_preserve_prior_v4_session', False)
        v4_outputs[symbol] = v4_result
        # Update V4 state based on result reason - counter now in outputs
        if preserve_v4_session:
            prior_v4 = cst.get_v4_state(prior_row_state, symbol)
            if prior_v4['clearing_counter'] is not None:
                cst.set_v4_state(
                    next_row_state, symbol,
                    prior_v4['clearing_counter'],
                    prior_v4['last_session_below_threshold']
                )
        elif v4_result['reason'] == 'volatility_at_or_above_2x':
            # Initial trip: volatility HIGH, no "last session below threshold" yet
            counter = v4_result.get('outputs', {}).get('clearing_counter', 0)
            cst.set_v4_state(next_row_state, symbol, counter, None)
        elif v4_result['reason'] == 'volatility_below_2x_but_not_yet_cleared':
            # Clearing phase: record this session as below threshold
            counter = v4_result.get('outputs', {}).get('clearing_counter', 0)
            cst.set_v4_state(next_row_state, symbol, counter, session)
        elif v4_result['reason'] == 'cleared_after_ten_sessions':
            # At count 10, report 10 and remove the fund entry per Q1
            cst.clear_v4_state(next_row_state, symbol)
        elif v4_result['reason'] == 'missing_input':
            # A07.1: Missing forecast earns zero clearing credit but MUST preserve active V4 counter
            prior_v4 = cst.get_v4_state(prior_row_state, symbol)
            if prior_v4['clearing_counter'] is not None:
                cst.set_v4_state(
                    next_row_state, symbol,
                    prior_v4['clearing_counter'],
                    prior_v4['last_session_below_threshold']
                )

        # V5 - decay monitor (B5 canonical format per Q6; fallback to top-level policy v5_tolerance)
        v5_inputs = fund_inputs if 'v5_tolerance' in fund_inputs else {**fund_inputs, 'v5_tolerance': validated_inputs.get('v5_tolerance')}
        v5_result = rows_vehicle.evaluate_V5(v5_inputs, prior_row_state, authorized_events, symbol, session)
        v5_outputs[symbol] = v5_result
        # Update V5 state - session identity per flag 4
        new_count = v5_result['outputs']['consecutive_sessions_beyond_tolerance']
        escalated = v5_result['outputs']['escalated_to_v1']
        cst.set_v5_state(next_row_state, symbol, new_count, escalated, session)

        # V6 - carrying cost
        v6_result = rows_vehicle.evaluate_V6(fund_inputs, prior_row_state, authorized_events, symbol)
        v6_outputs[symbol] = v6_result

        # V7 - quote/liquidity (fallback to top-level policy v7_spread_width)
        v7_inputs = fund_inputs if 'v7_spread_width' in fund_inputs else {**fund_inputs, 'v7_spread_width': validated_inputs.get('v7_spread_width')}
        v7_result = rows_vehicle.evaluate_V7(v7_inputs, prior_row_state, authorized_events, symbol)
        v7_outputs[symbol] = v7_result

    # Aggregate vehicle rows into single row outputs
    rows_by_ID['V1'] = aggregate_fund_row(v1_outputs)
    rows_by_ID['V2'] = aggregate_fund_row(v2_outputs)
    rows_by_ID['V3'] = aggregate_fund_row(v3_outputs)
    rows_by_ID['V4'] = aggregate_fund_row(v4_outputs)
    # V5, V6 are diagnostic with structured row-level outputs (Fix 2)
    # V7 is symbol-scoped interlock (not diagnostic)
    rows_by_ID['V5'] = aggregate_diagnostic_row(v5_outputs)
    rows_by_ID['V6'] = aggregate_diagnostic_row(v6_outputs)
    rows_by_ID['V7'] = aggregate_fund_row(v7_outputs, symbol_scoped=True, emit_scope_keys=False)

    # V2, V4, V5 state now written inline using canonical accessors per Q6

    # ==== OPERATIONS ROWS (O1-O9, J1) ====

    # O1 - required inputs stale/missing (B3; same-day stale->fresh cannot clear mid-session)
    o1_result = rows_ops.evaluate_O1(validated_inputs, prior_row_state, authorized_events, session, as_of=as_of)
    rows_by_ID['O1'] = o1_result
    o1_state = cst.get_o1_fresh_state(prior_row_state)
    o1_cur_date = as_of[:10] if isinstance(as_of, str) and len(as_of) >= 10 else session
    if o1_result['reason'] == 'clearing_period':
        cst.set_o1_fresh_state(
            next_row_state, 0, o1_cur_date,
            last_tripped_session=o1_state.get('last_tripped_session') or o1_cur_date
        )
    elif not o1_result['would_have_tripped']:
        if o1_state.get('last_session') == o1_cur_date and o1_state.get('fresh_session_count', 0) == 0:
            # Stale->fresh transition within the same session must NOT count as a full clean session
            cst.set_o1_fresh_state(next_row_state, 0, o1_cur_date)
        elif o1_state.get('last_session') == o1_cur_date:
            cst.set_o1_fresh_state(next_row_state, o1_state['fresh_session_count'], o1_cur_date)
        else:
            fresh_count = o1_state['fresh_session_count'] + 1
            cst.set_o1_fresh_state(next_row_state, fresh_count, o1_cur_date)
    else:
        # Operational stale/missing trip records last_tripped_session so same-day recovery cannot clear
        if o1_result['reason'] == 'stale_or_missing_input':
            cst.set_o1_fresh_state(next_row_state, 0, o1_cur_date, last_tripped_session=o1_cur_date)
        else:
            cst.set_o1_fresh_state(next_row_state, 0, o1_cur_date)

    # O2 - session calendar
    o2_result = rows_ops.evaluate_O2(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O2'] = o2_result

    # O3 - reconciliation mismatch (already evaluated before L6)
    rows_by_ID['O3'] = o3_result
    if o3_result['latched']:
        # Preserve original trip_session if already latched (§4.4 rule 3: persistence)
        prior_latch = cst.get_account_latch(prior_row_state, 'O3')
        trip_session = prior_latch['trip_session'] if prior_latch else session
        cst.set_account_latch(next_row_state, 'O3', trip_session)
    elif o3_result['reason'] == 'authorized_rearm':
        next_row_state['O3'] = {}

    # O4 - order timeout (canonical format per Q6, enumerate from all sources)
    o4_outputs = {}
    restart_marker = validated_inputs.get('restart_marker')

    for symbol in all_symbols:
        # Build order input for this symbol
        order_input = {}
        if symbol in funds:
            order_input = funds[symbol].copy()

        # Add pending order if present
        if symbol in pending_orders:
            order_input['o4_pending_order'] = pending_orders[symbol]

        # Forward restart_marker into O4 evaluation (Q6)
        if restart_marker:
            order_input['restart_marker'] = restart_marker

        o4_result = rows_ops.evaluate_O4(order_input, prior_row_state, authorized_events, symbol)
        o4_outputs[symbol] = o4_result

        # Store O4 state using canonical accessors (Q6)
        if o4_result.get('original_order_id'):
            order_id = o4_result['original_order_id']
            status = 'unknown'
            cst.set_o4_pending_order(next_row_state, symbol, order_id, status)
        elif o4_result['reason'] in ('original_order_terminal_status_received', 'order_filled'):
            # Clear resolved order
            cst.clear_o4_pending_order(next_row_state, symbol)

    rows_by_ID['O4'] = aggregate_fund_row(o4_outputs, symbol_scoped=True)

    # O5 - pre-trade limits (B2 canonical format per Q6)
    o5_result = rows_ops.evaluate_O5(validated_inputs, prior_row_state, authorized_events, session, as_of=as_of)
    rows_by_ID['O5'] = o5_result
    # O5 state: preserve session rejection count & latch across mixed PASS/REJECT checks in same session
    if o5_result['reason'] == 'authorized_rearm':
        next_row_state['O5'] = {}
    elif o5_result['would_have_tripped']:
        count = o5_result.get('rejection_count_this_session', 1)
        latched = o5_result['latched']
        cst.set_o5_state(next_row_state, count, session, latched)
    else:
        prior_o5 = cst.get_o5_state(prior_row_state)
        if prior_o5['last_rejection_session'] == session and (prior_o5['rejection_count'] > 0 or prior_o5['latched']):
            cst.set_o5_state(next_row_state, prior_o5['rejection_count'], session, prior_o5['latched'])

    # O6 - policy hash mismatch (canonical format per Q6)
    o6_result = rows_ops.evaluate_O6(validated_inputs, prior_row_state, authorized_events, session=session, as_of=as_of)
    rows_by_ID['O6'] = o6_result
    if o6_result['latched']:
        # Preserve original trip_session if already latched (§4.4 rule 3: persistence)
        prior_latch = cst.get_account_latch(prior_row_state, 'O6')
        trip_session = prior_latch['trip_session'] if prior_latch else session
        cst.set_account_latch(next_row_state, 'O6', trip_session)
    elif o6_result['reason'] == 'authorized_rearm':
        next_row_state['O6'] = {}

    # O7 - dead man's switch (canonical format per Q6)
    o7_result = rows_ops.evaluate_O7(validated_inputs, prior_row_state, authorized_events, as_of=as_of, session=session)
    rows_by_ID['O7'] = o7_result
    if o7_result['latched']:
        # Preserve original trip_session if already latched (§4.4 rule 3: persistence)
        prior_latch = cst.get_account_latch(prior_row_state, 'O7')
        trip_session = prior_latch['trip_session'] if prior_latch else session
        cst.set_account_latch(next_row_state, 'O7', trip_session)
    elif o7_result['reason'] == 'authorized_rearm':
        next_row_state['O7'] = {}

    # O8 - kill switch
    o8_result = rows_ops.evaluate_O8(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O8'] = o8_result

    # O9 - unauthorized parameter change (canonical format per Q6)
    o9_result = rows_ops.evaluate_O9(validated_inputs, prior_row_state, authorized_events, session=session, as_of=as_of)
    rows_by_ID['O9'] = o9_result
    if o9_result['latched']:
        # Preserve original trip_session if already latched (§4.4 rule 3: persistence)
        prior_latch = cst.get_account_latch(prior_row_state, 'O9')
        trip_session = prior_latch['trip_session'] if prior_latch else session
        cst.set_account_latch(next_row_state, 'O9', trip_session)
    elif o9_result['reason'] == 'authorized_rearm':
        next_row_state['O9'] = {}

    # J1 - joint exposure limit
    j1_result = rows_ops.evaluate_J1(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['J1'] = j1_result

    # Preserve durable scope state for funds/symbols not in current inputs (Q6 & A07.2)
    # V1, V2, V3, V4, V5, O4 state must survive across calls even when scope is absent
    if prior_row_state:
        # Preserve V1 state (latches and 5-session history) for absent funds, and reflect active latches
        for fund in sorted(prior_row_state.get('V1', {}).keys()):
            v1_fund_state = prior_row_state['V1'][fund]
            if fund not in fund_symbols and isinstance(v1_fund_state, dict) and v1_fund_state:
                if 'V1' not in next_row_state:
                    next_row_state['V1'] = {}
                if fund not in next_row_state['V1']:
                    next_row_state['V1'][fund] = copy.deepcopy(v1_fund_state)
                if v1_fund_state.get('latched'):
                    v1_outputs[fund] = {
                        'state': 'NO-NEW-RISK',
                        'would_have_tripped': True,
                        'kind': 'breaker',
                        'latched': True,
                        'reason': 'latched_prior_trip',
                        'fund': fund
                    }

        # Preserve V2 latched mismatches & pending adjustments for absent funds, and reflect in V2
        prior_v2 = prior_row_state.get('V2', {})
        if isinstance(prior_v2, dict):
            for fund in sorted(prior_v2.get('latched_mismatches', {}).keys()):
                mismatch = prior_v2['latched_mismatches'][fund]
                if fund not in fund_symbols and mismatch:
                    cst.set_v2_latched_mismatch(next_row_state, fund, mismatch)
                    v2_outputs[fund] = {
                        'state': 'HALT',
                        'would_have_tripped': True,
                        'kind': 'interlock_or_breaker',
                        'latched': True,
                        'reason': 'latched_prior_mismatch',
                        'fund': fund
                    }
            for fund in sorted(prior_v2.get('pending_adjustments', {}).keys()):
                pending = prior_v2['pending_adjustments'][fund]
                if fund not in fund_symbols and pending:
                    cst.set_v2_pending_adjustment(next_row_state, fund, pending)
                    if fund not in v2_outputs:
                        v2_outputs[fund] = {
                            'state': 'HALT',
                            'would_have_tripped': True,
                            'kind': 'interlock_or_breaker',
                            'latched': False,
                            'reason': 'pending_corporate_action_carried',
                            'fund': fund
                        }

        # Preserve V3 latches for absent funds
        for fund in sorted(prior_row_state.get('V3', {}).keys()):
            v3_fund_state = prior_row_state['V3'][fund]
            if fund not in fund_symbols and isinstance(v3_fund_state, dict) and v3_fund_state.get('latched'):
                if 'V3' not in next_row_state:
                    next_row_state['V3'] = {}
                if fund not in next_row_state['V3']:
                    next_row_state['V3'][fund] = v3_fund_state
                v3_outputs[fund] = {
                    'state': 'DE-RISK',
                    'would_have_tripped': True,
                    'kind': 'breaker',
                    'latched': True,
                    'reason': 'latched_prior_trip',
                    'fund': fund
                }

        # Preserve V4 state and active restrictions for funds omitted from current inputs (A08)
        if 'V4' in prior_row_state:
            if 'V4' not in next_row_state:
                next_row_state['V4'] = {}
            for fund in sorted(prior_row_state['V4'].keys()):
                v4_fund_state = prior_row_state['V4'][fund]
                if fund not in fund_symbols:
                    if fund not in next_row_state['V4']:
                        next_row_state['V4'][fund] = copy.deepcopy(v4_fund_state)
                    if isinstance(v4_fund_state, dict) and v4_fund_state.get('clearing_counter') is not None:
                        v4_outputs[fund] = {
                            'state': 'NO-NEW-RISK',
                            'would_have_tripped': True,
                            'kind': 'interlock',
                            'latched': False,
                            'reason': 'volatility_below_2x_but_not_yet_cleared',
                            'fund': fund,
                            'outputs': {'clearing_counter': v4_fund_state['clearing_counter']}
                        }

        # Re-aggregate V1/V2/V3/V4 if absent restricted funds were carried into outputs
        if prior_latched_funds:
            rows_by_ID['V1'] = aggregate_fund_row(v1_outputs)
            rows_by_ID['V2'] = aggregate_fund_row(v2_outputs)
            rows_by_ID['V3'] = aggregate_fund_row(v3_outputs)
            rows_by_ID['V4'] = aggregate_fund_row(v4_outputs)

        # Preserve V5 state for funds not evaluated
        if 'V5' in prior_row_state:
            if 'V5' not in next_row_state:
                next_row_state['V5'] = {}
            for fund, v5_fund_state in prior_row_state['V5'].items():
                if fund not in fund_symbols and fund not in next_row_state['V5']:
                    next_row_state['V5'][fund] = v5_fund_state

        # O4 already preserved via symbol enumeration (all_symbols includes prior O4 keys)

    # ==== PRECEDENCE RESOLUTION ====
    # Per §4.1: HALT > ORDER-UNKNOWN > DE-RISK > NO-NEW-RISK > NORMAL
    # Account HALT dominates all narrower scopes

    effective_state_by_scope = {}

    # Precedence order
    precedence = ['HALT', 'ORDER-UNKNOWN', 'DE-RISK', 'NO-NEW-RISK', 'NORMAL']

    # First, resolve account scope to check for dominance (Q5)
    account_states = []
    for row_id in ['L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'O1', 'O2', 'O3', 'O5', 'O6', 'O7', 'O8', 'O9']:
        row_result = rows_by_ID[row_id]
        account_states.append(row_result['state'])

    account_state = 'NORMAL'
    for state in precedence:
        if state in account_states:
            account_state = state
            break

    effective_state_by_scope['account'] = account_state

    # A08 / Q5: Account HALT dominates every narrower scope (§4.1), including joint
    if account_state == 'HALT':
        for scope in scopes:
            effective_state_by_scope[scope] = 'HALT'
    else:
        # Account not HALT - resolve each scope independently
        for scope in scopes:
            if scope == 'account':
                continue  # Already resolved above

            states_for_scope = []

            if scope.startswith('fund:'):
                symbol = scope.split(':')[1]
                # Fund-scoped rows
                if symbol in v1_outputs:
                    states_for_scope.append(v1_outputs[symbol]['state'])
                if symbol in v2_outputs:
                    states_for_scope.append(v2_outputs[symbol]['state'])
                if symbol in v3_outputs:
                    states_for_scope.append(v3_outputs[symbol]['state'])
                if symbol in v4_outputs:
                    states_for_scope.append(v4_outputs[symbol]['state'])
                if symbol in v5_outputs:
                    states_for_scope.append(v5_outputs[symbol]['state'])
            elif scope.startswith('symbol:'):
                symbol = scope.split(':')[1]
                # Symbol-scoped rows (O4, V7)
                if symbol in o4_outputs:
                    states_for_scope.append(o4_outputs[symbol]['state'])
                if symbol in v7_outputs:
                    states_for_scope.append(v7_outputs[symbol]['state'])
            elif scope == 'joint':
                # Joint-scoped rows
                states_for_scope.append(j1_result['state'])

            # Resolve by precedence
            effective_state = 'NORMAL'
            for state in precedence:
                if state in states_for_scope:
                    effective_state = state
                    break

            effective_state_by_scope[scope] = effective_state

    # G6 (F1-A10 / §5.3): Bind spec_version, canonical engine_hash, and shadow safety assertions
    next_row_state['spec_version'] = spec_version
    next_row_state['engine_hash'] = canonical_engine_hash
    next_row_state['enforcement_mode'] = 'shadow_would_have_tripped'
    next_row_state['loss_breakers_armed'] = False

    return (rows_by_ID, effective_state_by_scope, next_row_state)


def aggregate_fund_row(
    fund_outputs: Dict[str, Dict[str, Any]],
    symbol_scoped: bool = False,
    emit_scope_keys: bool = True
) -> Dict[str, Any]:
    """Aggregate per-fund row outputs into a single row output.

    For fund-scoped rows, returns the most restrictive state across all funds.
    """
    if not fund_outputs:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none'
        }

    # Order-independent deterministic key traversal (canonical order across dict permutations)
    ordered_keys = sorted(fund_outputs.keys()) if symbol_scoped else sorted(fund_outputs.keys(), key=_fund_sort_key)
    sample = fund_outputs[ordered_keys[0]]
    kind = sample['kind']

    # Aggregate: take most restrictive state (Fix 2: single-token reason)
    precedence = ['HALT', 'ORDER-UNKNOWN', 'DE-RISK', 'NO-NEW-RISK', 'NORMAL']
    most_restrictive = 'NORMAL'
    any_tripped = False
    any_latched = False
    reasons = []
    affected_funds = []

    for symbol in ordered_keys:
        result = fund_outputs[symbol]
        state = result['state']
        if precedence.index(state) < precedence.index(most_restrictive):
            most_restrictive = state
        if result['would_have_tripped']:
            any_tripped = True
            affected_funds.append(symbol)
        if result.get('latched'):
            any_latched = True
        if result['reason'] != 'none':
            reasons.append((symbol, result['reason']))

    # Determine single reason token (Fix 2 + Fix 3: golden expects single token with fund suffix where applicable)
    if not reasons:
        reason = 'none'
    elif len(reasons) == 1:
        symbol, base_reason = reasons[0]
        needs_suffix = (len(fund_outputs) > 1 and
                       base_reason in ['pending_corporate_action', 'pending_corporate_action_carried'])
        reason = f'{base_reason}_{symbol}' if needs_suffix else base_reason
    else:
        unique_reasons = set(r for _, r in reasons)
        if len(unique_reasons) == 1:
            reason = next(iter(unique_reasons))
            for symbol in ordered_keys:
                if reason.endswith(f'_{symbol}'):
                    reason = reason[:-len(f'_{symbol}')]
                    break
        else:
            reason = ', '.join(f"{sym}:{r}" for sym, r in reasons)

    # Build aggregate output
    aggregate = {
        'state': most_restrictive,
        'would_have_tripped': any_tripped,
        'kind': kind,
        'latched': any_latched,
        'reason': reason
    }

    # Include per-fund outputs in deterministic order
    if 'outputs' in sample:
        if len(ordered_keys) == 1:
            single_fund = ordered_keys[0]
            aggregate['outputs'] = copy.deepcopy(fund_outputs[single_fund].get('outputs', {}))
        else:
            aggregate['outputs'] = {
                symbol: copy.deepcopy(fund_outputs[symbol].get('outputs', {}))
                for symbol in ordered_keys
            }

    # For fund/symbol-scoped rows, include affected funds/symbols
    if emit_scope_keys:
        if len(ordered_keys) == 1:
            single_key = ordered_keys[0]
            single_result = fund_outputs[single_key]
            if symbol_scoped:
                aggregate['symbol'] = single_result.get('symbol', single_key)
                if affected_funds:
                    aggregate['symbols'] = affected_funds
            else:
                aggregate['fund'] = single_result.get('fund', single_key)
        elif affected_funds:
            if symbol_scoped:
                aggregate['symbols'] = affected_funds
            else:
                already_suffixed = any(reason.endswith(f'_{s}') for s in affected_funds)
                if len(affected_funds) == 1 and not already_suffixed:
                    aggregate['fund'] = affected_funds[0]
                elif len(affected_funds) > 1:
                    aggregate['funds'] = affected_funds

    # G1.3: Preserve declared successor evidence fields (deviation, original_order_id)
    if len(ordered_keys) == 1:
        single_fund = ordered_keys[0]
        single_result = fund_outputs[single_fund]

        if 'deviation' in single_result:
            aggregate['deviation'] = single_result['deviation']

        if 'original_order_id' in single_result:
            aggregate['original_order_id'] = single_result['original_order_id']

    return aggregate


def aggregate_diagnostic_row(fund_outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate diagnostic rows (V5, V6) in a deterministic, dict-order-independent manner."""
    if not fund_outputs:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'diagnostic',
            'latched': False,
            'reason': 'none'
        }

    ordered_keys = sorted(fund_outputs.keys(), key=_fund_sort_key)
    precedence = ['HALT', 'ORDER-UNKNOWN', 'DE-RISK', 'NO-NEW-RISK', 'NORMAL']
    disposition_rank = {
        'UNRESOLVED-FAIL-CLOSED': 0,
        'beyond_tolerance': 1,
        'missing_data': 2,
        'invalid_data': 2,
        'benign': 3,
    }

    def _diagnostic_severity(sym: str) -> tuple:
        res = fund_outputs[sym]
        outs = res.get('outputs', {})
        disp = outs.get('disposition', 'benign')
        return (
            precedence.index(res['state']),
            0 if res.get('would_have_tripped') else 1,
            0 if outs.get('escalated_to_v1') else 1,
            0 if outs.get('notify') else 1,
            0 if outs.get('exceeded') else 1,
            disposition_rank.get(disp, 4),
            0 if res.get('reason', 'none') != 'none' else 1,
            -(outs.get('consecutive_sessions_beyond_tolerance') or 0),
            _fund_sort_key(sym),
        )

    worst_sym = min(ordered_keys, key=_diagnostic_severity)
    worst_result = fund_outputs[worst_sym]
    kind = worst_result['kind']

    most_restrictive = worst_result['state']
    any_tripped = any(fund_outputs[s]['would_have_tripped'] for s in ordered_keys)

    raw_reason = worst_result.get('reason', 'none')
    reason = raw_reason[:-len(f'_{worst_sym}')] if raw_reason.endswith(f'_{worst_sym}') else raw_reason

    aggregate = {
        'state': most_restrictive,
        'would_have_tripped': any_tripped,
        'kind': kind,
        'latched': False,  # Diagnostics don't latch
        'reason': reason
    }

    if 'outputs' in worst_result:
        agg_outputs = copy.deepcopy(worst_result['outputs'])
        if 'notify' in agg_outputs:
            agg_outputs['notify'] = any(
                bool(fund_outputs[s].get('outputs', {}).get('notify'))
                for s in ordered_keys
            )
        if 'exceeded' in agg_outputs:
            agg_outputs['exceeded'] = any(
                bool(fund_outputs[s].get('outputs', {}).get('exceeded'))
                for s in ordered_keys
            )
        aggregate['outputs'] = agg_outputs

    if len(ordered_keys) == 1:
        single_fund = ordered_keys[0]
        aggregate['fund'] = fund_outputs[single_fund].get('fund', single_fund)

    return aggregate
