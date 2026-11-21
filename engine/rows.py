"""Row evaluators for FUSE-1 control table.

Loss rows L0-L6 implement full pure-Decimal trigger, latching, and state logic;
V, O, and J1 rows remain Phase C skeletons.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

ROW_IDS: tuple[str, ...] = (
    "L0",
    "L1",
    "L2",
    "L3",
    "L4",
    "L5",
    "L6",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "O1",
    "O2",
    "O3",
    "O4",
    "O5",
    "O6",
    "O7",
    "O8",
    "O9",
    "J1",
)

DEFAULT_FUNDS: tuple[str, ...] = ("TQQQ", "SOXL")

TIER_D_FRACTIONS: dict[str, Decimal] = {
    "conservative": Decimal("0.15"),
    "balanced": Decimal("0.30"),
    "aggressive": Decimal("0.50"),
}

L3_COOLING_OFF_DAYS = 30
L5_CLEAN_SESSIONS_REQUIRED = 1
L6_INDEX_FALL_THRESHOLD = Decimal("0.10")

REARM_TOKENS: frozenset[str] = frozenset(
    {"re_arm", "rearm", "owner_re_arm", "owner_rearm", "clear_breaker"}
)
L3_CLEAR_TOKENS: frozenset[str] = REARM_TOKENS | frozenset({"owner_card"})
L4_ACK_TOKENS: frozenset[str] = REARM_TOKENS | frozenset(
    {"owner_ack", "ack", "acknowledge", "owner_acknowledge"}
)


def _to_decimal(value: Any) -> Decimal | None:
    """Convert value to a finite Decimal, rejecting None, bool, and non-finite values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        raw = value.strip() if isinstance(value, str) else str(value)
        dec = Decimal(raw)
    except InvalidOperation:
        return None
    return dec if dec.is_finite() else None


def _tier_budget(
    validated_inputs: dict[str, Any] | None,
) -> tuple[str | None, Decimal | None, Decimal | None]:
    """Return (tier, D_fraction, D_amount), with D_amount=None if tier or bankroll invalid."""
    inputs = validated_inputs or {}
    raw_tier = inputs.get("tier")
    tier = raw_tier if isinstance(raw_tier, str) else None
    d_frac = TIER_D_FRACTIONS.get(tier) if tier is not None else None
    bankroll = _to_decimal(inputs.get("bankroll"))
    if d_frac is None or bankroll is None or bankroll <= 0:
        return tier, d_frac, None
    return tier, d_frac, bankroll * d_frac


def _prior_entry(
    prior_row_state: dict[str, Any] | None,
    row_id: str,
) -> dict[str, Any]:
    """Return the prior state dict for row_id, or an empty dict if absent."""
    if not isinstance(prior_row_state, dict):
        return {}
    entry = prior_row_state.get(row_id)
    return entry if isinstance(entry, dict) else {}


def _parse_iso_date(value: Any) -> date | None:
    """Parse an ISO YYYY-MM-DD date or timestamp prefix, returning None if invalid."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _norm_token(value: Any) -> str:
    """Normalize an event action or event_type token for matching."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _event_targets_row(event: dict[str, Any], row_id: str) -> bool:
    """Return True if an authorized event targets row_id."""
    for key in ("row_id", "row", "target_row"):
        if event.get(key) == row_id:
            return True
    for list_key in ("rows", "row_ids"):
        seq = event.get(list_key)
        if isinstance(seq, (list, tuple, set)) and row_id in seq:
            return True
    return False


def _has_authorized_event(
    authorized_events: list[Any] | None,
    row_id: str,
    allowed_tokens: frozenset[str],
    *,
    require_reconciled: bool = False,
) -> bool:
    """Return True if authorized_events contains an authorizing event for row_id."""
    if not authorized_events:
        return False
    for event in authorized_events:
        if not isinstance(event, dict):
            continue
        if not _event_targets_row(event, row_id):
            continue
        if require_reconciled and event.get("reconciled") is False:
            continue
        ev_type = _norm_token(event.get("event_type"))
        ev_action = _norm_token(event.get("action"))
        if ev_type in allowed_tokens or ev_action in allowed_tokens:
            return True
    return False


