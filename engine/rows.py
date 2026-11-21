"""Trivial skeleton row evaluators (Phase C).

Every row evaluator returns a benign skeleton cell with NO trigger logic.
"""

from __future__ import annotations

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


def eval_L0(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for L0 (standing exposure limit, static cap_output)."""
    cell = _benign_cell("account", "limit")
    sizing = (validated_inputs or {}).get("sizing") or {}
    joint = (validated_inputs or {}).get("joint") or {}
    proposed = sizing.get("proposed_exposure")
    cell["cap_output"] = {
        "exposure_cap": sizing.get("max_loss_cap"),
        "proposed_exposure": proposed,
        "joint_exposure": joint.get("joint_exposure"),
        "effective_capped_exposure": proposed,
        "cap_breached": False,
    }
    return cell


def eval_L1(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for L1."""
    return _benign_cell("account", "interlock")


def eval_L2(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for L2."""
    return _benign_cell("account", "breaker")


def eval_L3(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for L3."""
    return _benign_cell("account", "breaker")


def eval_L4(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for L4."""
    return _benign_cell("account", "breaker")


def eval_L5(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for L5."""
    return _benign_cell("account", "interlock")


def eval_L6(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    session: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Skeleton evaluator for L6."""
    return _benign_cell("account", "breaker")


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
