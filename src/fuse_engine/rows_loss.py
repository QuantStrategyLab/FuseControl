"""Loss breaker rows L0-L6 per BRIEF-FUSE-1 §4.3 Table A.

All loss rows operate on bankroll basis, flow-adjusted and split-adjusted.
Thresholds are fractions of D (tier loss budget).
"""

from typing import Any, Dict, Optional
from . import state as st
from . import canonical_state as cst


# Tier loss budgets (D) per spec §4.3 and spec.json
TIER_D = {
    'conservative': 0.15,
    'balanced': 0.30,
    'aggressive': 0.50
}


def evaluate_L0(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """L0: Exposure limited to maximum-loss cap (standing limit).

    Kind: limit (symmetric, automatic)
    Scope: account
    State contribution: none (outputs only)
    Required inputs: joint_exposure, max_loss_cap, proposed_exposure
    """
    # Required inputs - fail closed if missing/invalid
    joint_exposure = inputs.get('joint_exposure')
    max_loss_cap = inputs.get('max_loss_cap')
    proposed_exposure = inputs.get('proposed_exposure')

    # Fail closed on missing/invalid inputs (§4.4 rule 3, §5.2)
    if joint_exposure is None or max_loss_cap is None or proposed_exposure is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'limit',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'cap': None,
                'cap_breached': True,
                'increases_blocked': True
            }
        }

    # Type validation
    try:
        joint_exposure = float(joint_exposure)
        max_loss_cap = float(max_loss_cap)
        proposed_exposure = float(proposed_exposure)
    except (TypeError, ValueError):
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'limit',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'cap': None,
                'cap_breached': True,
                'increases_blocked': True
            }
        }

    # Check for invalid values
    import math
    if (math.isnan(joint_exposure) or math.isnan(max_loss_cap) or math.isnan(proposed_exposure) or
        math.isinf(joint_exposure) or math.isinf(max_loss_cap) or math.isinf(proposed_exposure) or
        joint_exposure < 0 or max_loss_cap < 0 or proposed_exposure < 0):
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'limit',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'cap': None,
                'cap_breached': True,
                'increases_blocked': True
            }
        }

    # Evaluate limit
    cap_breached = joint_exposure > max_loss_cap
    increases_blocked = proposed_exposure > max_loss_cap

    # Fix 4: tier_change re-based evaluation - report limits but don't trip
    # O9 handles enforcement of unauthorized tier changes
    tier_change_event = inputs.get('tier_change_event')
    if tier_change_event:
        # Re-based: report new tier limits in outputs but don't trip
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'limit',
            'latched': False,
            'reason': 'none',
            'outputs': {
                'cap': max_loss_cap,
                'cap_breached': cap_breached,
                'increases_blocked': increases_blocked
            }
        }

    return {
        'state': 'NORMAL',
        'would_have_tripped': cap_breached or increases_blocked,
        'kind': 'limit',
        'latched': False,
        'reason': 'breached' if (cap_breached or increases_blocked) else 'none',
        'outputs': {
            'cap': max_loss_cap,
            'cap_breached': cap_breached,
            'increases_blocked': increases_blocked
        }
    }


def evaluate_L1(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """L1: Drawdown reaches D/3 → notify and lock against loosening.

    Kind: interlock
    Scope: account
    State contribution: none (but locks tier/H/HWM)
    Clearing: Clears when drawdown is back under D/3
    """
    bankroll = inputs.get('bankroll')
    high_water_mark = inputs.get('high_water_mark')
    tier = inputs.get('tier')

    # Fail closed on missing inputs
    if bankroll is None or high_water_mark is None or tier is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'locked_against_loosening': True,
                'notify': True
            }
        }

    try:
        bankroll = float(bankroll)
        high_water_mark = float(high_water_mark)
    except (TypeError, ValueError):
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'locked_against_loosening': True,
                'notify': True
            }
        }

    # Get tier D and threshold
    D = TIER_D.get(tier)
    if D is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'missing_input',
            'outputs': {
                'locked_against_loosening': True,
                'notify': True
            }
        }

    threshold = D / 3.0

    # Calculate drawdown
    drawdown = (high_water_mark - bankroll) / high_water_mark if high_water_mark > 0 else 0.0

    # Check trigger
    triggered = drawdown >= threshold

    return {
        'state': 'NORMAL',
        'would_have_tripped': triggered,
        'kind': 'interlock',
        'latched': False,
        'reason': 'drawdown_threshold' if triggered else 'none',
        'outputs': {
            'locked_against_loosening': triggered,
            'notify': triggered
        }
    }


