"""Row evaluators for FUSE-1 control table.

All 24 control rows (L0-L6, V1-V7, O1-O9, J1) implement pure-Decimal trigger,
latching, interlock, diagnostic, limit, and state logic.
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

V1_DEV_1S_THRESHOLD_PP = Decimal("0.75")
V1_DEV_5S_THRESHOLD_PP = Decimal("2.0")
V4_VOL_MULTIPLE = Decimal("2")
V4_CLEARING_SESSIONS_REQUIRED = 10

V3_CLEAR_TOKENS: frozenset[str] = REARM_TOKENS | frozenset(
    {"owner_decision", "owner_decides", "clear", "resume", "owner_clear"}
)

O1_FRESH_SESSIONS_REQUIRED = 1
O1_MAX_AGE_SESSIONS = Decimal("1")
O2_CLOSED_STATES: frozenset[str] = frozenset(
    {"closed", "holiday", "half_day_past_cutoff"}
)
O4_NON_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        "",
        "none",
        "null",
        "unknown",
        "pending",
        "open",
        "submitted",
        "working",
        "in_flight",
    }
)
O5_HALT_REJECTION_THRESHOLD = 3
O5_COMPLIANCE_FLAG_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("symbol_whitelisted", ("whitelisted_symbol", "symbol_whitelisted")),
    ("account_whitelisted", ("whitelisted_account", "account_whitelisted")),
    ("long_only", ("long_only",)),
    ("within_settled_cash", ("within_settled_cash",)),
    ("within_max_order_size", ("size_within_max", "within_max_order_size")),
    (
        "within_max_orders_per_session",
        ("session_orders_within_max", "within_max_orders_per_session"),
    ),
    (
        "within_max_turnover_per_session",
        ("turnover_within_max", "within_max_turnover_per_session"),
    ),
)
O7_REARM_TOKENS: frozenset[str] = REARM_TOKENS | frozenset(
    {"human_re_arm", "human_rearm"}
)
O8_KILL_TOKENS: frozenset[str] = frozenset(
    {"kill_switch", "killswitch", "owner_kill_switch", "halt", "owner_halt"}
)
O8_CLEAR_TOKENS: frozenset[str] = REARM_TOKENS | frozenset(
    {
        "clear",
        "owner_clear",
        "clear_kill_switch",
        "owner_clear_kill_switch",
        "kill_switch_clear",
        "resume",
        "owner_resume",
        "owner_command_clear",
    }
)
O8_UNSCOPED_CLEAR_TOKENS: frozenset[str] = frozenset(
    {
        "clear_kill_switch",
        "owner_clear_kill_switch",
        "kill_switch_clear",
        "owner_clear",
    }
)
J1_TRIM_MULTIPLIER_NUM = Decimal("11")
J1_TRIM_MULTIPLIER_DEN = Decimal("10")

_STATE_PRECEDENCE: dict[str, int] = {
    "NORMAL": 0,
    "NO-NEW-RISK": 1,
    "DE-RISK": 2,
    "ORDER-UNKNOWN": 3,
    "HALT": 4,
}


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


def _fund_keys(validated_inputs: dict[str, Any] | None) -> list[str]:
    """Extract fund/symbol keys from inputs, falling back to DEFAULT_FUNDS."""
    funds = (validated_inputs or {}).get("funds")
    if isinstance(funds, dict) and funds:
        return list(funds.keys())
    return list(DEFAULT_FUNDS)


def _fund_input(validated_inputs: dict[str, Any] | None, fund: str) -> dict[str, Any]:
    """Return the validated input dict for a specific fund, or empty dict if absent."""
    funds = (validated_inputs or {}).get("funds")
    if not isinstance(funds, dict):
        return {}
    entry = funds.get(fund)
    return entry if isinstance(entry, dict) else {}


def _prior_fund_entry(
    prior_row_state: dict[str, Any] | None,
    row_id: str,
    fund: str,
) -> dict[str, Any]:
    """Return prior state dict for (row_id, fund), or empty dict if absent."""
    row_prior = _prior_entry(prior_row_state, row_id)
    by_fund = row_prior.get("by_fund")
    if not isinstance(by_fund, dict):
        return {}
    entry = by_fund.get(fund)
    return entry if isinstance(entry, dict) else {}


def _event_targets_fund(event: dict[str, Any], fund: str) -> bool:
    """Return True if event targets fund or carries no fund-scoping keys."""
    has_scope = False
    for key in ("fund", "symbol", "target_fund"):
        val = event.get(key)
        if val is not None:
            has_scope = True
            if val == fund:
                return True
    for list_key in ("funds", "symbols"):
        seq = event.get(list_key)
        if seq is not None:
            has_scope = True
            if isinstance(seq, (list, tuple, set)) and fund in seq:
                return True
    return not has_scope


def _has_authorized_fund_event(
    authorized_events: list[Any] | None,
    row_id: str,
    fund: str,
    allowed_tokens: frozenset[str],
    *,
    require_reconciled: bool = False,
) -> bool:
    """Return True if authorized_events contains an authorizing event for (row_id, fund)."""
    if not authorized_events:
        return False
    for event in authorized_events:
        if not isinstance(event, dict):
            continue
        if not _event_targets_row(event, row_id):
            continue
        if not _event_targets_fund(event, fund):
            continue
        if require_reconciled and event.get("reconciled") is False:
            continue
        ev_type = _norm_token(event.get("event_type"))
        ev_action = _norm_token(event.get("action"))
        if ev_type in allowed_tokens or ev_action in allowed_tokens:
            return True
    return False


def _is_fund_event_present(value: Any) -> bool:
    """Return True if a V3 fund_event payload indicates an active event."""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _prior_symbol_entry(
    prior_row_state: dict[str, Any] | None,
    row_id: str,
    symbol: str,
) -> dict[str, Any]:
    """Return prior state dict for (row_id, symbol), or empty dict if absent."""
    row_prior = _prior_entry(prior_row_state, row_id)
    by_symbol = row_prior.get("by_symbol")
    if not isinstance(by_symbol, dict):
        return {}
    entry = by_symbol.get(symbol)
    return entry if isinstance(entry, dict) else {}


def _non_neg_int(value: Any) -> int | None:
    """Return value as int if it is a non-negative non-bool integer, else None."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _is_definitive_terminal_status(value: Any) -> bool:
    """Return True if value represents a definitive broker terminal order status."""
    if not isinstance(value, str):
        return False
    token = _norm_token(value)
    return bool(token) and token not in O4_NON_TERMINAL_STATUSES


def _event_has_row_scope(event: dict[str, Any]) -> bool:
    """Return True if an authorized event carries explicit row-targeting fields."""
    for key in ("row_id", "row", "target_row", "rows", "row_ids"):
        if event.get(key) is not None:
            return True
    return False


def _values_equal(a: Any, b: Any) -> bool:
    """Compare two values using Decimal equality when both parse as Decimal."""
    da = _to_decimal(a)
    db = _to_decimal(b)
    if da is not None and db is not None:
        return da == db
    return a == b


def _format_decimal_clean(value: Decimal) -> str:
    """Format a finite Decimal cleanly without scientific notation or trailing fractional zeros."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _aggregate_scoped_cell(
    scope: str,
    kind: str,
    entries_key: str,
    entries: dict[str, dict[str, Any]],
    reason: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate per-fund or per-symbol entries into a scoped row cell."""
    state = "NORMAL"
    max_prec = 0
    for sub in entries.values():
        prec = _STATE_PRECEDENCE.get(sub["state"], 0)
        if prec > max_prec:
            max_prec = prec
            state = sub["state"]

    would_have_tripped = any(sub["would_have_tripped"] for sub in entries.values())
    latched = any(sub["latched"] for sub in entries.values())

    reason_class = "none"
    tripped_subs = [sub for sub in entries.values() if sub["would_have_tripped"]]
    if tripped_subs:
        best = max(
            tripped_subs,
            key=lambda sub: (
                _STATE_PRECEDENCE.get(sub["state"], 0),
                int(bool(sub["latched"])),
            ),
        )
        reason_class = best["reason_class"]
    else:
        for sub in entries.values():
            if sub["reason_class"] != "none":
                reason_class = sub["reason_class"]
                break

    cell: dict[str, Any] = {
        "scope": scope,
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": kind,
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
        entries_key: entries,
    }
    if extra:
        cell.update(extra)
    return cell