def _benign_cell(scope: str, kind: str) -> dict[str, Any]:
    """Return the standard benign skeleton cell for a row."""
    return {
        "scope": scope,
        "state": "NORMAL",
        "would_have_tripped": False,
        "kind": kind,
        "latched": False,
        "reason_class": "none",
        "reason": "skeleton",
    }


def _benign_sub_entry() -> dict[str, Any]:
    """Return a benign per-fund or per-symbol sub-entry."""
    return {
        "state": "NORMAL",
        "would_have_tripped": False,
        "latched": False,
        "reason_class": "none",
        "reason": "skeleton",
    }


def _fund_keys(validated_inputs: dict[str, Any] | None) -> list[str]:
    """Extract fund/symbol keys from inputs, falling back to DEFAULT_FUNDS."""
    funds = (validated_inputs or {}).get("funds")
    if isinstance(funds, dict) and funds:
        return list(funds.keys())
    return list(DEFAULT_FUNDS)


def _eval_L0_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate L0 standing exposure cap limit (state contribution NONE, never latched)."""
    inputs = validated_inputs or {}
    sizing = inputs.get("sizing")
    joint = inputs.get("joint")
    sizing_dict = sizing if isinstance(sizing, dict) else {}
    joint_dict = joint if isinstance(joint, dict) else {}

    cap_raw = sizing_dict.get("max_loss_cap")
    proposed_raw = sizing_dict.get("proposed_exposure")
    joint_raw = joint_dict.get("joint_exposure")

    cap_dec = _to_decimal(cap_raw)
    proposed_dec = _to_decimal(proposed_raw)
    joint_dec = _to_decimal(joint_raw)

    joint_str = str(joint_dec) if joint_dec is not None else joint_raw

    if cap_dec is None or proposed_dec is None or cap_dec < 0 or proposed_dec < 0:
        cell = {
            "scope": "account",
            "state": "NORMAL",
            "would_have_tripped": True,
            "kind": "limit",
            "latched": False,
            "reason_class": "missing_input",
            "reason": "missing or invalid sizing cap/proposed exposure (fail-closed, state contribution NONE)",
            "cap_output": {
                "exposure_cap": str(cap_dec) if cap_dec is not None else cap_raw,
                "proposed_exposure": str(proposed_dec) if proposed_dec is not None else proposed_raw,
                "joint_exposure": joint_str,
                "effective_capped_exposure": "0",
                "cap_breached": True,
            },
        }
        return cell, {"latched": False}

    cap_breached = proposed_dec > cap_dec
    effective_dec = min(proposed_dec, cap_dec)
    reason_class = "cap_breached" if cap_breached else "none"
    reason = (
        f"standing limit: proposed {proposed_dec} > exposure cap {cap_dec}, capped to {effective_dec} (state contribution NONE)"
        if cap_breached
        else f"standing limit: exposure cap {cap_dec}, proposed {proposed_dec}, joint {joint_str} within cap (state contribution NONE)"
    )
    cell = {
        "scope": "account",
        "state": "NORMAL",
        "would_have_tripped": cap_breached,
        "kind": "limit",
        "latched": False,
        "reason_class": reason_class,
        "reason": reason,
        "cap_output": {
            "exposure_cap": str(cap_dec),
            "proposed_exposure": str(proposed_dec),
            "joint_exposure": joint_str,
            "effective_capped_exposure": str(effective_dec),
            "cap_breached": cap_breached,
        },
    }
    return cell, {"latched": False}


def eval_L0(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate L0 standing exposure limit (cap_output, state contribution NONE)."""
    return _eval_L0_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_L1_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate L1 interlock: drawdown >= D/3 notifies and locks tier/H/HWM against loosening."""
    tier, d_frac, d_amount = _tier_budget(validated_inputs)
    loss_dict = (validated_inputs or {}).get("loss")
    drawdown = _to_decimal(loss_dict.get("drawdown_amount") if isinstance(loss_dict, dict) else None)

    if d_amount is None or drawdown is None or drawdown < 0:
        tripped = True
        reason_class = "missing_input"
        reason = "missing or invalid drawdown/tier/bankroll for L1 (fail-closed notify and loosening lock)"
    else:
        tripped = Decimal("3") * drawdown >= d_amount
        if tripped:
            reason_class = "drawdown_reached_D_over_3"
            reason = (
                f"drawdown {drawdown} >= D/3 ({d_amount / Decimal('3')}, tier={tier}, D={d_frac}); "
                "notify and lock tier, H, and high-water mark against loosening (state contribution NONE)"
            )
        else:
            reason_class = "none"
            reason = f"drawdown {drawdown} < D/3 ({d_amount / Decimal('3')}, tier={tier}, D={d_frac})"

    cell = {
        "scope": "account",
        "state": "NORMAL",
        "would_have_tripped": tripped,
        "kind": "interlock",
        "latched": False,
        "reason_class": reason_class,
        "reason": reason,
        "locked_against_loosening": tripped,
        "notify": tripped,
    }
    return cell, {"latched": False, "locked_against_loosening": tripped}


def eval_L1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate L1 interlock (drawdown >= D/3)."""
    return _eval_L1_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_L2_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate L2 breaker: drawdown >= 2D/3 latches NO-NEW-RISK until owner re-arm."""
    prior = _prior_entry(prior_row_state, "L2")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")

    tier, d_frac, d_amount = _tier_budget(validated_inputs)
    loss_dict = (validated_inputs or {}).get("loss")
    drawdown = _to_decimal(loss_dict.get("drawdown_amount") if isinstance(loss_dict, dict) else None)
    rearmed = _has_authorized_event(authorized_events, "L2", REARM_TOKENS)

    if d_amount is None or drawdown is None or drawdown < 0:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "missing_input"
        latch_reason: str | None = "missing_input"
        reason = "missing or invalid drawdown/tier/bankroll for L2 (fail-closed NO-NEW-RISK)"
    elif Decimal("3") * drawdown >= Decimal("2") * d_amount:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "drawdown_reached_2D_over_3"
        latch_reason = "drawdown_reached_2D_over_3"
        reason = (
            f"drawdown {drawdown} >= 2D/3 ({(Decimal('2') * d_amount) / Decimal('3')}, "
            f"tier={tier}, D={d_frac}); L2 breaker trips to NO-NEW-RISK and latches pending owner re-arm"
        )
    elif prior_latched and not rearmed:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "prior_drawdown_reached_2D_over_3"
        )
        reason = f"prior L2 breaker remains latched ({latch_reason}) pending owner re-arm"
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        reason = (
            f"L2 re-armed via authorized_events; drawdown {drawdown} < 2D/3 "
            f"({(Decimal('2') * d_amount) / Decimal('3')}, tier={tier}, D={d_frac})"
            if prior_latched and rearmed
            else f"drawdown {drawdown} < 2D/3 ({(Decimal('2') * d_amount) / Decimal('3')}, tier={tier}, D={d_frac})"
        )

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "breaker",
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
    }
    return cell, {"latched": latched, "latch_reason": latch_reason}


def eval_L2(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate L2 breaker (drawdown >= 2D/3)."""
    return _eval_L2_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_L3_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate L3 breaker: drawdown >= D latches DE-RISK with 30-day cooling-off."""
    prior = _prior_entry(prior_row_state, "L3")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")
    prior_until = prior.get("cooling_off_until")
    prior_until_date = _parse_iso_date(prior_until)
    prior_days = prior.get("cooling_off_days_remaining")

    cur_date = _parse_iso_date(session) or _parse_iso_date(as_of)
    tier, d_frac, d_amount = _tier_budget(validated_inputs)
    loss_dict = (validated_inputs or {}).get("loss")
    drawdown = _to_decimal(loss_dict.get("drawdown_amount") if isinstance(loss_dict, dict) else None)
    owner_card_clear = _has_authorized_event(authorized_events, "L3", L3_CLEAR_TOKENS)

    if prior_latched:
        if prior_until_date is not None and cur_date is not None:
            remaining_days = max(0, (prior_until_date - cur_date).days)
        elif isinstance(prior_days, int) and not isinstance(prior_days, bool) and prior_days > 0:
            remaining_days = prior_days
        else:
            remaining_days = 0
        cooling_off_elapsed = remaining_days == 0
    else:
        remaining_days = 0
        cooling_off_elapsed = True

    if d_amount is None or drawdown is None or drawdown < 0:
        state = "DE-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "missing_input"
        latch_reason: str | None = "missing_input"
        cooling_days = L3_COOLING_OFF_DAYS
        cooling_until = (
            (cur_date + timedelta(days=L3_COOLING_OFF_DAYS)).isoformat()
            if cur_date is not None
            else prior_until
        )
        locked_flat = True
        reason = "missing or invalid drawdown/tier/bankroll for L3 (fail-closed DE-RISK)"
    elif drawdown >= d_amount:
        state = "DE-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "drawdown_reached_D"
        latch_reason = "drawdown_reached_D"
        cooling_days = L3_COOLING_OFF_DAYS
        cooling_until = (
            (cur_date + timedelta(days=L3_COOLING_OFF_DAYS)).isoformat()
            if cur_date is not None
            else None
        )
        locked_flat = True
        reason = (
            f"drawdown {drawdown} >= D ({d_amount}, tier={tier}, D={d_frac}); "
            "L3 breaker trips to DE-RISK to zero, locked flat, 30-day cooling-off recorded, loss record not cleared"
        )
    elif prior_latched and owner_card_clear and cooling_off_elapsed:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        cooling_days = 0
        cooling_until = None
        locked_flat = False
        reason = (
            f"L3 cleared by owner card after cooling-off; drawdown {drawdown} < D "
            f"({d_amount}, tier={tier}, D={d_frac})"
        )
    elif prior_latched:
        state = "DE-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "drawdown_reached_D"
        )
        cooling_days = remaining_days
        cooling_until = prior_until
        locked_flat = True
        reason = (
            f"prior L3 breaker remains latched ({latch_reason}, "
            f"cooling_off_days_remaining={cooling_days})"
        )
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        cooling_days = 0
        cooling_until = None
        locked_flat = False
        reason = f"drawdown {drawdown} < D ({d_amount}, tier={tier}, D={d_frac})"

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "breaker",
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
        "cooling_off_days_remaining": cooling_days,
        "locked_flat": locked_flat,
        "loss_record_cleared": False,
    }
    next_state = {
        "latched": latched,
        "latch_reason": latch_reason,
        "cooling_off_days_remaining": cooling_days,
        "cooling_off_until": cooling_until,
        "locked_flat": locked_flat,
        "loss_record_cleared": False,
        "loss_record_kept": True,
    }
    return cell, next_state


def eval_L3(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate L3 breaker (drawdown >= D)."""
    return _eval_L3_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_L4_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate L4 breaker: session loss >= D/10 latches NO-NEW-RISK until next-session owner ack."""
    prior = _prior_entry(prior_row_state, "L4")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")
    prior_tripped_session = prior.get("tripped_session")

    tier, d_frac, d_amount = _tier_budget(validated_inputs)
    loss_dict = (validated_inputs or {}).get("loss")
    session_loss = _to_decimal(
        loss_dict.get("session_loss_amount") if isinstance(loss_dict, dict) else None
    )
    owner_acked = _has_authorized_event(authorized_events, "L4", L4_ACK_TOKENS)

    if prior_tripped_session is None or session is None:
        next_session_ok = True
    else:
        cur_d = _parse_iso_date(session)
        tripped_d = _parse_iso_date(prior_tripped_session)
        if cur_d is not None and tripped_d is not None:
            next_session_ok = cur_d > tripped_d
        else:
            next_session_ok = str(session) != str(prior_tripped_session)

    if d_amount is None or session_loss is None or session_loss < 0:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "missing_input"
        latch_reason: str | None = "missing_input"
        tripped_session = session
        reason = "missing or invalid session_loss/tier/bankroll for L4 (fail-closed NO-NEW-RISK)"
    elif Decimal("10") * session_loss >= d_amount:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "session_loss_reached_D_over_10"
        latch_reason = "session_loss_reached_D_over_10"
        tripped_session = session
        reason = (
            f"one-session loss {session_loss} >= D/10 ({d_amount / Decimal('10')}, "
            f"tier={tier}, D={d_frac}); L4 breaker trips to NO-NEW-RISK and latches pending owner acknowledgment"
        )
    elif prior_latched and owner_acked and next_session_ok:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        tripped_session = None
        reason = (
            f"L4 cleared on owner acknowledgment after tripped session {prior_tripped_session}; "
            f"one-session loss {session_loss} < D/10 ({d_amount / Decimal('10')}, tier={tier}, D={d_frac})"
        )
    elif prior_latched:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "session_loss_reached_D_over_10"
        )
        tripped_session = prior_tripped_session
        reason = (
            f"prior L4 breaker remains latched ({latch_reason}, "
            f"tripped_session={tripped_session}) pending next-session owner acknowledgment"
        )
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        tripped_session = None
        reason = f"one-session loss {session_loss} < D/10 ({d_amount / Decimal('10')}, tier={tier}, D={d_frac})"

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "breaker",
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
    }
    next_state = {
        "latched": latched,
        "latch_reason": latch_reason,
        "tripped_session": tripped_session,
    }
    return cell, next_state


def eval_L4(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate L4 breaker (one-session loss >= D/10)."""
    return _eval_L4_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_L5_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate L5 interlock: MWCB Level 1 or 2 trips NO-NEW-RISK until 1 clean session."""
    prior = _prior_entry(prior_row_state, "L5")
    prior_active = bool(prior.get("active"))
    prior_clean_raw = prior.get("clean_sessions_count")
    prior_clean = (
        prior_clean_raw
        if isinstance(prior_clean_raw, int)
        and not isinstance(prior_clean_raw, bool)
        and prior_clean_raw >= 0
        else 0
    )

    market = (validated_inputs or {}).get("market")
    market_dict = market if isinstance(market, dict) else {}
    mwcb_level = market_dict.get("mwcb_level")
    clean_session = market_dict.get("clean_session")

    mwcb_valid = (
        isinstance(mwcb_level, int)
        and not isinstance(mwcb_level, bool)
        and mwcb_level >= 0
    )
    clean_valid = isinstance(clean_session, bool)

    if not (mwcb_valid and clean_valid):
        state = "NO-NEW-RISK"
        would_have_tripped = True
        reason_class = "missing_input"
        next_active = True
        next_clean = 0
        reason = "missing or invalid market mwcb_level/clean_session for L5 (fail-closed NO-NEW-RISK)"
    elif mwcb_level in (1, 2):
        state = "NO-NEW-RISK"
        would_have_tripped = True
        reason_class = "mwcb_level_1_or_2"
        next_active = True
        next_clean = 0
        reason = f"market mwcb_level={mwcb_level} (Level 1 or 2 halt); L5 interlock sets NO-NEW-RISK for session"
    elif prior_active:
        if clean_session and mwcb_level == 0:
            new_clean = prior_clean + 1
            if new_clean >= L5_CLEAN_SESSIONS_REQUIRED:
                state = "NORMAL"
                would_have_tripped = False
                reason_class = "none"
                next_active = False
                next_clean = 0
                reason = (
                    f"L5 interlock cleared after {new_clean} clean session(s) "
                    f"(mwcb_level={mwcb_level}, clean_session={clean_session})"
                )
            else:
                state = "NO-NEW-RISK"
                would_have_tripped = True
                reason_class = "active_clearing_counter"
                next_active = True
                next_clean = new_clean
                reason = (
                    f"L5 interlock active ({new_clean}/{L5_CLEAN_SESSIONS_REQUIRED} clean sessions)"
                )
        else:
            state = "NO-NEW-RISK"
            would_have_tripped = True
            reason_class = "active_clearing_counter"
            next_active = True
            next_clean = 0
            reason = (
                f"L5 interlock remains active (mwcb_level={mwcb_level}, "
                f"clean_session={clean_session}; clean counter reset to 0)"
            )
    else:
        state = "NORMAL"
        would_have_tripped = False
        reason_class = "none"
        next_active = False
        next_clean = 0
        reason = f"market mwcb_level={mwcb_level} (not Level 1 or 2) and clean_session={clean_session}"

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "interlock",
        "latched": False,
        "reason_class": reason_class,
        "reason": reason,
    }
    next_state = {
        "latched": False,
        "active": next_active,
        "clean_sessions_count": next_clean,
    }
    return cell, next_state


def eval_L5(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate L5 interlock (MWCB Level 1 or 2)."""
    return _eval_L5_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _parse_index_session_fall(raw: Any) -> Decimal | None:
    """Parse index_session_fall scalar or per-index dict into max non-negative Decimal."""
    if isinstance(raw, dict):
        if not raw:
            return None
        parsed: list[Decimal] = []
        for val in raw.values():
            dec = _to_decimal(val)
            if dec is None or dec < 0:
                return None
            parsed.append(dec)
        return max(parsed)
    dec = _to_decimal(raw)
    if dec is None or dec < 0:
        return None
    return dec


