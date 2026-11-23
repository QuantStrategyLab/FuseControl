"""FUSE-1 reference engine evaluator.

Implements the §5.1 signature with all 24 rows fully evaluated.
"""

from typing import Any, Dict, Optional
from . import rows_loss
from . import rows_vehicle
from . import rows_ops
from . import state as st


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
    # Initialize outputs
    if prior_row_state is None:
        prior_row_state = {}
    if authorized_events is None:
        authorized_events = {}

    # Initialize next_row_state
    next_row_state = st.init_next_state()

    # Get funds from inputs
    funds = validated_inputs.get('funds', {})
    fund_symbols = list(funds.keys())

    # Build the six scope keys: account, fund:SYMBOL for each fund, symbol:SYMBOL for each, joint
    scopes = ['account']
    for symbol in fund_symbols:
        scopes.append(f'fund:{symbol}')
    for symbol in fund_symbols:
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

    # L2 - drawdown 2D/3 breaker
    l2_result = rows_loss.evaluate_L2(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['L2'] = l2_result
    if l2_result['latched']:
        st.set_latch(next_row_state, 'L2', 'account', True, l2_result['reason'])

    # L3 - drawdown D breaker
    l3_result = rows_loss.evaluate_L3(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['L3'] = l3_result
    if l3_result['latched']:
        st.set_latch(next_row_state, 'L3', 'account', True, l3_result['reason'])

    # L4 - one-session loss D/10 breaker
    l4_result = rows_loss.evaluate_L4(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['L4'] = l4_result
    if l4_result['latched']:
        st.set_latch(next_row_state, 'L4', 'account', True, l4_result['reason'])

    # L5 - market halt L1/L2 interlock
    l5_result = rows_loss.evaluate_L5(validated_inputs, prior_row_state, authorized_events, session)
    rows_by_ID['L5'] = l5_result
    # Update L5 fresh session counter if not triggered
    if not l5_result['would_have_tripped']:
        fresh_count = st.get_counter(prior_row_state, 'L5', 'account', 'fresh_sessions', default=0)
        st.set_counter(next_row_state, 'L5', 'account', 'fresh_sessions', fresh_count + 1)
    else:
        st.set_counter(next_row_state, 'L5', 'account', 'fresh_sessions', 0)
        if l5_result.get('latched'):
            st.set_latch(next_row_state, 'L5', 'account', True, l5_result['reason'])

    # L6 - market halt L3 or 10% index fall breaker
    l6_result = rows_loss.evaluate_L6(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['L6'] = l6_result
    if l6_result['latched']:
        st.set_latch(next_row_state, 'L6', 'account', True, l6_result['reason'])

    # ==== VEHICLE ROWS (V1-V7) - Fund/symbol scope ====

    # Initialize fund-level outputs
    v1_outputs = {}
    v2_outputs = {}
    v3_outputs = {}
    v4_outputs = {}
    v5_outputs = {}
    v6_outputs = {}
    v7_outputs = {}
    v2_pending = {}
    v4_last_increment = {}
    v5_escalated = {}

    for symbol in fund_symbols:
        fund_inputs = funds[symbol]

        # V1 - tracking deviation
        v1_result = rows_vehicle.evaluate_V1(fund_inputs, prior_row_state, authorized_events, symbol)
        v1_outputs[symbol] = v1_result
        if v1_result['latched']:
            st.set_latch(next_row_state, 'V1', f'fund:{symbol}', True, v1_result['reason'])

        # V2 - corporate action
        v2_result = rows_vehicle.evaluate_V2(fund_inputs, prior_row_state, authorized_events, symbol)
        v2_outputs[symbol] = v2_result
        if v2_result['latched']:
            st.set_latch(next_row_state, 'V2', f'fund:{symbol}', True, v2_result['reason'])
        # Update pending state (B1)
        if v2_result['reason'] in ['pending_corporate_action', 'pending_corporate_action_carried']:
            corporate_action = fund_inputs.get('corporate_action')
            if isinstance(corporate_action, dict):
                v2_pending[symbol] = {
                    'type': corporate_action.get('type'),
                    'ratio': corporate_action.get('ratio'),
                    'awaiting_reconciliation': True
                }

        # V3 - fund event
        v3_result = rows_vehicle.evaluate_V3(fund_inputs, prior_row_state, authorized_events, symbol)
        v3_outputs[symbol] = v3_result
        if v3_result['latched']:
            st.set_latch(next_row_state, 'V3', f'fund:{symbol}', True, v3_result['reason'])

        # V4 - extreme volatility (B4: session-keyed counter)
        v4_result = rows_vehicle.evaluate_V4(fund_inputs, prior_row_state, authorized_events, symbol, session)
        v4_outputs[symbol] = v4_result
        # Update V4 counter (B4: at most once per session)
        if v4_result['reason'] == 'clearing_period':
            last_increment_session = st.get_prior_state(prior_row_state, 'V4_last_increment_session', {}).get(f'fund:{symbol}')
            clearing_count = st.get_counter(prior_row_state, 'V4', f'fund:{symbol}', 'clearing_sessions', session=session, default=0)
            if last_increment_session != session:
                new_count = clearing_count + 1
                st.set_counter(next_row_state, 'V4', f'fund:{symbol}', 'clearing_sessions', new_count, session=session)
                v4_last_increment[f'fund:{symbol}'] = session
            else:
                st.set_counter(next_row_state, 'V4', f'fund:{symbol}', 'clearing_sessions', clearing_count, session=session)
                v4_last_increment[f'fund:{symbol}'] = last_increment_session
        elif v4_result['reason'] == 'extreme_volatility':
            # Reset counter on trip
            st.set_counter(next_row_state, 'V4', f'fund:{symbol}', 'clearing_sessions', 0, session=session)
            v4_last_increment[f'fund:{symbol}'] = None

        # V5 - decay monitor (B5: 40-session escalation)
        v5_result = rows_vehicle.evaluate_V5(fund_inputs, prior_row_state, authorized_events, symbol, session)
        v5_outputs[symbol] = v5_result
        # Update V5 persistence counter
        new_count = v5_result['outputs']['consecutive_sessions_beyond_tolerance']
        st.set_counter(next_row_state, 'V5', f'fund:{symbol}', 'persistence_sessions', new_count)
        v5_escalated[f'fund:{symbol}'] = v5_result['outputs']['escalated_to_v1']

        # V6 - carrying cost
        v6_result = rows_vehicle.evaluate_V6(fund_inputs, prior_row_state, authorized_events, symbol)
        v6_outputs[symbol] = v6_result

        # V7 - quote/liquidity
        v7_result = rows_vehicle.evaluate_V7(fund_inputs, prior_row_state, authorized_events, symbol)
        v7_outputs[symbol] = v7_result

    # Aggregate vehicle rows into single row outputs
    rows_by_ID['V1'] = aggregate_fund_row(v1_outputs)
    rows_by_ID['V2'] = aggregate_fund_row(v2_outputs)
    rows_by_ID['V3'] = aggregate_fund_row(v3_outputs)
    rows_by_ID['V4'] = aggregate_fund_row(v4_outputs)
    rows_by_ID['V5'] = aggregate_fund_row(v5_outputs)
    rows_by_ID['V6'] = aggregate_fund_row(v6_outputs)
    rows_by_ID['V7'] = aggregate_fund_row(v7_outputs)

    # Store V2 pending state (B1)
    if v2_pending:
        next_row_state['V2_pending'] = v2_pending
    # Store V4 last increment session (B4)
    if v4_last_increment:
        next_row_state['V4_last_increment_session'] = v4_last_increment
    # Store V5 escalated state (B5)
    if v5_escalated:
        next_row_state['V5_escalated'] = v5_escalated

    # ==== OPERATIONS ROWS (O1-O9, J1) ====

    # O1 - required inputs stale/missing (B3)
    o1_result = rows_ops.evaluate_O1(validated_inputs, prior_row_state, authorized_events, session)
    rows_by_ID['O1'] = o1_result
    # Update O1 fresh session counter
    if not o1_result['would_have_tripped']:
        fresh_count = st.get_counter(prior_row_state, 'O1', 'account', 'fresh_sessions', default=0)
        st.set_counter(next_row_state, 'O1', 'account', 'fresh_sessions', fresh_count + 1)
    else:
        st.set_counter(next_row_state, 'O1', 'account', 'fresh_sessions', 0)

    # O2 - session calendar
    o2_result = rows_ops.evaluate_O2(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O2'] = o2_result

    # O3 - reconciliation mismatch
    o3_result = rows_ops.evaluate_O3(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O3'] = o3_result
    if o3_result['latched']:
        st.set_latch(next_row_state, 'O3', 'account', True, o3_result['reason'])

    # O4 - order timeout (B6: keyed to original order ID)
    o4_outputs = {}
    o4_pending = {}
    for symbol in fund_symbols:
        fund_inputs = funds[symbol]
        o4_result = rows_ops.evaluate_O4(fund_inputs, prior_row_state, authorized_events, symbol)
        o4_outputs[symbol] = o4_result
        # Store pending order state (B6)
        if o4_result['reason'] in ['order_timeout', 'order_timeout_carried']:
            pending_order = fund_inputs.get('o4_pending_order')
            if isinstance(pending_order, dict):
                o4_pending[f'symbol:{symbol}'] = {
                    'order_id': pending_order.get('order_id'),
                    'timed_out': True
                }
            elif prior_row_state:
                # Carry forward prior pending
                prior_pending = prior_row_state.get('O4_pending', {}).get(f'symbol:{symbol}')
                if prior_pending:
                    o4_pending[f'symbol:{symbol}'] = prior_pending
    rows_by_ID['O4'] = aggregate_fund_row(o4_outputs, symbol_scoped=True)
    if o4_pending:
        next_row_state['O4_pending'] = o4_pending

    # O5 - pre-trade limits (B2: per-session rejection counter)
    o5_result = rows_ops.evaluate_O5(validated_inputs, prior_row_state, authorized_events, session)
    rows_by_ID['O5'] = o5_result
    if o5_result['latched']:
        st.set_latch(next_row_state, 'O5', 'account', True, o5_result['reason'])
    # Update O5 rejection counter (B2: per-session)
    if o5_result['would_have_tripped'] and not o5_result['latched']:
        rejection_count = st.get_counter(prior_row_state, 'O5', 'account', 'rejections', session=session, default=0)
        st.set_counter(next_row_state, 'O5', 'account', 'rejections', rejection_count + 1, session=session)

    # O6 - policy hash mismatch
    o6_result = rows_ops.evaluate_O6(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O6'] = o6_result
    if o6_result['latched']:
        st.set_latch(next_row_state, 'O6', 'account', True, o6_result['reason'])

    # O7 - dead man's switch
    o7_result = rows_ops.evaluate_O7(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O7'] = o7_result
    if o7_result['latched']:
        st.set_latch(next_row_state, 'O7', 'account', True, o7_result['reason'])

    # O8 - kill switch
    o8_result = rows_ops.evaluate_O8(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O8'] = o8_result

    # O9 - unauthorized parameter change
    o9_result = rows_ops.evaluate_O9(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['O9'] = o9_result
    if o9_result['latched']:
        st.set_latch(next_row_state, 'O9', 'account', True, o9_result['reason'])

    # J1 - joint exposure limit
    j1_result = rows_ops.evaluate_J1(validated_inputs, prior_row_state, authorized_events)
    rows_by_ID['J1'] = j1_result

    # ==== PRECEDENCE RESOLUTION ====
    # Per §4.1: HALT > ORDER-UNKNOWN > DE-RISK > NO-NEW-RISK > NORMAL
    # Account HALT dominates all narrower scopes

    effective_state_by_scope = {}

    # Precedence order
    precedence = ['HALT', 'ORDER-UNKNOWN', 'DE-RISK', 'NO-NEW-RISK', 'NORMAL']

    for scope in scopes:
        # Collect all state contributions for this scope
        states_for_scope = []

        if scope == 'account':
            # Account-scoped rows
            for row_id in ['L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'O1', 'O2', 'O3', 'O5', 'O6', 'O7', 'O8', 'O9']:
                row_result = rows_by_ID[row_id]
                states_for_scope.append(row_result['state'])
        elif scope.startswith('fund:'):
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

    return (rows_by_ID, effective_state_by_scope, next_row_state)


def aggregate_fund_row(fund_outputs: Dict[str, Dict[str, Any]], symbol_scoped: bool = False) -> Dict[str, Any]:
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

    # Get a sample to determine kind
    sample = next(iter(fund_outputs.values()))
    kind = sample['kind']

    # Aggregate: take most restrictive state
    precedence = ['HALT', 'ORDER-UNKNOWN', 'DE-RISK', 'NO-NEW-RISK', 'NORMAL']
    most_restrictive = 'NORMAL'
    any_tripped = False
    any_latched = False
    reasons = []
    affected_funds = []

    for symbol, result in fund_outputs.items():
        state = result['state']
        if precedence.index(state) < precedence.index(most_restrictive):
            most_restrictive = state
        if result['would_have_tripped']:
            any_tripped = True
            affected_funds.append(symbol)
        if result.get('latched'):
            any_latched = True
        if result['reason'] != 'none':
            reasons.append(f"{symbol}:{result['reason']}")

    # Build aggregate output
    aggregate = {
        'state': most_restrictive,
        'would_have_tripped': any_tripped,
        'kind': kind,
        'latched': any_latched,
        'reason': ', '.join(reasons) if reasons else 'none'
    }

    # Include per-fund outputs if present
    if 'outputs' in sample:
        aggregate['outputs'] = {symbol: result.get('outputs', {}) for symbol, result in fund_outputs.items()}

    # For fund/symbol-scoped rows, include affected funds/symbols
    if affected_funds:
        if symbol_scoped:
            aggregate['symbols'] = affected_funds
        else:
            aggregate['funds'] = affected_funds

    return aggregate
