"""Canonical state management per Q6 adjudication ruling.

All state reads and writes use the golden nested row objects directly.
Retired private aliases: V2_pending, V4_counter, V4_last_increment_session,
V5_counter, V5_escalated, O4_pending, O5_counter, O5_last_rejection_session,
{row}_counter, {row}_latch.

Canonical state keys:
- V2.pending_adjustments[fund], V2.latched_mismatches[fund]
- V4[fund].clearing_counter, V4[fund].last_session_below_threshold
- V5[fund].consecutive_beyond_tolerance, V5[fund].escalated
- O5.rejection_count, O5.last_rejection_session, O5.latched
- O4[symbol].original_order_id, O4[symbol].status
- L2.latched, L2.trip_session
- V1[fund].latched, V1[fund].trip_session, V1[fund].deviation
- O1.fresh_session_count, O1.last_session
- L3.latched, L3.trip_session, L3.cooling_off_until, L3.loss_record
- L5.fresh_session_count
"""

from typing import Any, Dict, Optional


# V2 canonical state accessors

def get_v2_pending_adjustment(prior_state: Optional[Dict], fund: str) -> Optional[Dict]:
    """Get pending adjustment for a fund from V2.pending_adjustments."""
    if not prior_state or 'V2' not in prior_state:
        return None
    pending = prior_state['V2'].get('pending_adjustments', {})
    return pending.get(fund)


def set_v2_pending_adjustment(next_state: Dict, fund: str, adjustment: Dict) -> None:
    """Set pending adjustment in V2.pending_adjustments[fund]."""
    if 'V2' not in next_state:
        next_state['V2'] = {}
    if 'pending_adjustments' not in next_state['V2']:
        next_state['V2']['pending_adjustments'] = {}
    next_state['V2']['pending_adjustments'][fund] = adjustment


def clear_v2_pending_adjustment(next_state: Dict, fund: str) -> None:
    """Clear pending adjustment for a fund.

    Per golden target-state projections, V2 is serialized as {} when empty, not absent.
    """
    if 'V2' not in next_state:
        next_state['V2'] = {}
    if 'pending_adjustments' in next_state['V2'] and fund in next_state['V2']['pending_adjustments']:
        del next_state['V2']['pending_adjustments'][fund]
        if not next_state['V2']['pending_adjustments']:
            del next_state['V2']['pending_adjustments']
    # Keep empty V2:{} per golden projections


def get_v2_latched_mismatch(prior_state: Optional[Dict], fund: str) -> Optional[Dict]:
    """Get latched mismatch for a fund from V2.latched_mismatches."""
    if not prior_state or 'V2' not in prior_state:
        return None
    mismatches = prior_state['V2'].get('latched_mismatches', {})
    return mismatches.get(fund)


def set_v2_latched_mismatch(next_state: Dict, fund: str, mismatch: Dict) -> None:
    """Set latched mismatch in V2.latched_mismatches[fund]."""
    if 'V2' not in next_state:
        next_state['V2'] = {}
    if 'latched_mismatches' not in next_state['V2']:
        next_state['V2']['latched_mismatches'] = {}
    next_state['V2']['latched_mismatches'][fund] = mismatch


def clear_v2_latched_mismatch(next_state: Dict, fund: str) -> None:
    """Clear latched mismatch for a fund.

    Per golden target-state projections, V2 is serialized as {} when empty, not absent.
    """
    if 'V2' not in next_state:
        next_state['V2'] = {}
    if 'latched_mismatches' in next_state['V2'] and fund in next_state['V2']['latched_mismatches']:
        del next_state['V2']['latched_mismatches'][fund]
        if not next_state['V2']['latched_mismatches']:
            del next_state['V2']['latched_mismatches']
    # Keep empty V2:{} per golden projections


# V4 canonical state accessors

def get_v4_state(prior_state: Optional[Dict], fund: str) -> Dict:
    """Get V4 state for a fund. Returns dict with clearing_counter and last_session_below_threshold.

    Present entry with counter=0 means active after trip (distinct from absent=inactive).
    """
    if not prior_state or 'V4' not in prior_state:
        return {'clearing_counter': None, 'last_session_below_threshold': None}

    fund_state = prior_state['V4'].get(fund, {})
    return {
        'clearing_counter': fund_state.get('clearing_counter'),
        'last_session_below_threshold': fund_state.get('last_session_below_threshold')
    }


def set_v4_state(next_state: Dict, fund: str, counter: int, last_session: Optional[str]) -> None:
    """Set V4 state for a fund. Counter and last_session together.

    At count 10, caller should remove the fund entry instead of storing count 10.
    """
    if 'V4' not in next_state:
        next_state['V4'] = {}
    next_state['V4'][fund] = {
        'clearing_counter': counter,
        'last_session_below_threshold': last_session
    }