def evaluate_L2(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """L2: Drawdown reaches 2D/3 → NO-NEW-RISK.

    Kind: breaker
    Scope: account
    State contribution: NO-NEW-RISK
    Clearing: Owner re-arms via authorized_events (canonical format per Q6)
    """
    # Check for prior latch from canonical format (SUC-12)
    prior_latch = cst.get_l2_latch(prior_state)
    if prior_latch:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            # Handle both list and dict formats
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'L2' or event.get('row_id') == 'L2'):
                    rearm = True
                    break

        if rearm:
            # Q4 short-circuit: re-arm wins, return authorized_rearm WITHOUT re-evaluating
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'breaker',
                'latched': False,
                'reason': 'authorized_rearm'
            }

        # Stay latched without re-arm
        # Stay latched - check for specific latched conditions
        flow_event = inputs.get('flow_event')
        tier_change_event = inputs.get('tier_change_event')

        # Determine specific latched reason (SUC-12)
        if flow_event and flow_event.get('type') == 'deposit':
            reason = 'latched_survives_deposit'
        elif tier_change_event:
            reason = 'latched_survives_tier_change'
        else:
            reason = 'latched_prior_trip'

        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': reason
        }

    # Evaluate trigger
    bankroll = inputs.get('bankroll')
    high_water_mark = inputs.get('high_water_mark')
    tier = inputs.get('tier')

    # Fail closed on missing inputs
    if bankroll is None or high_water_mark is None or tier is None:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    try:
        bankroll = float(bankroll)
        high_water_mark = float(high_water_mark)
    except (TypeError, ValueError):
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    # Get tier D and threshold
    D = TIER_D.get(tier)
    if D is None:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    threshold = 2.0 * D / 3.0

    # Calculate drawdown
    drawdown = (high_water_mark - bankroll) / high_water_mark if high_water_mark > 0 else 0.0

    # Check trigger (inclusive per spec: "reaches 2D/3 (inclusive)")
    triggered = drawdown >= threshold

    if not triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none'
        }

    # Trip and latch (SUC-12 step 1: specific reason)
    return {
        'state': 'NO-NEW-RISK',
        'would_have_tripped': True,
        'kind': 'breaker',
        'latched': True,
        'reason': 'drawdown_at_2D_over_3'
    }


def evaluate_L3(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """L3: Drawdown reaches D → DE-RISK to zero, then locked flat.

    Kind: breaker
    Scope: account
    State contribution: DE-RISK
    Clearing: Owner card with 30-day cooling-off; loss record not cleared
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'L3', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        cooling_off_days_remaining = prior_latch['details'].get('cooling_off_days_remaining', 30)

        if authorized_events:
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and event.get('row_id') == 'L3':
                    rearm = True
                    # Check if cooling-off period satisfied
                    days_elapsed = event.get('days_since_trip', 0)
                    if days_elapsed >= 30:
                        cooling_off_days_remaining = 0
                    else:
                        cooling_off_days_remaining = 30 - days_elapsed
                    break

        if not rearm or cooling_off_days_remaining > 0:
            # Stay latched
            return {
                'state': 'DE-RISK',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip',
                'outputs': {
                    'cooling_off_days_remaining': cooling_off_days_remaining,
                    'locked_flat': True,
                    'loss_record_cleared': False
                }
            }

    # Evaluate trigger
    bankroll = inputs.get('bankroll')
    high_water_mark = inputs.get('high_water_mark')
    tier = inputs.get('tier')

    # Fail closed on missing inputs
    if bankroll is None or high_water_mark is None or tier is None:
        return {
            'state': 'DE-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input',
            'outputs': {
                'cooling_off_days_remaining': 30,
                'locked_flat': True,
                'loss_record_cleared': False
            }
        }

    try:
        bankroll = float(bankroll)
        high_water_mark = float(high_water_mark)
    except (TypeError, ValueError):
        return {
            'state': 'DE-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input',
            'outputs': {
                'cooling_off_days_remaining': 30,
                'locked_flat': True,
                'loss_record_cleared': False
            }
        }

    # Get tier D
    D = TIER_D.get(tier)
    if D is None:
        return {
            'state': 'DE-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input',
            'outputs': {
                'cooling_off_days_remaining': 30,
                'locked_flat': True,
                'loss_record_cleared': False
            }
        }

    # Calculate drawdown
    drawdown = (high_water_mark - bankroll) / high_water_mark if high_water_mark > 0 else 0.0

    # Check trigger
    triggered = drawdown >= D

    if not triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none',
            'outputs': {
                'cooling_off_days_remaining': 0,
                'locked_flat': False,
                'loss_record_cleared': False
            }
        }

    # Trip and latch
    return {
        'state': 'DE-RISK',
        'would_have_tripped': True,
        'kind': 'breaker',
        'latched': True,
        'reason': 'drawdown_threshold',
        'outputs': {
            'cooling_off_days_remaining': 30,
            'locked_flat': True,
            'loss_record_cleared': False
        }
    }


def evaluate_L4(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """L4: One-session loss reaches D/10 → NO-NEW-RISK.

    Kind: breaker
    Scope: account
    State contribution: NO-NEW-RISK
    Clearing: Owner acknowledges, not before next session
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'L4', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'L4' or event.get('row_id') == 'L4'):
                    # Must be next session or later
                    if event.get('sessions_since_trip', 0) >= 1:
                        rearm = True
                    break

        if not rearm:
            # Stay latched
            return {
                'state': 'NO-NEW-RISK',
                'would_have_tripped': True,
                'kind': 'breaker',
                'latched': True,
                'reason': 'latched_prior_trip'
            }

    # Evaluate trigger
    one_session_loss = inputs.get('one_session_loss')
    tier = inputs.get('tier')

    # Fail closed on missing inputs
    if one_session_loss is None or tier is None:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    try:
        one_session_loss = float(one_session_loss)
    except (TypeError, ValueError):
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    # Get tier D and threshold
    D = TIER_D.get(tier)
    if D is None:
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'breaker',
            'latched': True,
            'reason': 'missing_input'
        }

    threshold = D / 10.0

    # Check trigger
    triggered = one_session_loss >= threshold

    if not triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none'
        }

    # Trip and latch
    return {
        'state': 'NO-NEW-RISK',
        'would_have_tripped': True,
        'kind': 'breaker',
        'latched': True,
        'reason': 'one_session_loss_threshold'
    }