def _aggregate_fund_cell(
    kind: str,
    by_fund: dict[str, dict[str, Any]],
    reason: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate per-fund entries into a fund-scoped row cell."""
    return _aggregate_scoped_cell(
        "fund", kind, "by_fund", by_fund, reason, extra=extra
    )


def _aggregate_symbol_cell(
    kind: str,
    by_symbol: dict[str, dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    """Aggregate per-symbol entries into a symbol-scoped row cell."""
    return _aggregate_scoped_cell("symbol", kind, "by_symbol", by_symbol, reason)


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


def _eval_V1_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate V1 breaker: 1s tracking dev > 0.75pp or 5s > 2.0pp latches NO-NEW-RISK per fund."""
    by_fund: dict[str, dict[str, Any]] = {}
    next_by_fund: dict[str, dict[str, Any]] = {}

    for fund in _fund_keys(validated_inputs):
        fund_data = _fund_input(validated_inputs, fund)
        prior_f = _prior_fund_entry(prior_row_state, "V1", fund)
        prior_latched = bool(prior_f.get("latched"))
        prior_latch_reason = prior_f.get("latch_reason")
        rearmed = _has_authorized_fund_event(
            authorized_events, "V1", fund, REARM_TOKENS
        )

        dev_1s = _to_decimal(fund_data.get("tracking_dev_1s_pp"))
        dev_5s = _to_decimal(fund_data.get("tracking_dev_5s_pp"))

        if dev_1s is None or dev_5s is None:
            state = "NO-NEW-RISK"
            would_have_tripped = True
            latched = True
            reason_class = "missing_input"
            latch_reason: str | None = "missing_input"
            reason = (
                f"{fund} missing or invalid tracking deviation inputs for V1 "
                "(fail-closed NO-NEW-RISK)"
            )
        else:
            exceed_1s = abs(dev_1s) > V1_DEV_1S_THRESHOLD_PP
            exceed_5s = abs(dev_5s) > V1_DEV_5S_THRESHOLD_PP
            if exceed_1s or exceed_5s:
                state = "NO-NEW-RISK"
                would_have_tripped = True
                latched = True
                if exceed_1s and exceed_5s:
                    reason_class = "tracking_dev_1s_and_5s"
                elif exceed_1s:
                    reason_class = "tracking_dev_1s_exceeded"
                else:
                    reason_class = "tracking_dev_5s_exceeded"
                latch_reason = reason_class
                reason = (
                    f"{fund} tracking deviations {dev_1s}pp (1s) / {dev_5s}pp (5s) exceed "
                    f"CONFIRMED-AS-SPEC limits ({V1_DEV_1S_THRESHOLD_PP}pp / {V1_DEV_5S_THRESHOLD_PP}pp); "
                    "V1 breaker trips to NO-NEW-RISK and latches pending owner re-arm"
                )
            elif prior_latched and not rearmed:
                state = "NO-NEW-RISK"
                would_have_tripped = True
                latched = True
                reason_class = "latched_prior_trip"
                latch_reason = (
                    prior_latch_reason
                    if isinstance(prior_latch_reason, str) and prior_latch_reason
                    else "tracking_dev_latched"
                )
                reason = (
                    f"{fund} prior V1 breaker remains latched ({latch_reason}) "
                    "pending owner re-arm"
                )
            else:
                state = "NORMAL"
                would_have_tripped = False
                latched = False
                reason_class = "none"
                latch_reason = None
                reason = (
                    f"{fund} V1 re-armed; tracking deviations {dev_1s}pp (1s <= {V1_DEV_1S_THRESHOLD_PP}pp) "
                    f"and {dev_5s}pp (5s <= {V1_DEV_5S_THRESHOLD_PP}pp) within CONFIRMED-AS-SPEC limits"
                    if prior_latched and rearmed
                    else f"{fund} tracking deviations {dev_1s}pp (1s <= {V1_DEV_1S_THRESHOLD_PP}pp) "
                    f"and {dev_5s}pp (5s <= {V1_DEV_5S_THRESHOLD_PP}pp) within CONFIRMED-AS-SPEC limits"
                )

        by_fund[fund] = {
            "state": state,
            "would_have_tripped": would_have_tripped,
            "latched": latched,
            "reason_class": reason_class,
            "reason": reason,
        }
        next_by_fund[fund] = {
            "latched": latched,
            "latch_reason": latch_reason,
        }

    tripped_funds = [f for f, sub in by_fund.items() if sub["would_have_tripped"]]
    top_reason = (
        f"V1 tracking deviation breaker tripped/latched for {', '.join(tripped_funds)}"
        if tripped_funds
        else f"tracking deviations within {V1_DEV_1S_THRESHOLD_PP}pp (1s) and {V1_DEV_5S_THRESHOLD_PP}pp (5s) limits"
    )
    cell = _aggregate_fund_cell("breaker", by_fund, top_reason)
    return cell, {"by_fund": next_by_fund}


def eval_V1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate V1 fund tracking deviation breaker."""
    return _eval_V1_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_V2_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate V2 corporate action breaker-with-auto-clear-branch per fund."""
    by_fund: dict[str, dict[str, Any]] = {}
    next_by_fund: dict[str, dict[str, Any]] = {}

    for fund in _fund_keys(validated_inputs):
        fund_data = _fund_input(validated_inputs, fund)
        prior_f = _prior_fund_entry(prior_row_state, "V2", fund)
        prior_latched = bool(prior_f.get("latched"))
        prior_latch_reason = prior_f.get("latch_reason")
        rearmed = _has_authorized_fund_event(
            authorized_events, "V2", fund, REARM_TOKENS
        )
        ca = fund_data.get("corporate_action")

        if ca is None:
            if prior_latched and not rearmed:
                state = "HALT"
                would_have_tripped = True
                latched = True
                reason_class = "latched_prior_trip"
                latch_reason: str | None = (
                    prior_latch_reason
                    if isinstance(prior_latch_reason, str) and prior_latch_reason
                    else "corporate_action_reconciliation_failed"
                )
                reason = (
                    f"{fund} prior V2 breaker remains latched ({latch_reason}) "
                    "pending owner re-arm"
                )
            else:
                state = "NORMAL"
                would_have_tripped = False
                latched = False
                reason_class = "none"
                latch_reason = None
                reason = f"no corporate action for {fund}"
        elif not isinstance(ca, dict):
            state = "HALT"
            would_have_tripped = True
            latched = True
            reason_class = "missing_input"
            latch_reason = "missing_input"
            reason = f"{fund} invalid corporate_action payload for V2 (fail-closed HALT)"
        else:
            ledger_adjusted = ca.get("ledger_adjusted") is True
            reconciles_exactly = ca.get("reconciles_exactly") is True
            ca_type = ca.get("type") or "corporate_action"
            if ledger_adjusted and reconciles_exactly:
                if prior_latched and not rearmed:
                    state = "HALT"
                    would_have_tripped = True
                    latched = True
                    reason_class = "latched_prior_trip"
                    latch_reason = (
                        prior_latch_reason
                        if isinstance(prior_latch_reason, str) and prior_latch_reason
                        else "corporate_action_reconciliation_failed"
                    )
                    reason = (
                        f"{fund} prior V2 breaker remains latched ({latch_reason}) "
                        "pending owner re-arm"
                    )
                else:
                    state = "NORMAL"
                    would_have_tripped = False
                    latched = False
                    reason_class = "reconciled"
                    latch_reason = None
                    reason = (
                        f"{fund} {ca_type} ledger_adjusted=True and reconciles_exactly=True; "
                        "V2 auto-cleared"
                    )
            elif ledger_adjusted and not reconciles_exactly:
                state = "HALT"
                would_have_tripped = True
                latched = True
                reason_class = "corporate_action_reconciliation_failed"
                latch_reason = "corporate_action_reconciliation_failed"
                reason = (
                    f"{fund} {ca_type} ledger_adjusted=True but reconciles_exactly=False; "
                    "V2 breaker latches HALT pending owner re-arm"
                )
            else:
                if prior_latched and not rearmed:
                    state = "HALT"
                    would_have_tripped = True
                    latched = True
                    reason_class = "latched_prior_trip"
                    latch_reason = (
                        prior_latch_reason
                        if isinstance(prior_latch_reason, str) and prior_latch_reason
                        else "corporate_action_reconciliation_failed"
                    )
                    reason = (
                        f"{fund} prior V2 breaker remains latched ({latch_reason}) "
                        "pending owner re-arm"
                    )
                else:
                    state = "HALT"
                    would_have_tripped = True
                    latched = False
                    reason_class = "corporate_action_pending"
                    latch_reason = None
                    reason = (
                        f"{fund} {ca_type} announced={ca.get('announced')} "
                        f"detected_in_price={ca.get('detected_in_price')} with "
                        f"ledger_adjusted={ledger_adjusted}, reconciles_exactly={reconciles_exactly}; "
                        f"HALT in fund:{fund} pending adjustment (not latched)"
                    )

        by_fund[fund] = {
            "state": state,
            "would_have_tripped": would_have_tripped,
            "latched": latched,
            "reason_class": reason_class,
            "reason": reason,
        }
        next_by_fund[fund] = {
            "latched": latched,
            "latch_reason": latch_reason,
        }

    tripped_funds = [f for f, sub in by_fund.items() if sub["would_have_tripped"]]
    reconciled_funds = [f for f, sub in by_fund.items() if sub["reason_class"] == "reconciled"]
    if tripped_funds:
        top_reason = f"corporate action HALT for {', '.join(tripped_funds)}"
    elif reconciled_funds:
        top_reason = f"corporate action reconciled and auto-cleared for {', '.join(reconciled_funds)}"
    else:
        top_reason = "no split, reverse split, or distribution"
    cell = _aggregate_fund_cell("breaker-with-auto-clear-branch", by_fund, top_reason)
    return cell, {"by_fund": next_by_fund}


def eval_V2(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate V2 corporate action breaker-with-auto-clear-branch."""
    return _eval_V2_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_V3_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate V3 breaker: issuer/exchange/delisting fund_event latches DE-RISK per fund."""
    by_fund: dict[str, dict[str, Any]] = {}
    next_by_fund: dict[str, dict[str, Any]] = {}

    for fund in _fund_keys(validated_inputs):
        fund_data = _fund_input(validated_inputs, fund)
        prior_f = _prior_fund_entry(prior_row_state, "V3", fund)
        prior_latched = bool(prior_f.get("latched"))
        prior_latch_reason = prior_f.get("latch_reason")
        cleared = _has_authorized_fund_event(
            authorized_events, "V3", fund, V3_CLEAR_TOKENS
        )
        fund_event = fund_data.get("fund_event")

        if _is_fund_event_present(fund_event):
            state = "DE-RISK"
            would_have_tripped = True
            latched = True
            reason_class = "fund_event"
            latch_reason: str | None = "fund_event"
            reason = (
                f"{fund} fund_event present ({fund_event!r}); "
                "V3 breaker trips to DE-RISK and latches pending owner decision"
            )
        elif prior_latched and not cleared:
            state = "DE-RISK"
            would_have_tripped = True
            latched = True
            reason_class = "latched_prior_trip"
            latch_reason = (
                prior_latch_reason
                if isinstance(prior_latch_reason, str) and prior_latch_reason
                else "fund_event"
            )
            reason = (
                f"{fund} prior V3 breaker remains latched ({latch_reason}) "
                "pending owner decision"
            )
        else:
            state = "NORMAL"
            would_have_tripped = False
            latched = False
            reason_class = "none"
            latch_reason = None
            reason = (
                f"{fund} V3 cleared via authorized_events; no fund_event"
                if prior_latched and cleared
                else f"no issuer, exchange halt, or delisting event for {fund}"
            )

        by_fund[fund] = {
            "state": state,
            "would_have_tripped": would_have_tripped,
            "latched": latched,
            "reason_class": reason_class,
            "reason": reason,
        }
        next_by_fund[fund] = {
            "latched": latched,
            "latch_reason": latch_reason,
        }

    tripped_funds = [f for f, sub in by_fund.items() if sub["would_have_tripped"]]
    top_reason = (
        f"V3 fund_event DE-RISK breaker tripped/latched for {', '.join(tripped_funds)}"
        if tripped_funds
        else "no fund_event"
    )
    cell = _aggregate_fund_cell("breaker", by_fund, top_reason)
    return cell, {"by_fund": next_by_fund}


def eval_V3(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate V3 issuer/exchange/delisting fund_event breaker."""
    return _eval_V3_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_V4_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate V4 interlock: forecast_vol >= 2x long_run_vol trips NO-NEW-RISK until 10 sessions below."""
    data_inputs = (validated_inputs or {}).get("data_inputs")
    vol_meta = data_inputs.get("volatility") if isinstance(data_inputs, dict) else {}
    vol_meta_dict = vol_meta if isinstance(vol_meta, dict) else {}
    vol_meta_missing = bool(
        vol_meta_dict
        and (
            vol_meta_dict.get("present") is False
            or vol_meta_dict.get("valid") is False
        )
    )

    last_valid = _to_decimal(vol_meta_dict.get("last_valid"))
    stress_default = _to_decimal(vol_meta_dict.get("stress_default"))
    sub_candidates = [v for v in (last_valid, stress_default) if v is not None and v >= 0]
    substituted_vol = max(sub_candidates) if sub_candidates else None

    by_fund: dict[str, dict[str, Any]] = {}
    next_by_fund: dict[str, dict[str, Any]] = {}

    for fund in _fund_keys(validated_inputs):
        fund_data = _fund_input(validated_inputs, fund)
        prior_f = _prior_fund_entry(prior_row_state, "V4", fund)
        prior_active = bool(prior_f.get("active"))
        prior_below_raw = prior_f.get("below_threshold_sessions")
        prior_below = (
            prior_below_raw
            if isinstance(prior_below_raw, int)
            and not isinstance(prior_below_raw, bool)
            and prior_below_raw >= 0
            else 0
        )

        forecast_vol = _to_decimal(fund_data.get("forecast_vol"))
        long_run_vol = _to_decimal(fund_data.get("long_run_vol"))
        emit_sub = False

        vol_missing_or_invalid = (
            forecast_vol is None or forecast_vol < 0 or vol_meta_missing
        )
        if vol_missing_or_invalid or long_run_vol is None or long_run_vol <= 0:
            state = "NO-NEW-RISK"
            would_have_tripped = True
            reason_class = "missing_input"
            next_active = True
            next_below = 0
            emit_sub = substituted_vol is not None and vol_missing_or_invalid
            reason = (
                f"missing_input: {fund} forecast_vol missing/invalid; fail-closed trip "
                f"with stress substitution {substituted_vol}"
                if emit_sub
                else f"missing_input: {fund} missing or invalid forecast_vol/long_run_vol for V4 (fail-closed NO-NEW-RISK)"
            )
        elif forecast_vol >= V4_VOL_MULTIPLE * long_run_vol:
            threshold = V4_VOL_MULTIPLE * long_run_vol
            state = "NO-NEW-RISK"
            would_have_tripped = True
            reason_class = "forecast_vol_exceeded_2x_long_run"
            next_active = True
            next_below = 0
            reason = (
                f"{fund} forecast_vol {forecast_vol} >= 2x long_run_vol ({threshold}); "
                "V4 interlock trips to NO-NEW-RISK (below_threshold_sessions=0)"
            )
        elif prior_active:
            threshold = V4_VOL_MULTIPLE * long_run_vol
            new_below = prior_below + 1
            if new_below >= V4_CLEARING_SESSIONS_REQUIRED:
                state = "NORMAL"
                would_have_tripped = False
                reason_class = "none"
                next_active = False
                next_below = 0
                reason = (
                    f"{fund} V4 interlock cleared after {new_below} sessions below "
                    f"2x long_run_vol ({threshold})"
                )
            else:
                state = "NO-NEW-RISK"
                would_have_tripped = True
                reason_class = "active_clearing_counter"
                next_active = True
                next_below = new_below
                reason = (
                    f"{fund} prior V4 active state preserved; forecast_vol {forecast_vol} < 2x long_run_vol ({threshold}) "
                    f"advances below_threshold_sessions {prior_below} -> {new_below} (< {V4_CLEARING_SESSIONS_REQUIRED} required to clear)"
                )
        else:
            threshold = V4_VOL_MULTIPLE * long_run_vol
            state = "NORMAL"
            would_have_tripped = False
            reason_class = "none"
            next_active = False
            next_below = 0
            reason = f"{fund} forecast_vol {forecast_vol} < 2x long_run_vol ({threshold})"

        entry: dict[str, Any] = {
            "state": state,
            "would_have_tripped": would_have_tripped,
            "latched": False,
            "reason_class": reason_class,
            "reason": reason,
            "active": next_active,
            "below_threshold_sessions": next_below,
            "clearing_threshold_sessions": V4_CLEARING_SESSIONS_REQUIRED,
            "prior_below_threshold_sessions": prior_below,
        }
        if emit_sub and substituted_vol is not None:
            entry["substituted_vol"] = str(substituted_vol)

        by_fund[fund] = entry
        next_by_fund[fund] = {
            "latched": False,
            "active": next_active,
            "below_threshold_sessions": next_below,
        }

    tripped_funds = [f for f, sub in by_fund.items() if sub["would_have_tripped"]]
    top_reason = (
        f"V4 volatility interlock active for {', '.join(tripped_funds)}"
        if tripped_funds
        else "forecast_vol < 2x long_run_vol"
    )
    cell = _aggregate_fund_cell("interlock", by_fund, top_reason)
    return cell, {"by_fund": next_by_fund}


def eval_V4(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate V4 forecast volatility interlock."""
    return _eval_V4_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_V5_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate V5 diagnostic: 60s decay tolerance is UNRESOLVED-FAIL-CLOSED."""
    by_fund: dict[str, dict[str, Any]] = {}
    diag_by_fund: dict[str, dict[str, Any]] = {}
    next_by_fund: dict[str, dict[str, Any]] = {}

    for fund in _fund_keys(validated_inputs):
        fund_data = _fund_input(validated_inputs, fund)
        prior_f = _prior_fund_entry(prior_row_state, "V5", fund)
        prior_pers_raw = prior_f.get("persistent_sessions")
        prior_pers = (
            prior_pers_raw
            if isinstance(prior_pers_raw, int)
            and not isinstance(prior_pers_raw, bool)
            and prior_pers_raw >= 0
            else 0
        )
        next_pers = prior_pers + 1

        shortfall_raw = fund_data.get("decay_shortfall_60s")
        predicted_raw = fund_data.get("decay_predicted_60s")
        shortfall_dec = _to_decimal(shortfall_raw)
        predicted_dec = _to_decimal(predicted_raw)
        excess_str = (
            str(shortfall_dec - predicted_dec)
            if shortfall_dec is not None and predicted_dec is not None
            else None
        )

        by_fund[fund] = {
            "state": "NORMAL",
            "would_have_tripped": True,
            "latched": False,
            "reason_class": "unresolved_fail_closed",
            "reason": (
                f"{fund} V5 decay tolerance is UNRESOLVED-FAIL-CLOSED (never numeric default or 0); "
                f"fail-closed diagnostic notify (persistent_sessions {prior_pers} -> {next_pers}, state contribution NONE)"
            ),
        }
        diag_by_fund[fund] = {
            "decay_shortfall_60s": str(shortfall_dec) if shortfall_dec is not None else shortfall_raw,
            "decay_predicted_60s": str(predicted_dec) if predicted_dec is not None else predicted_raw,
            "excess_shortfall_60s": excess_str,
            "tolerance": None,
            "fail_closed": True,
            "notify": True,
            "persistent_sessions": next_pers,
            "escalated_to_v1": False,
        }
        next_by_fund[fund] = {
            "latched": False,
            "persistent_sessions": next_pers,
            "escalated_to_v1": False,
        }

    top_reason = (
        "V5 decay tolerance is UNRESOLVED-FAIL-CLOSED in disposition_register; "
        "evaluation fails closed to diagnostic notify without numeric default or 0 (state contribution NONE)"
    )
    cell = _aggregate_fund_cell(
        "diagnostic",
        by_fund,
        top_reason,
        extra={
            "diagnostic_output": {
                "tolerance_disposition": "UNRESOLVED-FAIL-CLOSED",
                "by_fund": diag_by_fund,
            }
        },
    )
    return cell, {"by_fund": next_by_fund}


def eval_V5(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate V5 60s decay diagnostic."""
    return _eval_V5_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_V6_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate V6 diagnostic: carrying_cost.measured_per_unit > quarter_shrunk_excess."""
    by_fund: dict[str, dict[str, Any]] = {}
    diag_by_fund: dict[str, dict[str, Any]] = {}
    next_by_fund: dict[str, dict[str, Any]] = {}

    for fund in _fund_keys(validated_inputs):
        fund_data = _fund_input(validated_inputs, fund)
        cc = fund_data.get("carrying_cost")
        cc_dict = cc if isinstance(cc, dict) else {}

        measured_raw = cc_dict.get("measured_per_unit")
        quarter_raw = cc_dict.get("quarter_shrunk_excess")
        measured_dec = _to_decimal(measured_raw)
        quarter_dec = _to_decimal(quarter_raw)

        if measured_dec is None or quarter_dec is None:
            tripped = True
            reason_class = "missing_input"
            headroom_str: str | None = None
            reason = (
                f"{fund} missing or invalid carrying_cost inputs for V6 "
                "(fail-closed diagnostic notify, state contribution NONE)"
            )
        else:
            tripped = measured_dec > quarter_dec
            headroom_str = str(quarter_dec - measured_dec)
            if tripped:
                reason_class = "carrying_cost_exceeded"
                reason = (
                    f"{fund} carrying cost {measured_dec} > quarter shrunk excess {quarter_dec} "
                    "(diagnostic notify=true, policy review required, state contribution NONE)"
                )
            else:
                reason_class = "none"
                reason = (
                    f"{fund} carrying cost {measured_dec} <= quarter shrunk excess {quarter_dec} "
                    "(diagnostic notify=false)"
                )

        by_fund[fund] = {
            "state": "NORMAL",
            "would_have_tripped": tripped,
            "latched": False,
            "reason_class": reason_class,
            "reason": reason,
        }
        diag_by_fund[fund] = {
            "measured_per_unit": str(measured_dec) if measured_dec is not None else measured_raw,
            "quarter_shrunk_excess": str(quarter_dec) if quarter_dec is not None else quarter_raw,
            "headroom": headroom_str,
            "notify": tripped,
            "policy_review_required": tripped,
        }
        next_by_fund[fund] = {"latched": False}

    tripped_funds = [f for f, sub in by_fund.items() if sub["would_have_tripped"]]
    top_reason = (
        f"carrying cost diagnostic triggered for {', '.join(tripped_funds)} (state contribution NONE)"
        if tripped_funds
        else "measured carrying cost <= quarter shrunk excess (diagnostic notify=false)"
    )
    cell = _aggregate_fund_cell(
        "diagnostic",
        by_fund,
        top_reason,
        extra={"diagnostic_output": {"by_fund": diag_by_fund}},
    )
    return cell, {"by_fund": next_by_fund}


def eval_V6(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate V6 carrying cost diagnostic."""
    return _eval_V6_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_V7_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate V7 order-level interlock: stale quote, pause, outside session, or unresolved spread."""
    by_fund: dict[str, dict[str, Any]] = {}
    next_by_fund: dict[str, dict[str, Any]] = {}

    for fund in _fund_keys(validated_inputs):
        fund_data = _fund_input(validated_inputs, fund)
        quote = fund_data.get("quote")

        if not isinstance(quote, dict):
            tripped = True
            reason_class = "missing_input"
            reason = (
                f"{fund} missing or invalid quote payload for V7; "
                "fail-closed order-level gate: order not sent (state contribution NONE)"
            )
        elif quote.get("stale") is True:
            tripped = True
            reason_class = "stale_quote"
            reason = (
                f"{fund} quote is stale; order-level gate fails closed: "
                "order not sent (state contribution NONE)"
            )
        elif quote.get("single_stock_pause") is True:
            tripped = True
            reason_class = "single_stock_pause"
            reason = (
                f"{fund} single_stock_pause active; order-level gate fails closed: "
                "order not sent (state contribution NONE)"
            )
        elif quote.get("in_regular_session") is False:
            tripped = True
            reason_class = "outside_regular_session"
            reason = (
                f"{fund} outside regular session; order-level gate fails closed: "
                "order not sent (state contribution NONE)"
            )
        elif (
            not isinstance(quote.get("stale"), bool)
            or not isinstance(quote.get("single_stock_pause"), bool)
            or not isinstance(quote.get("in_regular_session"), bool)
        ):
            tripped = True
            reason_class = "missing_input"
            reason = (
                f"{fund} missing or invalid quote status flags for V7; "
                "fail-closed order-level gate: order not sent (state contribution NONE)"
            )
        else:
            spread_dec = _to_decimal(quote.get("spread"))
            if spread_dec is None or spread_dec < 0:
                tripped = True
                reason_class = "missing_input"
                reason = (
                    f"{fund} missing or invalid quote.spread value for V7; "
                    "fail-closed order-level gate: order not sent (state contribution NONE)"
                )
            else:
                tripped = True
                reason_class = "unresolved_fail_closed"
                reason = (
                    f"{fund} V7 spread width is UNRESOLVED-FAIL-CLOSED "
                    f"(quote.spread={spread_dec} cannot clear an unresolved width); "
                    "fail-closed order-level gate: order not sent (state contribution NONE)"
                )

        by_fund[fund] = {
            "state": "NORMAL",
            "would_have_tripped": tripped,
            "latched": False,
            "reason_class": reason_class,
            "reason": reason,
        }
        next_by_fund[fund] = {"latched": False}

    tripped_funds = [f for f, sub in by_fund.items() if sub["would_have_tripped"]]
    top_reason = (
        f"V7 order-level gate blocked order for {', '.join(tripped_funds)} (order not sent, state contribution NONE)"
        if tripped_funds
        else "quote gates clear"
    )
    cell = _aggregate_fund_cell("interlock", by_fund, top_reason)
    return cell, {"by_fund": next_by_fund}


def eval_V7(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate V7 quote/session order-level interlock."""
    return _eval_V7_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_O1_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O1 interlock: missing/invalid/stale data_inputs triggers NO-NEW-RISK until 1 fresh session."""
    prior = _prior_entry(prior_row_state, "O1")
    prior_active = bool(prior.get("active"))
    prior_fresh = _non_neg_int(prior.get("fresh_sessions_count")) or 0

    data_inputs = (validated_inputs or {}).get("data_inputs")
    if not isinstance(data_inputs, dict) or not data_inputs:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        reason_class = "missing_input"
        next_active = True
        next_fresh = 0
        reason = "missing or invalid data_inputs for O1 (fail-closed NO-NEW-RISK)"
    else:
        missing_names: list[str] = []
        invalid_names: list[str] = []
        stale_names: list[str] = []
        max_age = Decimal("0")

        for name, entry in data_inputs.items():
            if not isinstance(entry, dict):
                missing_names.append(str(name))
                continue
            present = entry.get("present")
            valid = entry.get("valid")
            age_dec = _to_decimal(entry.get("age_sessions"))
            if present is not True:
                missing_names.append(str(name))
            elif valid is False:
                invalid_names.append(str(name))
            elif valid is not True:
                missing_names.append(str(name))
            elif age_dec is None or age_dec < 0:
                missing_names.append(str(name))
            elif age_dec > O1_MAX_AGE_SESSIONS:
                stale_names.append(str(name))
            elif age_dec > max_age:
                max_age = age_dec

        vol_sub_note = ""
        if "volatility" in missing_names or "volatility" in invalid_names:
            vol_entry = data_inputs.get("volatility")
            if isinstance(vol_entry, dict):
                last_valid = _to_decimal(vol_entry.get("last_valid"))
                stress_default = _to_decimal(vol_entry.get("stress_default"))
                candidates = [
                    v for v in (last_valid, stress_default) if v is not None and v >= 0
                ]
                if candidates:
                    vol_sub_note = (
                        f"; substitute max(last_valid={last_valid}, "
                        f"stress_default={stress_default})={max(candidates)}, "
                        "block increases, never return-1-on-missing"
                    )

        if missing_names:
            state = "NO-NEW-RISK"
            would_have_tripped = True
            reason_class = "missing_input"
            next_active = True
            next_fresh = 0
            reason = (
                f"missing_input: data_inputs {', '.join(missing_names)} missing/absent"
                f"{vol_sub_note}; O1 interlock trips to NO-NEW-RISK"
            )
        elif invalid_names:
            state = "NO-NEW-RISK"
            would_have_tripped = True
            reason_class = "invalid_input"
            next_active = True
            next_fresh = 0
            reason = (
                f"invalid_input: data_inputs {', '.join(invalid_names)} failed validation"
                f"{vol_sub_note}; O1 interlock trips to NO-NEW-RISK"
            )
        elif stale_names:
            state = "NO-NEW-RISK"
            would_have_tripped = True
            reason_class = "stale_input"
            next_active = True
            next_fresh = 0
            stale_desc = ", ".join(
                f"{n}.age_sessions={data_inputs[n].get('age_sessions')}"
                for n in stale_names
            )
            reason = (
                f"stale required input: {stale_desc} (> {O1_MAX_AGE_SESSIONS}); "
                "O1 interlock trips to NO-NEW-RISK until one session of fresh data"
            )
        elif prior_active:
            new_fresh = prior_fresh + 1
            if new_fresh >= O1_FRESH_SESSIONS_REQUIRED:
                state = "NORMAL"
                would_have_tripped = False
                reason_class = "none"
                next_active = False
                next_fresh = 0
                reason = (
                    f"O1 interlock cleared after {new_fresh} session(s) of fresh data "
                    f"(max age_sessions={max_age} <= {O1_MAX_AGE_SESSIONS})"
                )
            else:
                state = "NO-NEW-RISK"
                would_have_tripped = True
                reason_class = "active_clearing_counter"
                next_active = True
                next_fresh = new_fresh
                reason = (
                    f"O1 interlock active ({new_fresh}/{O1_FRESH_SESSIONS_REQUIRED} fresh sessions)"
                )
        else:
            state = "NORMAL"
            would_have_tripped = False
            reason_class = "none"
            next_active = False
            next_fresh = 0
            reason = (
                f"all required data_inputs present, valid, and age_sessions={max_age} <= {O1_MAX_AGE_SESSIONS}"
            )

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
        "fresh_sessions_count": next_fresh,
    }
    return cell, next_state


def eval_O1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O1 data freshness/validity interlock."""
    return _eval_O1_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_O2_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O2 session calendar/exchange interlock (session gate: no order, state contribution NONE)."""
    calendar = (validated_inputs or {}).get("calendar")
    if not isinstance(calendar, dict):
        tripped = True
        reason_class = "missing_input"
        reason = (
            "missing or invalid calendar payload for O2; "
            "session-level order gate trips: no order (state contribution NONE)"
        )
    else:
        session_state = calendar.get("session_state")
        exchange_agrees = calendar.get("exchange_agrees")
        if (
            not isinstance(session_state, str)
            or not session_state.strip()
            or not isinstance(exchange_agrees, bool)
        ):
            tripped = True
            reason_class = "missing_input"
            reason = (
                "missing or invalid calendar session_state/exchange_agrees for O2; "
                "session-level order gate trips: no order (state contribution NONE)"
            )
        else:
            session_norm = session_state.strip().lower()
            if exchange_agrees is False:
                tripped = True
                reason_class = "calendar_disagreement"
                reason = (
                    f"calendar.session_state={session_state} with exchange_agrees=False; "
                    "session-level order gate trips: no order (state contribution NONE)"
                )
            elif session_norm in O2_CLOSED_STATES:
                tripped = True
                reason_class = "calendar_closed"
                reason = (
                    f"calendar.session_state={session_state} (exchange_agrees={exchange_agrees}); "
                    "session-level order gate trips: no order (state contribution NONE)"
                )
            elif session_norm != "open":
                tripped = True
                reason_class = "missing_input"
                reason = (
                    f"unrecognized calendar.session_state={session_state!r} for O2; "
                    "session-level order gate trips: no order (state contribution NONE)"
                )
            else:
                tripped = False
                reason_class = "none"
                reason = "calendar.session_state=open and exchange_agrees=true"

    cell = {
        "scope": "account",
        "state": "NORMAL",
        "would_have_tripped": tripped,
        "kind": "interlock",
        "latched": False,
        "reason_class": reason_class,
        "reason": reason,
    }
    return cell, {"latched": False}


def eval_O2(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O2 session calendar gate."""
    return _eval_O2_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_O3_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O3 breaker: positions or cash beyond broker tolerance latches HALT."""
    prior = _prior_entry(prior_row_state, "O3")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")
    rearmed = _has_authorized_event(authorized_events, "O3", REARM_TOKENS)

    broker = (validated_inputs or {}).get("broker_record")
    pos_bt = broker.get("positions_beyond_tolerance") if isinstance(broker, dict) else None
    cash_bt = broker.get("cash_beyond_tolerance") if isinstance(broker, dict) else None

    if not isinstance(pos_bt, bool) or not isinstance(cash_bt, bool):
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "missing_input"
        latch_reason: str | None = "missing_input"
        reason = "missing or invalid broker_record tolerance flags for O3 (fail-closed HALT)"
    elif pos_bt or cash_bt:
        state = "HALT"
        would_have_tripped = True
        latched = True
        if pos_bt and cash_bt:
            reason_class = "positions_and_cash_beyond_tolerance"
        elif pos_bt:
            reason_class = "positions_beyond_tolerance"
        else:
            reason_class = "cash_beyond_tolerance"
        latch_reason = reason_class
        reason = (
            f"broker reconciliation breach (positions_beyond_tolerance={pos_bt}, "
            f"cash_beyond_tolerance={cash_bt}); O3 breaker latches HALT pending owner re-arm"
        )
    elif prior_latched and not rearmed:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "broker_record_beyond_tolerance"
        )
        reason = f"prior O3 breaker remains latched ({latch_reason}) pending owner re-arm"
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        reason = (
            "O3 re-armed via authorized_events; broker positions and cash within tolerance"
            if prior_latched and rearmed
            else "broker positions and cash within tolerance"
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


def eval_O3(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O3 broker positions/cash reconciliation breaker."""
    return _eval_O3_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_O4_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O4 symbol-scoped order-outcome interlock-with-breaker-branch."""
    symbols = list(_fund_keys(validated_inputs))
    prior_by_symbol = _prior_entry(prior_row_state, "O4").get("by_symbol")
    if isinstance(prior_by_symbol, dict):
        for sym in sorted(prior_by_symbol):
            if sym not in symbols:
                symbols.append(sym)

    orders = (validated_inputs or {}).get("orders")
    orders_valid = isinstance(orders, dict) and "pending" in orders
    entries: list[Any] = []
    if orders_valid:
        pending_raw = orders["pending"]
        if pending_raw is None:
            entries = []
        elif isinstance(pending_raw, dict):
            entries = [pending_raw]
        elif isinstance(pending_raw, list):
            entries = pending_raw
        else:
            orders_valid = False

    grouped: dict[str, list[dict[str, Any]]] = {}
    if orders_valid:
        extra_syms: set[str] = set()
        for item in entries:
            if not isinstance(item, dict):
                orders_valid = False
                break
            sym_raw = item.get("symbol")
            if not isinstance(sym_raw, str) or not sym_raw.strip():
                orders_valid = False
                break
            sym = sym_raw.strip()
            grouped.setdefault(sym, []).append(item)
            if sym not in symbols:
                extra_syms.add(sym)
        if orders_valid and extra_syms:
            symbols.extend(sorted(extra_syms))

    by_symbol: dict[str, dict[str, Any]] = {}
    next_by_symbol: dict[str, dict[str, Any]] = {}

    if not orders_valid:
        for sym in symbols:
            by_symbol[sym] = {
                "state": "ORDER-UNKNOWN",
                "would_have_tripped": True,
                "latched": True,
                "reason_class": "missing_input",
                "reason": (
                    f"{sym} missing or malformed orders.pending for O4 "
                    "(fail-closed ORDER-UNKNOWN)"
                ),
            }
            next_by_symbol[sym] = {
                "latched": True,
                "order_unknown": True,
                "latch_reason": "missing_input",
            }
        top_reason = "missing or malformed orders.pending for O4 (fail-closed ORDER-UNKNOWN)"
        cell = _aggregate_symbol_cell(
            "interlock-with-breaker-branch", by_symbol, top_reason
        )
        return cell, {"by_symbol": next_by_symbol}

    for sym in symbols:
        sym_entries = grouped.get(sym, [])
        prior_s = _prior_symbol_entry(prior_row_state, "O4", sym)
        prior_was_unknown = bool(prior_s.get("latched")) or bool(
            prior_s.get("order_unknown")
        )
        prior_latch_reason = prior_s.get("latch_reason")
        rearmed = _has_authorized_fund_event(
            authorized_events, "O4", sym, REARM_TOKENS
        )

        has_invalid_timeout = any(
            not isinstance(e.get("timed_out"), bool) for e in sym_entries
        )
        has_timed_out_unknown = any(
            e.get("timed_out") is True
            and not _is_definitive_terminal_status(e.get("terminal_status"))
            for e in sym_entries
        )
        has_definitive_status = any(
            _is_definitive_terminal_status(e.get("terminal_status"))
            for e in sym_entries
        )

        if has_invalid_timeout:
            state = "ORDER-UNKNOWN"
            would_have_tripped = True
            latched = True
            order_unknown = True
            reason_class = "missing_input"
            latch_reason: str | None = "missing_input"
            reason = (
                f"{sym} pending order missing boolean timed_out flag for O4 "
                "(fail-closed ORDER-UNKNOWN)"
            )
        elif has_timed_out_unknown:
            state = "ORDER-UNKNOWN"
            would_have_tripped = True
            latched = True
            order_unknown = True
            reason_class = "order_timeout_unknown"
            latch_reason = "order_timeout_unknown"
            reason = (
                f"{sym} pending order timed_out without definitive terminal_status; "
                f"ORDER-UNKNOWN in scope symbol:{sym} (query original order, do not re-send)"
            )
        elif has_definitive_status:
            state = "NORMAL"
            would_have_tripped = False
            latched = False
            order_unknown = False
            reason_class = "none"
            latch_reason = None
            reason = (
                f"{sym} definitive broker terminal_status received; ORDER-UNKNOWN cleared"
                if prior_was_unknown
                else f"pending order for {sym} has definitive terminal_status"
            )
        elif prior_was_unknown and not rearmed:
            state = "ORDER-UNKNOWN"
            would_have_tripped = True
            latched = True
            order_unknown = True
            reason_class = "latched_prior_trip"
            latch_reason = (
                prior_latch_reason
                if isinstance(prior_latch_reason, str) and prior_latch_reason
                else "order_timeout_unknown"
            )
            reason = (
                f"{sym} prior O4 ORDER-UNKNOWN persists ({latch_reason}) "
                "without definitive terminal_status or owner re-arm"
            )
        else:
            state = "NORMAL"
            would_have_tripped = False
            latched = False
            order_unknown = False
            reason_class = "none"
            latch_reason = None
            reason = (
                f"{sym} O4 re-armed via authorized_events"
                if prior_was_unknown and rearmed
                else f"no pending or timed-out order for {sym}"
            )

        by_symbol[sym] = {
            "state": state,
            "would_have_tripped": would_have_tripped,
            "latched": latched,
            "reason_class": reason_class,
            "reason": reason,
        }
        next_by_symbol[sym] = {
            "latched": latched,
            "order_unknown": order_unknown,
            "latch_reason": latch_reason,
        }

    tripped_syms = [s for s, sub in by_symbol.items() if sub["would_have_tripped"]]
    if tripped_syms:
        top_reason = f"O4 ORDER-UNKNOWN active for {', '.join(tripped_syms)}"
    elif orders["pending"] is None:
        top_reason = "orders.pending is null; no symbol in ORDER-UNKNOWN"
    else:
        top_reason = "all pending orders resolved with definitive terminal_status; no symbol in ORDER-UNKNOWN"
    cell = _aggregate_symbol_cell("interlock-with-breaker-branch", by_symbol, top_reason)
    return cell, {"by_symbol": next_by_symbol}


def eval_O4(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O4 symbol-scoped order timeout / terminal status interlock."""
    return _eval_O4_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _check_o5_order(order: Any) -> str | None:
    """Return rejection reason_class for a single O5 attempted order."""
    if not isinstance(order, dict):
        return "missing_input"
    missing_flag = False
    for _, aliases in O5_COMPLIANCE_FLAG_ALIASES:
        found = False
        val: Any = None
        for alias in aliases:
            if alias in order:
                found = True
                val = order[alias]
                break
        if not found or not isinstance(val, bool):
            missing_flag = True
        elif val is False:
            return "pretrade_limit_violation"
    if missing_flag:
        return "missing_input"
    return "unresolved_fail_closed"


def _eval_O5_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O5 pre-trade limits and UNRESOLVED-FAIL-CLOSED price collar (HALT on 3rd rejection)."""
    prior = _prior_entry(prior_row_state, "O5")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")
    prior_count = _non_neg_int(prior.get("rejections_this_session")) or 0
    rearmed = _has_authorized_event(authorized_events, "O5", REARM_TOKENS)

    pretrade = (validated_inputs or {}).get("pretrade")
    pretrade_invalid = False
    input_count = 0
    if isinstance(pretrade, dict):
        if "rejections_this_session" in pretrade:
            parsed_cnt = _non_neg_int(pretrade.get("rejections_this_session"))
            if parsed_cnt is None:
                pretrade_invalid = True
            else:
                input_count = parsed_cnt
    else:
        pretrade_invalid = True

    rejections_this_eval = 0
    eval_reasons: list[str] = []
    orders_to_check: list[Any] = []

    if not isinstance(pretrade, dict):
        rejections_this_eval = 1
        eval_reasons.append("missing_input")
    elif "attempted_order" in pretrade:
        attempted = pretrade["attempted_order"]
        if attempted is None:
            orders_to_check = []
        elif isinstance(attempted, dict):
            orders_to_check = [attempted]
        elif isinstance(attempted, list):
            orders_to_check = attempted
        else:
            rejections_this_eval = 1
            eval_reasons.append("missing_input")
    else:
        has_direct_flag = any(
            alias in pretrade
            for _, aliases in O5_COMPLIANCE_FLAG_ALIASES
            for alias in aliases
        )
        if has_direct_flag:
            orders_to_check = [pretrade]
        else:
            rejections_this_eval = 1
            eval_reasons.append("missing_input")

    for order in orders_to_check:
        rc = _check_o5_order(order)
        if rc is not None:
            rejections_this_eval += 1
            eval_reasons.append(rc)

    if pretrade_invalid and rejections_this_eval == 0:
        rejections_this_eval = 1
        eval_reasons.append("missing_input")

    if "pretrade_limit_violation" in eval_reasons:
        eval_reason = "pretrade_limit_violation"
    elif "missing_input" in eval_reasons:
        eval_reason = "missing_input"
    elif "unresolved_fail_closed" in eval_reasons:
        eval_reason = "unresolved_fail_closed"
    else:
        eval_reason = "none"

    base_count = (
        input_count if (prior_latched and rearmed) else max(prior_count, input_count)
    )
    new_count = base_count + rejections_this_eval

    if new_count >= O5_HALT_REJECTION_THRESHOLD:
        state = "HALT"
        would_have_tripped = True
        latched = True
        if rejections_this_eval > 0:
            reason_class = eval_reason
        elif prior_latched and not rearmed:
            reason_class = "latched_prior_trip"
        else:
            reason_class = "pretrade_three_rejections"
        latch_reason: str | None = (
            prior_latch_reason
            if reason_class == "latched_prior_trip"
            and isinstance(prior_latch_reason, str)
            and prior_latch_reason
            else reason_class
        )
        reason = (
            f"O5 rejections_this_session reached {new_count} (>= {O5_HALT_REJECTION_THRESHOLD}); "
            f"breaker trips to HALT and latches ({reason_class}) pending owner re-arm"
        )
    elif prior_latched and not rearmed:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "pretrade_three_rejections"
        )
        reason = f"prior O5 breaker remains latched ({latch_reason}) pending owner re-arm"
    elif rejections_this_eval > 0:
        state = "NORMAL"
        would_have_tripped = True
        latched = False
        reason_class = eval_reason
        latch_reason = None
        if eval_reason == "unresolved_fail_closed":
            reason = (
                f"O5 price collar is UNRESOLVED-FAIL-CLOSED in disposition_register; "
                f"attempted_order fails closed (single rejection: rejections_this_session "
                f"{base_count} -> {new_count} < {O5_HALT_REJECTION_THRESHOLD}, state contribution NONE)"
            )
        else:
            reason = (
                f"O5 pre-trade check failed ({eval_reason}); order rejected "
                f"(rejections_this_session {base_count} -> {new_count} < {O5_HALT_REJECTION_THRESHOLD}, "
                "state contribution NONE)"
            )
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        reason = (
            f"O5 cleared via authorized_events (rejections_this_session={new_count})"
            if prior_latched and rearmed
            else f"no attempted pre-trade order (rejections_this_session={new_count})"
        )

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "breaker on third rejection (stateful count)",
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
        "rejections_this_session": new_count,
    }
    next_state = {
        "latched": latched,
        "latch_reason": latch_reason,
        "rejections_this_session": new_count,
    }
    return cell, next_state


def eval_O5(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O5 pre-trade limits and rejection counter."""
    return _eval_O5_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_O6_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O6 breaker: policy loaded_hash != registered_hash latches HALT."""
    prior = _prior_entry(prior_row_state, "O6")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")
    rearmed = _has_authorized_event(authorized_events, "O6", REARM_TOKENS)

    policy = (validated_inputs or {}).get("policy")
    loaded_raw = policy.get("loaded_hash") if isinstance(policy, dict) else None
    registered_raw = policy.get("registered_hash") if isinstance(policy, dict) else None
    loaded = loaded_raw.strip() if isinstance(loaded_raw, str) else ""
    registered = registered_raw.strip() if isinstance(registered_raw, str) else ""

    if not loaded or not registered:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "missing_input"
        latch_reason: str | None = "missing_input"
        reason = "missing or invalid policy loaded_hash/registered_hash for O6 (fail-closed HALT)"
    elif loaded != registered:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "policy_hash_mismatch"
        latch_reason = "policy_hash_mismatch"
        reason = (
            f"policy loaded_hash ({loaded}) != registered_hash ({registered}); "
            "O6 breaker latches HALT pending owner re-arm"
        )
    elif prior_latched and not rearmed:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "policy_hash_mismatch"
        )
        reason = f"prior O6 breaker remains latched ({latch_reason}) pending owner re-arm"
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        reason = (
            "O6 re-armed via authorized_events; loaded_hash matches registered_hash"
            if prior_latched and rearmed
            else "loaded_hash matches registered_hash"
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


def eval_O6(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O6 policy hash match breaker."""
    return _eval_O6_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_O7_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O7 dead-man's switch breaker: silence_seconds > scheduled_interval_seconds latches NO-NEW-RISK."""
    prior = _prior_entry(prior_row_state, "O7")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")
    rearmed = _has_authorized_event(authorized_events, "O7", O7_REARM_TOKENS)

    runtime = (validated_inputs or {}).get("runtime")
    silence = _to_decimal(runtime.get("silence_seconds") if isinstance(runtime, dict) else None)
    interval = _to_decimal(
        runtime.get("scheduled_interval_seconds") if isinstance(runtime, dict) else None
    )

    if (
        not isinstance(runtime, dict)
        or silence is None
        or interval is None
        or silence < 0
        or interval <= 0
    ):
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "missing_input"
        latch_reason: str | None = "missing_input"
        reason = (
            "missing or invalid runtime silence_seconds/scheduled_interval_seconds for O7 "
            "(fail-closed NO-NEW-RISK)"
        )
    elif silence > interval:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "dead_mans_switch"
        latch_reason = "dead_mans_switch"
        reason = (
            f"runtime silence_seconds={silence} > scheduled_interval_seconds={interval}; "
            "O7 dead-man's switch latches NO-NEW-RISK pending human re-arm"
        )
    elif prior_latched and not rearmed:
        state = "NO-NEW-RISK"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "dead_mans_switch"
        )
        reason = f"prior O7 breaker remains latched ({latch_reason}) pending human re-arm"
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        reason = (
            f"O7 re-armed via authorized_events; runtime silence_seconds={silence} <= scheduled_interval_seconds={interval}"
            if prior_latched and rearmed
            else f"runtime silence_seconds={silence} <= scheduled_interval_seconds={interval}"
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


def eval_O7(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O7 dead-man's switch breaker."""
    return _eval_O7_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_O8_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O8 owner kill-switch: kill_switch event latches HALT until owner clear event."""
    prior = _prior_entry(prior_row_state, "O8")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")

    kill_triggered = False
    owner_cleared = False
    for event in authorized_events or ():
        if not isinstance(event, dict):
            continue
        ev_type = _norm_token(event.get("event_type"))
        ev_action = _norm_token(event.get("action"))
        targets_o8 = _event_targets_row(event, "O8")
        has_scope = _event_has_row_scope(event)
        if (targets_o8 or not has_scope) and (
            ev_type in O8_KILL_TOKENS or ev_action in O8_KILL_TOKENS
        ):
            kill_triggered = True
        if (
            targets_o8
            and (ev_type in O8_CLEAR_TOKENS or ev_action in O8_CLEAR_TOKENS)
        ) or (
            not has_scope
            and (
                ev_type in O8_UNSCOPED_CLEAR_TOKENS
                or ev_action in O8_UNSCOPED_CLEAR_TOKENS
            )
        ):
            owner_cleared = True

    if kill_triggered:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "owner_kill_switch"
        latch_reason: str | None = "owner_kill_switch"
        reason = "owner kill_switch event in authorized_events; O8 latches HALT until owner clear"
    elif prior_latched and not owner_cleared:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "owner_kill_switch"
        )
        reason = f"prior O8 kill-switch remains latched ({latch_reason}) until owner clear event"
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        reason = (
            "O8 kill-switch cleared by owner command in authorized_events"
            if prior_latched and owner_cleared
            else "no owner kill-switch event in authorized_events"
        )

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "owner",
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
    }
    return cell, {"latched": latched, "latch_reason": latch_reason}


def eval_O8(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O8 owner kill-switch."""
    return _eval_O8_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _norm_o9_field(value: Any) -> str:
    """Normalize an O9 parameter field name."""
    token = _norm_token(value)
    if token == "hwm":
        return "high_water_mark"
    return token


def _extract_o9_descriptor_fields(
    item: dict[str, Any],
) -> tuple[Any, Any]:
    """Extract (from_value, to_value) from an O9 change descriptor dict."""
    from_val = next(
        (item[k] for k in ("from_value", "from", "old_value") if k in item),
        None,
    )
    to_val = next(
        (item[k] for k in ("to_value", "to", "new_value") if k in item),
        None,
    )
    return from_val, to_val


def _append_o9_change(
    changes: list[tuple[str, Any, Any]],
    field: str,
    from_val: Any,
    to_val: Any,
) -> None:
    """Append an O9 parameter change if not already recorded."""
    for existing_field, _, existing_to in changes:
        if existing_field == field and _values_equal(existing_to, to_val):
            return
    changes.append((field, from_val, to_val))


def _o9_change_has_owner_card(
    authorized_events: list[Any] | None,
    field: str,
    from_val: Any,
    to_val: Any,
) -> str | None:
    """Return matching owner-card identifier if authorized_events authorizes the O9 change."""
    for event in authorized_events or ():
        if not isinstance(event, dict):
            continue
        ev_type = _norm_token(event.get("event_type"))
        if ev_type not in {"owner_card", "owner_change_card"}:
            continue
        if "card_id" in event:
            card_id_raw = event.get("card_id")
            if not isinstance(card_id_raw, str) or not card_id_raw.strip():
                continue
        ev_field_raw = next(
            (
                event.get(k)
                for k in ("field", "parameter", "param")
                if event.get(k) is not None
            ),
            None,
        )
        if ev_field_raw is not None:
            if _norm_o9_field(ev_field_raw) != field:
                continue
        elif _norm_token(event.get("action")) != f"{field}_change":
            continue

        ev_from = next(
            (event[k] for k in ("from_value", "from", "old_value") if k in event),
            None,
        )
        if (
            ev_from is not None
            and from_val is not None
            and not _values_equal(ev_from, from_val)
        ):
            continue

        ev_to = next(
            (event[k] for k in ("to_value", "to", "new_value") if k in event),
            None,
        )
        if (
            ev_to is not None
            and to_val is not None
            and not _values_equal(ev_to, to_val)
        ):
            continue

        card_id = event.get("card_id")
        return card_id.strip() if isinstance(card_id, str) and card_id.strip() else "owner_card"
    return None


def _eval_O9_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate O9 breaker: unauthorized tier/H/HWM/limit change latches HALT."""
    prior = _prior_entry(prior_row_state, "O9")
    prior_latched = bool(prior.get("latched"))
    prior_latch_reason = prior.get("latch_reason")
    rearmed = _has_authorized_event(authorized_events, "O9", REARM_TOKENS)

    inputs = validated_inputs or {}
    joint = inputs.get("joint")
    sizing = inputs.get("sizing")
    loss = inputs.get("loss")

    cur_tier = inputs.get("tier")
    cur_joint_cap = joint.get("joint_cap") if isinstance(joint, dict) else None
    cur_max_loss_cap = sizing.get("max_loss_cap") if isinstance(sizing, dict) else None
    cur_h = inputs["H"] if "H" in inputs else inputs.get("h")
    cur_hwm = (
        loss.get("high_water_mark")
        if isinstance(loss, dict) and "high_water_mark" in loss
        else inputs.get("high_water_mark")
    )

    prior_tier = prior.get("prior_tier")
    prior_joint_cap = prior.get("prior_joint_cap")
    prior_max_loss_cap = prior.get("prior_max_loss_cap")
    prior_h = prior["prior_H"] if "prior_H" in prior else prior.get("prior_h")
    prior_hwm = (
        prior["prior_high_water_mark"]
        if "prior_high_water_mark" in prior
        else prior.get("prior_hwm")
    )

    changes: list[tuple[str, Any, Any]] = []
    for field_name, p_val, c_val in (
        ("tier", prior_tier, cur_tier),
        ("joint_cap", prior_joint_cap, cur_joint_cap),
        ("max_loss_cap", prior_max_loss_cap, cur_max_loss_cap),
        ("h", prior_h, cur_h),
        ("high_water_mark", prior_hwm, cur_hwm),
    ):
        if p_val is not None and c_val is not None and not _values_equal(p_val, c_val):
            _append_o9_change(changes, field_name, p_val, c_val)

    malformed_desc = False
    raw_desc = inputs.get("change_descriptors")
    if raw_desc is None:
        pass
    elif isinstance(raw_desc, list):
        for item in raw_desc:
            if not isinstance(item, dict):
                malformed_desc = True
                break
            if item.get("changed") is False:
                continue
            f_raw = next(
                (
                    item.get(k)
                    for k in ("field", "parameter", "param", "name")
                    if item.get(k) is not None
                ),
                None,
            )
            f_norm = _norm_o9_field(f_raw)
            if not f_norm:
                malformed_desc = True
                break
            f_from, f_to = _extract_o9_descriptor_fields(item)
            _append_o9_change(changes, f_norm, f_from, f_to)
    elif isinstance(raw_desc, dict):
        if raw_desc:
            if any(k in raw_desc for k in ("field", "parameter", "param", "name")):
                if raw_desc.get("changed") is not False:
                    f_raw = next(
                        (
                            raw_desc.get(k)
                            for k in ("field", "parameter", "param", "name")
                            if raw_desc.get(k) is not None
                        ),
                        None,
                    )
                    f_norm = _norm_o9_field(f_raw)
                    if not f_norm:
                        malformed_desc = True
                    else:
                        f_from, f_to = _extract_o9_descriptor_fields(raw_desc)
                        _append_o9_change(changes, f_norm, f_from, f_to)
            else:
                for k, v in raw_desc.items():
                    f_norm = _norm_o9_field(k)
                    if not f_norm:
                        malformed_desc = True
                        break
                    if isinstance(v, dict):
                        if v.get("changed") is False:
                            continue
                        f_from, f_to = _extract_o9_descriptor_fields(v)
                        _append_o9_change(changes, f_norm, f_from, f_to)
                    elif v is not False and v is not None:
                        _append_o9_change(changes, f_norm, None, v)
    else:
        malformed_desc = True

    authorized_notes: list[str] = []
    unauthorized_changes: list[tuple[str, Any, Any]] = []
    for field_name, f_from, f_to in changes:
        card_id = _o9_change_has_owner_card(authorized_events, field_name, f_from, f_to)
        if card_id is not None:
            authorized_notes.append(
                f"{field_name} change {f_from} -> {f_to} authorized by owner_card {card_id}"
            )
        else:
            unauthorized_changes.append((field_name, f_from, f_to))

    if malformed_desc or unauthorized_changes:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "unauthorized_parameter_change"
        latch_reason: str | None = "unauthorized_parameter_change"
        if malformed_desc:
            reason = (
                "malformed change_descriptors without valid owner card; "
                "O9 breaker latches HALT pending owner re-arm"
            )
        else:
            desc = ", ".join(
                f"{f} ({fv} -> {tv})" for f, fv, tv in unauthorized_changes
            )
            reason = (
                f"unauthorized parameter change detected without recorded owner card: {desc}; "
                "O9 breaker latches HALT pending owner re-arm"
            )
        next_tier = prior_tier if prior_tier is not None else cur_tier
        next_joint_cap = prior_joint_cap if prior_joint_cap is not None else cur_joint_cap
        next_max_loss_cap = (
            prior_max_loss_cap if prior_max_loss_cap is not None else cur_max_loss_cap
        )
        next_h = prior_h if prior_h is not None else cur_h
        next_hwm = prior_hwm if prior_hwm is not None else cur_hwm
    elif prior_latched and not rearmed:
        state = "HALT"
        would_have_tripped = True
        latched = True
        reason_class = "latched_prior_trip"
        latch_reason = (
            prior_latch_reason
            if isinstance(prior_latch_reason, str) and prior_latch_reason
            else "unauthorized_parameter_change"
        )
        reason = f"prior O9 breaker remains latched ({latch_reason}) pending owner re-arm"
        next_tier = prior_tier if prior_tier is not None else cur_tier
        next_joint_cap = prior_joint_cap if prior_joint_cap is not None else cur_joint_cap
        next_max_loss_cap = (
            prior_max_loss_cap if prior_max_loss_cap is not None else cur_max_loss_cap
        )
        next_h = prior_h if prior_h is not None else cur_h
        next_hwm = prior_hwm if prior_hwm is not None else cur_hwm
    else:
        state = "NORMAL"
        would_have_tripped = False
        latched = False
        reason_class = "none"
        latch_reason = None
        if authorized_notes:
            reason = "; ".join(authorized_notes)
        elif prior_latched and rearmed:
            reason = "O9 re-armed via authorized_events; no unauthorized parameter changes"
        else:
            reason = "no tier, H, high-water mark, or limit changes"
        next_tier = cur_tier if cur_tier is not None else prior_tier
        next_joint_cap = cur_joint_cap if cur_joint_cap is not None else prior_joint_cap
        next_max_loss_cap = (
            cur_max_loss_cap if cur_max_loss_cap is not None else prior_max_loss_cap
        )
        next_h = cur_h if cur_h is not None else prior_h
        next_hwm = cur_hwm if cur_hwm is not None else prior_hwm

    cell = {
        "scope": "account",
        "state": state,
        "would_have_tripped": would_have_tripped,
        "kind": "breaker",
        "latched": latched,
        "reason_class": reason_class,
        "reason": reason,
    }
    next_state: dict[str, Any] = {
        "latched": latched,
        "latch_reason": latch_reason,
        "prior_tier": next_tier,
        "prior_joint_cap": next_joint_cap,
        "prior_max_loss_cap": next_max_loss_cap,
    }
    if next_h is not None:
        next_state["prior_H"] = next_h
    if next_hwm is not None:
        next_state["prior_high_water_mark"] = next_hwm
    return cell, next_state


def eval_O9(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate O9 parameter-change authorization breaker."""
    return _eval_O9_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


def _eval_J1_stateful(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate J1 joint exposure cap limit (headroom_output, state contribution NONE)."""
    inputs = validated_inputs or {}
    tier_raw = inputs.get("tier")
    tier_note = f", tier={tier_raw}" if isinstance(tier_raw, str) and tier_raw else ""
    joint = inputs.get("joint")
    joint_dict = joint if isinstance(joint, dict) else {}

    exposure_raw = joint_dict.get("joint_exposure")
    cap_raw = joint_dict.get("joint_cap")
    exposure_dec = _to_decimal(exposure_raw)
    cap_dec = _to_decimal(cap_raw)

    if (
        not isinstance(joint, dict)
        or exposure_dec is None
        or cap_dec is None
        or exposure_dec < 0
        or cap_dec < 0
    ):
        would_have_tripped = True
        reason_class = "missing_input"
        reason = "missing or invalid joint_exposure/joint_cap for J1 (fail-closed, state contribution NONE)"
        headroom_output = {
            "joint_exposure": str(exposure_dec) if exposure_dec is not None else exposure_raw,
            "joint_cap": str(cap_dec) if cap_dec is not None else cap_raw,
            "headroom": None,
            "trim_threshold_110pct": None,
            "increases_blocked": True,
            "trim_required_next_session": True,
        }
    else:
        headroom_dec = cap_dec - exposure_dec
        trim_dec = (cap_dec * J1_TRIM_MULTIPLIER_NUM) / J1_TRIM_MULTIPLIER_DEN
        trim_str = _format_decimal_clean(trim_dec)
        increases_blocked = exposure_dec > cap_dec
        trim_required = exposure_dec > trim_dec
        would_have_tripped = increases_blocked

        if trim_required:
            reason_class = "joint_cap_trim_required"
            reason = (
                f"joint_exposure {exposure_dec} > 110% of joint_cap {cap_dec} "
                f"({trim_str}{tier_note}); increases blocked and trim required at next session "
                f"(headroom={headroom_dec}, state contribution NONE)"
            )
        elif increases_blocked:
            reason_class = "joint_cap_exceeded"
            reason = (
                f"joint_exposure {exposure_dec} > joint_cap {cap_dec} "
                f"(<= 110% trim threshold {trim_str}{tier_note}); increases blocked "
                f"(headroom={headroom_dec}, state contribution NONE)"
            )
        else:
            reason_class = "none"
            reason = (
                f"joint_exposure {exposure_dec} <= joint_cap {cap_dec} "
                f"(headroom={headroom_dec}, 110% trim threshold={trim_str}{tier_note}, "
                "state contribution NONE)"
            )

        headroom_output = {
            "joint_exposure": str(exposure_dec),
            "joint_cap": str(cap_dec),
            "headroom": str(headroom_dec),
            "trim_threshold_110pct": trim_str,
            "increases_blocked": increases_blocked,
            "trim_required_next_session": trim_required,
        }

    cell = {
        "scope": "joint",
        "state": "NORMAL",
        "would_have_tripped": would_have_tripped,
        "kind": "limit",
        "latched": False,
        "reason_class": reason_class,
        "reason": reason,
        "headroom_output": headroom_output,
    }
    return cell, {"latched": False}


def eval_J1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Evaluate J1 joint exposure cap and headroom."""
    return _eval_J1_stateful(
        validated_inputs,
        prior_row_state,
        authorized_events,
        session=session,
        as_of=as_of,
    )[0]


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
    "V1": _eval_V1_stateful,
    "V2": _eval_V2_stateful,
    "V3": _eval_V3_stateful,
    "V4": _eval_V4_stateful,
    "V5": _eval_V5_stateful,
    "V6": _eval_V6_stateful,
    "V7": _eval_V7_stateful,
    "O1": _eval_O1_stateful,
    "O2": _eval_O2_stateful,
    "O3": _eval_O3_stateful,
    "O4": _eval_O4_stateful,
    "O5": _eval_O5_stateful,
    "O6": _eval_O6_stateful,
    "O7": _eval_O7_stateful,
    "O8": _eval_O8_stateful,
    "O9": _eval_O9_stateful,
    "J1": _eval_J1_stateful,
}