def clear_v4_state(next_state: Dict, fund: str) -> None:
    """Remove V4 fund entry (after clearing at count 10)."""
    if 'V4' in next_state and fund in next_state['V4']:
        del next_state['V4'][fund]
        if not next_state['V4']:
            del next_state['V4']


# V5 canonical state accessors

def get_v5_state(prior_state: Optional[Dict], fund: str) -> Dict:
    """Get V5 state for a fund. Returns dict with counter, escalated flag, and last_session."""
    if not prior_state or 'V5' not in prior_state:
        return {'consecutive_beyond_tolerance': 0, 'escalated': False, 'last_session': None}

    fund_state = prior_state['V5'].get(fund, {})
    return {
        'consecutive_beyond_tolerance': fund_state.get('consecutive_beyond_tolerance', 0),
        'escalated': fund_state.get('escalated', False),
        'last_session': fund_state.get('last_session')
    }


def set_v5_state(next_state: Dict, fund: str, count: int, escalated: bool, session: str) -> None:
    """Set V5 state for a fund.

    Q6 requires sufficient session identity for replay and duplicate evaluations.
    """
    if 'V5' not in next_state:
        next_state['V5'] = {}
    next_state['V5'][fund] = {
        'consecutive_beyond_tolerance': count,
        'escalated': escalated,
        'last_session': session
    }


# O5 canonical state accessors

def get_o5_state(prior_state: Optional[Dict]) -> Dict:
    """Get O5 account-level state. Returns dict with rejection_count, last_session, latched."""
    if not prior_state or 'O5' not in prior_state:
        return {'rejection_count': 0, 'last_rejection_session': None, 'latched': False}

    o5 = prior_state['O5']
    return {
        'rejection_count': o5.get('rejection_count', 0),
        'last_rejection_session': o5.get('last_rejection_session'),
        'latched': o5.get('latched', False)
    }


def set_o5_state(next_state: Dict, count: int, last_session: Optional[str], latched: bool) -> None:
    """Set O5 account-level state."""
    next_state['O5'] = {
        'rejection_count': count,
        'last_rejection_session': last_session,
        'latched': latched
    }


# O4 canonical state accessors

def get_o4_pending_order(prior_state: Optional[Dict], symbol: str) -> Optional[Dict]:
    """Get O4 pending order state for a symbol. Returns dict with original_order_id and status."""
    if not prior_state or 'O4' not in prior_state:
        return None

    symbol_state = prior_state['O4'].get(symbol, {})
    if 'original_order_id' not in symbol_state:
        return None

    return {
        'original_order_id': symbol_state['original_order_id'],
        'status': symbol_state.get('status', 'unknown')
    }


def set_o4_pending_order(next_state: Dict, symbol: str, order_id: str, status: str = 'unknown') -> None:
    """Set O4 pending order state for a symbol."""
    if 'O4' not in next_state:
        next_state['O4'] = {}
    next_state['O4'][symbol] = {
        'original_order_id': order_id,
        'status': status
    }


def clear_o4_pending_order(next_state: Dict, symbol: str) -> None:
    """Clear O4 pending order for a symbol (after resolution)."""
    if 'O4' in next_state and symbol in next_state['O4']:
        del next_state['O4'][symbol]
        if not next_state['O4']:
            del next_state['O4']


# L2 canonical state accessors

def get_l2_latch(prior_state: Optional[Dict]) -> Optional[Dict]:
    """Get L2 latch state. Returns dict with latched and trip_session."""
    if not prior_state or 'L2' not in prior_state:
        return None

    l2 = prior_state['L2']
    if not l2.get('latched'):
        return None

    return {
        'latched': True,
        'trip_session': l2.get('trip_session')
    }


def set_l2_latch(next_state: Dict, trip_session: str) -> None:
    """Set L2 latch state."""
    next_state['L2'] = {
        'latched': True,
        'trip_session': trip_session
    }


def clear_l2_latch(next_state: Dict) -> None:
    """Clear L2 latch state (Q4 authorized re-arm)."""
    next_state['L2'] = {}


# V1 canonical state accessors

def get_v1_latch(prior_state: Optional[Dict], fund: str) -> Optional[Dict]:
    """Get V1 latch state for a fund. Returns dict with latched, trip_session, deviation."""
    if not prior_state or 'V1' not in prior_state:
        return None

    fund_state = prior_state['V1'].get(fund, {})
    if not fund_state.get('latched'):
        return None

    return {
        'latched': True,
        'trip_session': fund_state.get('trip_session'),
        'deviation': fund_state.get('deviation')
    }


def set_v1_latch(next_state: Dict, fund: str, trip_session: str, deviation: float) -> None:
    """Set V1 latch state for a fund."""
    if 'V1' not in next_state:
        next_state['V1'] = {}
    next_state['V1'][fund] = {
        'latched': True,
        'trip_session': trip_session,
        'deviation': deviation
    }