def _eval_L6_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate L6 breaker: MWCB Level 3 or index_session_fall >= 0.10 latches HALT."""
    prior = _prior_entry(prior_row_state, "L6")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")

    market = (validated_inputs or {}).get("market")
    market_dict = market if isinstance(market, dict) else {}
    mwcb_level = market_dict.get("mwcb_level")
    mwcb_valid = (
        isinstance(mwcb_level, int)
        and not isinstance(mwcb_level, bool)
        and mwcb_level >= 0
    )
    fall_dec = _parse_index_session_fall(market_dict.get("index_session_fall"))
    rearmed = _has_authorized_event(
        authorized_events, "L6", REARM_TOKENS, require_reconciled=True
    )

    if not mwcb_valid or fall_dec is None:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "missing_input"
        latch_reason: str | None = "missing_input"
        reason = "missing or invalid market mwcb_level/index_session_fall for L6 (fail-closed HALT)"
    else:
        level3 = mwcb_level >= 3
        fall_tripped = fall_dec >= L6_INDEX_FALL_THRESHOLD
        if level3 or fall_tripped:
            state = "HALT"
            would_have_tripped = True
            latched = True
            if level3 and fall_tripped:
                reason_class = "mwcb_level_3_and_index_fall"
            elif level3:
                reason_class = "mwcb_level_3"
            else:
                reason_class = "index_session_fall_reached_10pct"
            latch_reason = reason_class
            reason = (
                f"mwcb_level={mwcb_level}, index_session_fall={fall_dec} (>= {L6_INDEX_FALL_THRESHOLD}); "
                "L6 breaker trips to HALT and latches pending owner re-arm after reconciliation"
            )
        elif prior_latched and not rearmed:
            state = "HALT"
            would_have_tripped = True
            latched = True
            reason_class = "latched_prior_trip"
            latch_reason = (
                prior_latch_reason
                if isinstance(prior_latch_reason, str) and prior_latch_reason
                else "l6_breaker_latched"
            )
            reason = f"prior L6 breaker remains latched ({latch_reason}) pending reconciled owner re-arm"
        else:
            state = "NORMAL"
            would_have_tripped = False
            latched = False
            reason_class = "none"
            latch_reason = None
            reason = (
                f"L6 re-armed after reconciliation; mwcb_level={mwcb_level} and "
                f"index_session_fall={fall_dec} < {L6_INDEX_FALL_THRESHOLD} (10% CONFIRMED-AS-SPEC)"
                if prior_latched and rearmed
                else f"mwcb_level={mwcb_level} and index_session_fall={fall_dec} < {L6_INDEX_FALL_THRESHOLD} (10% CONFIRMED-AS-SPEC)"
            )

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "breaker",
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
    }
    return cell, {"latched": latched, "latch_reason": latch_reason}


def eval_L6(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate L6 breaker (MWCB Level 3 or index_session_fall >= 0.10)."""
    return _eval_L6_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def eval_V1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for V1."""
    cell = _benign_cell("fund", "breaker")
    cell["by_fund"] = {f: _benign_sub_entry() for f in _fund_keys(validated_inputs)}
    return cell


def eval_V2(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for V2."""
    cell = _benign_cell("fund", "breaker-with-auto-clear-branch")
    cell["by_fund"] = {f: _benign_sub_entry() for f in _fund_keys(validated_inputs)}
    return cell


