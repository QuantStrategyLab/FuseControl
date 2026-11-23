"""Synthetic stub adapter implementing §5.1 evaluate(...) signature.

Returns correctly-shaped rows with synthetic-only values. Consumers can swap
this stub for the FUSE-1 engine with no harness change (§5.3 stub interchangeability).
"""

from typing import Any, Dict, Optional


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
    """Synthetic stub evaluator with §5.1 signature.

    Returns:
        (rows_by_ID, effective_state_by_scope, next_row_state) tuple with
        correctly-shaped outputs. All values are synthetic-only.
    """
    if prior_row_state is None:
        prior_row_state = {}
    if authorized_events is None:
        authorized_events = {}

    # Get funds from inputs to build scopes
    funds = validated_inputs.get('funds', {})
    fund_symbols = list(funds.keys()) if funds else ['TQQQ', 'SOXL']

    # Build scopes: account, fund:SYMBOL, symbol:SYMBOL, joint
    scopes = ['account']
    for symbol in fund_symbols:
        scopes.append(f'fund:{symbol}')
    for symbol in fund_symbols:
        scopes.append(f'symbol:{symbol}')
    scopes.append('joint')

    # Build rows_by_ID with synthetic outputs
    rows_by_ID = {}

    # Loss rows (L0-L6) - account scope
    rows_by_ID['L0'] = {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'limit',
        'latched': False,
        'reason': 'none',
        'outputs': {
            'cap': 50000.0,
            'cap_breached': False,
            'increases_blocked': False
        }
    }

    rows_by_ID['L1'] = {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock',
        'latched': False,
        'reason': 'none',
        'outputs': {
            'locked_against_loosening': False,
            'notify': False
        }
    }

    for row_id in ['L2', 'L3', 'L4', 'L5', 'L6']:
        kind = 'breaker' if row_id in ['L2', 'L3', 'L4', 'L6'] else 'interlock'
        row_data = {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': kind,
            'latched': False,
            'reason': 'none'
        }
        # L3 has specific outputs
        if row_id == 'L3':
            row_data['outputs'] = {
                'cooling_off_days_remaining': 0,
                'locked_flat': False,
                'loss_record_cleared': False
            }
        rows_by_ID[row_id] = row_data

    # Vehicle rows (V1-V7) - fund/symbol scope
    # Note: V4 aggregate has no 'outputs' field (per-fund only)
    for row_id in ['V1', 'V2', 'V3', 'V4']:
        kind = {
            'V1': 'breaker',
            'V2': 'interlock_or_breaker',
            'V3': 'breaker',
            'V4': 'interlock'
        }[row_id]

        rows_by_ID[row_id] = {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': kind,
            'latched': False,
            'reason': 'none'
        }

    # V5 - diagnostic with structured outputs (unresolved case per test inputs)
    rows_by_ID['V5'] = {
        'state': 'NORMAL',
        'would_have_tripped': True,
        'kind': 'diagnostic',
        'latched': False,
        'reason': 'unresolved_fail_closed',
        'outputs': {
            'excess_shortfall': None,
            'consecutive_sessions_beyond_tolerance': 0,
            'escalated_to_v1': False,
            'disposition': 'UNRESOLVED-FAIL-CLOSED'
        }
    }

    # V6 - diagnostic with structured outputs (missing inputs case)
    rows_by_ID['V6'] = {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'diagnostic',
        'latched': False,
        'reason': 'none',
        'outputs': {
            'cost_per_unit_exposure': None,
            'threshold': None,
            'exceeded': False,
            'notify': False
        }
    }

    # V7 - symbol-scoped interlock (unresolved spread width trips with symbols list)
    rows_by_ID['V7'] = {
        'state': 'NORMAL',
        'would_have_tripped': True,
        'kind': 'interlock',
        'latched': False,
        'reason': 'unresolved_fail_closed',
        'symbols': fund_symbols  # Include symbols when tripped
    }

    # Operations rows (O1-O9) - account scope
    for row_id in ['O1', 'O2', 'O3', 'O5', 'O6', 'O7', 'O8', 'O9']:
        kind = {
            'O1': 'interlock',
            'O2': 'interlock',
            'O3': 'breaker',
            'O5': 'breaker',
            'O6': 'breaker',
            'O7': 'breaker',
            'O8': 'owner',
            'O9': 'breaker'
        }[row_id]

        rows_by_ID[row_id] = {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': kind,
            'latched': False,
            'reason': 'none'
        }

    # O4 - symbol scope
    rows_by_ID['O4'] = {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'interlock_or_breaker',
        'latched': False,
        'reason': 'none'
    }

    # J1 - joint scope limit
    rows_by_ID['J1'] = {
        'state': 'NORMAL',
        'would_have_tripped': False,
        'kind': 'limit',
        'latched': False,
        'reason': 'none',
        'outputs': {
            'headroom': 15000.0,
            'cap': 50000.0,
            'above_cap': False,
            'above_trim_threshold': False
        }
    }

    # Build effective_state_by_scope (all NORMAL in stub)
    effective_state_by_scope = {scope: 'NORMAL' for scope in scopes}

    # Build next_row_state (empty in stub - no latches or counters)
    next_row_state = {}

    return (rows_by_ID, effective_state_by_scope, next_row_state)