def evaluate_L5(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]], session: str) -> Dict[str, Any]:
    """L5: Market-wide trading halt Level 1 or 2 → NO-NEW-RISK for rest of session.

    Kind: interlock
    Scope: account
    State contribution: NO-NEW-RISK
    Clearing: Clears after one clean session
    """
    # Check for prior active state
    fresh_session_count = st.get_counter(prior_state, 'L5', 'account', 'fresh_sessions', default=0)
    prior_latch = st.get_latch(prior_state, 'L5', 'account')

    if prior_latch and prior_latch['latched']:
        # Interlock clearing: one clean session needed
        if fresh_session_count >= 1:
            # Clear
            return {
                'state': 'NORMAL',
                'would_have_tripped': False,
                'kind': 'interlock',
                'latched': False,
                'reason': 'none'
            }
        # Still active
        return {
            'state': 'NO-NEW-RISK',
            'would_have_tripped': True,
            'kind': 'interlock',
            'latched': False,
            'reason': 'clearing_period'
        }

    # Evaluate trigger
    market_halt_level = inputs.get('market_halt_level')

    # null market_halt_level = no halt (benign)
    if market_halt_level is None:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'interlock',
            'latched': False,
            'reason': 'none'
        }

    # Check trigger (Level 1 or 2)
    triggered = market_halt_level in [1, 2]

    if not triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'interlock',
            'latched': False,
            'reason': 'none'
        }

    # Trip
    return {
        'state': 'NO-NEW-RISK',
        'would_have_tripped': True,
        'kind': 'interlock',
        'latched': False,
        'reason': 'market_halt_level_1_or_2'
    }


def evaluate_L6(inputs: Dict[str, Any], prior_state: Optional[Dict[str, Any]],
                authorized_events: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """L6: Market-wide Level 3 halt OR one-session fall ≥10% in either index → HALT.

    Kind: breaker
    Scope: account
    State contribution: HALT
    Clearing: Owner re-arms after reconciliation
    """
    # Check for prior latch
    prior_latch = st.get_latch(prior_state, 'L6', 'account')
    if prior_latch and prior_latch['latched']:
        # Check for authorized re-arm
        rearm = False
        if authorized_events:
            events_list = authorized_events if isinstance(authorized_events, list) else authorized_events.get('account', [])
            for event in events_list:
                if event.get('type') == 'rearm' and (event.get('row') == 'L6' or event.get('row_id') == 'L6'):
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
    market_halt_level = inputs.get('market_halt_level')
    index_returns = inputs.get('index_one_session_returns')

    # Event-trigger rows don't fail closed on missing inputs (Fix 4):
    # They require affirmative trigger evidence; O1 carries the data-integrity trip
    # null market_halt_level = no halt (benign)
    # null index_returns = no index data, thus no affirmative evidence of 10% fall (benign)

    # Check Level 3 halt (null = no halt, benign)
    level_3_halt = market_halt_level == 3 if market_halt_level is not None else False

    # Check 10% fall in either index (only if index_returns present)
    index_fall = False
    if index_returns is not None:
        try:
            for index, ret in index_returns.items():
                if ret is not None and float(ret) <= -0.10:
                    index_fall = True
                    break
        except (TypeError, ValueError):
            # Malformed data - treat as no affirmative evidence
            index_fall = False

    triggered = level_3_halt or index_fall

    if not triggered:
        return {
            'state': 'NORMAL',
            'would_have_tripped': False,
            'kind': 'breaker',
            'latched': False,
            'reason': 'none'
        }

    # Trip and latch
    reason = 'level_3_halt' if level_3_halt else 'index_fall_10pct'
    return {
        'state': 'HALT',
        'would_have_tripped': True,
        'kind': 'breaker',
        'latched': True,
        'reason': reason
    }