def eval_V3(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for V3."""
    cell = _benign_cell("fund", "breaker")
    cell["by_fund"] = {f: _benign_sub_entry() for f in _fund_keys(validated_inputs)}
    return cell


def eval_V4(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for V4."""
    cell = _benign_cell("fund", "interlock")
    cell["by_fund"] = {f: _benign_sub_entry() for f in _fund_keys(validated_inputs)}
    return cell


def eval_V5(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for V5."""
    cell = _benign_cell("fund", "diagnostic")
    cell["by_fund"] = {f: _benign_sub_entry() for f in _fund_keys(validated_inputs)}
    return cell


def eval_V6(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for V6."""
    cell = _benign_cell("fund", "diagnostic")
    cell["by_fund"] = {f: _benign_sub_entry() for f in _fund_keys(validated_inputs)}
    return cell


def eval_V7(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for V7."""
    cell = _benign_cell("fund", "interlock")
    cell["by_fund"] = {f: _benign_sub_entry() for f in _fund_keys(validated_inputs)}
    return cell


def eval_O1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O1."""
    return _benign_cell("account", "interlock")


def eval_O2(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O2."""
    return _benign_cell("account", "interlock")


def eval_O3(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O3."""
    return _benign_cell("account", "breaker")


def eval_O4(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O4."""
    cell = _benign_cell("symbol", "interlock-with-breaker-branch")
    cell["by_symbol"] = {s: _benign_sub_entry() for s in _fund_keys(validated_inputs)}
    return cell


def eval_O5(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O5."""
    return _benign_cell("account", "breaker on third rejection (stateful count)")


def eval_O6(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O6."""
    return _benign_cell("account", "breaker")


def eval_O7(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O7."""
    return _benign_cell("account", "breaker")


def eval_O8(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O8."""
    return _benign_cell("account", "owner")


def eval_O9(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for O9."""
    return _benign_cell("account", "breaker")


def eval_J1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for J1."""
    return _benign_cell("joint", "limit")


RowEvaluator = Callable[..., dict[str, Any]]

ROW_EVALUATORS: dict[str, RowEvaluator] = {
    "L0": eval_L0,
    "L1": eval_L1,
    "L2": eval_L2,
    "L3": eval_L3,
    "L4": eval_L4,
    "L5": eval_L5,
    "L6": eval_L6,
    "V1": eval_V1,
    "V2": eval_V2,
    "V3": eval_V3,
    "V4": eval_V4,
    "V5": eval_V5,
    "V6": eval_V6,
    "V7": eval_V7,
    "O1": eval_O1,
    "O2": eval_O2,
    "O3": eval_O3,
    "O4": eval_O4,
    "O5": eval_O5,
    "O6": eval_O6,
    "O7": eval_O7,
    "O8": eval_O8,
    "O9": eval_O9,
    "J1": eval_J1,
}

StatefulRowEvaluator = Callable[..., tuple[dict[str, Any], dict[str, Any]]]

ROW_STATE_EVALUATORS: dict[str, StatefulRowEvaluator] = {
    "L0": _eval_L0_stateful,
    "L1": _eval_L1_stateful,
    "L2": _eval_L2_stateful,
    "L3": _eval_L3_stateful,
    "L4": _eval_L4_stateful,
    "L5": _eval_L5_stateful,
    "L6": _eval_L6_stateful,
}