def clear_v1_latch(next_state: Dict, fund: str) -> None:
    """Clear V1 latch state for a fund (Q4 authorized re-arm).

    Serializes as {"V1":{}} for one-target case per Q4 requirement.
    """
    if 'V1' not in next_state:
        next_state['V1'] = {}
    if fund in next_state['V1']:
        del next_state['V1'][fund]
    # Keep empty V1:{} for target-state projection


# O1 canonical state accessors

def get_o1_fresh_state(prior_state: Optional[Dict]) -> Dict:
    """Get O1 fresh-session state."""
    if not prior_state or 'O1' not in prior_state:
        return {'fresh_session_count': 0, 'last_session': None}

    o1 = prior_state['O1']
    return {
        'fresh_session_count': o1.get('fresh_session_count', 0),
        'last_session': o1.get('last_session')
    }


def set_o1_fresh_state(next_state: Dict, count: int, session: str) -> None:
    """Set O1 fresh-session state."""
    next_state['O1'] = {
        'fresh_session_count': count,
        'last_session': session
    }


# L3 canonical state accessors

def get_l3_latch(prior_state: Optional[Dict]) -> Optional[Dict]:
    """Get L3 latch and loss record."""
    if not prior_state or 'L3' not in prior_state:
        return None

    l3 = prior_state['L3']
    if not l3.get('latched'):
        return None

    return {
        'latched': True,
        'trip_session': l3.get('trip_session'),
        'cooling_off_until': l3.get('cooling_off_until'),
        'loss_record': l3.get('loss_record')
    }


def set_l3_latch(next_state: Dict, trip_session: str, cooling_off_until: str, loss_record: Dict) -> None:
    """Set L3 latch with cooling-off period and durable loss record."""
    next_state['L3'] = {
        'latched': True,
        'trip_session': trip_session,
        'cooling_off_until': cooling_off_until,
        'loss_record': loss_record
    }


def clear_l3_lock(next_state: Dict, loss_record: Dict) -> None:
    """Clear L3 active lock after cooling-off, preserve loss record."""
    next_state['L3'] = {
        'latched': False,
        'loss_record': loss_record
    }


# L5 canonical state accessors

def get_l5_fresh_count(prior_state: Optional[Dict]) -> int:
    """Get L5 fresh-session counter."""
    if not prior_state or 'L5' not in prior_state:
        return 0
    return prior_state['L5'].get('fresh_session_count', 0)


def set_l5_fresh_count(next_state: Dict, count: int) -> None:
    """Set L5 fresh-session counter."""
    if 'L5' not in next_state:
        next_state['L5'] = {}
    next_state['L5']['fresh_session_count'] = count


# General latch accessors for rows using old state.py pattern (L4, L6, V3)
# These can read from either old {row}_latch format or canonical format

def get_account_latch(prior_state: Optional[Dict], row_id: str) -> Optional[Dict]:
    """Get account-level latch for a row (L3/L4/L6).

    Reads from canonical {row}.latched format or falls back to old {row}_latch.
    """
    if not prior_state:
        return None

    # Try canonical format first
    if row_id in prior_state:
        row_state = prior_state[row_id]
        if row_state.get('latched'):
            return {
                'latched': True,
                'trip_session': row_state.get('trip_session'),
                'details': row_state.get('details', {})
            }

    # Fall back to old format for compatibility during migration
    old_key = f'{row_id}_latch'
    if old_key in prior_state:
        latch = prior_state[old_key].get('account')
        if latch and latch.get('latched'):
            return latch

    return None


def set_account_latch(next_state: Dict, row_id: str, trip_session: str, details: Dict = None) -> None:
    """Set account-level latch in canonical format."""
    next_state[row_id] = {
        'latched': True,
        'trip_session': trip_session,
        'details': details or {}
    }


def get_fund_latch(prior_state: Optional[Dict], row_id: str, fund: str) -> Optional[Dict]:
    """Get fund-level latch for a row (V3).

    Reads from canonical {row}.{fund}.latched format or falls back to old {row}_latch.
    """
    if not prior_state:
        return None

    # Try canonical format first
    if row_id in prior_state:
        row_state = prior_state[row_id]
        fund_state = row_state.get(fund, {})
        if fund_state.get('latched'):
            return {
                'latched': True,
                'trip_session': fund_state.get('trip_session'),
                'details': fund_state.get('details', {})
            }

    # Fall back to old format
    old_key = f'{row_id}_latch'
    if old_key in prior_state:
        scope = f'fund:{fund}'
        latch = prior_state[old_key].get(scope)
        if latch and latch.get('latched'):
            return latch

    return None


def set_fund_latch(next_state: Dict, row_id: str, fund: str, trip_session: str, details: Dict = None) -> None:
    """Set fund-level latch in canonical format."""
    if row_id not in next_state:
        next_state[row_id] = {}
    next_state[row_id][fund] = {
        'latched': True,
        'trip_session': trip_session,
        'details': details or {}
    }
