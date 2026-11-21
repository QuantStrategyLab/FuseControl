"""Pure pinned evaluator entrypoint (L0-L6 implemented; V, O, J1 skeleton)."""

from __future__ import annotations

import copy
from typing import Any

from engine.rows import DEFAULT_FUNDS, ROW_EVALUATORS, ROW_IDS, ROW_STATE_EVALUATORS

ENFORCEMENT_MODE = "shadow_would_have_tripped"
LOSS_BREAKERS_ARMED = False
KELLY_APPLIED = False
ORDERS_PLACED = 0
OBSERVATION_CLASS = "synthetic"

ALLOWED_MODES = frozenset({"shadow_would_have_tripped", "shadow"})

STATE_PRECEDENCE: dict[str, int] = {
    "NORMAL": 0,
    "NO-NEW-RISK": 1,
    "DE-RISK": 2,
    "ORDER-UNKNOWN": 3,
    "HALT": 4,
}


class EvaluationResult(tuple):
    """3-tuple (rows_by_ID, effective_state_by_scope, next_row_state) with shadow envelope metadata."""

    def __new__(
        cls,
        rows_by_ID: dict[str, dict[str, Any]],
        effective_state_by_scope: dict[str, str],
        next_row_state: Any,
        *,
        spec_version: str,
        engine_hash: str,
        policy_hash: str,
        session: Any,
        as_of: Any,
        mode: str,
    ) -> "EvaluationResult":
        obj = super().__new__(
            cls, (rows_by_ID, effective_state_by_scope, next_row_state)
        )
        obj.spec_version = spec_version
        obj.engine_hash = engine_hash
        obj.policy_hash = policy_hash
        obj.session = session
        obj.as_of = as_of
        obj.mode = mode
        obj.enforcement_mode = ENFORCEMENT_MODE
        obj.loss_breakers_armed = LOSS_BREAKERS_ARMED
        obj.kelly_applied = KELLY_APPLIED
        obj.orders_placed = ORDERS_PLACED
        obj.observation_class = OBSERVATION_CLASS
        return obj

    def to_envelope(self) -> dict[str, Any]:
        """Wrap evaluation outputs with shadow-mode metadata."""
        return wrap_outputs(
            self[0],
            self[1],
            self[2],
            spec_version=self.spec_version,
            engine_hash=self.engine_hash,
            policy_hash=self.policy_hash,
            session=self.session,
            as_of=self.as_of,
        )


def wrap_outputs(
    rows_by_ID: dict[str, dict[str, Any]],
    effective_state_by_scope: dict[str, str],
    next_row_state: Any,
    *,
    spec_version: str,
    engine_hash: str,
    policy_hash: str,
    session: Any,
    as_of: Any,
) -> dict[str, Any]:
    """Return full output envelope asserting shadow defaults."""
    return {
        "spec_version": spec_version,
        "engine_hash": engine_hash,
        "code_hash": engine_hash,
        "policy_hash": policy_hash,
        "session": session,
        "as_of": as_of,
        "observation_class": OBSERVATION_CLASS,
        "enforcement_mode": ENFORCEMENT_MODE,
        "loss_breakers_armed": LOSS_BREAKERS_ARMED,
        "kelly_applied": KELLY_APPLIED,
        "orders_placed": ORDERS_PLACED,
        "rows_by_ID": rows_by_ID,
        "effective_state_by_scope": effective_state_by_scope,
        "next_row_state": next_row_state,
    }


def _pick_higher_state(current: str, candidate: str) -> str:
    """Return the higher-precedence state between current and candidate."""
    if candidate not in STATE_PRECEDENCE:
        raise ValueError(f"Unknown control state: {candidate!r}")
    if STATE_PRECEDENCE[candidate] > STATE_PRECEDENCE[current]:
        return candidate
    return current


def _resolve_effective_states(
    rows_by_ID: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Resolve effective state independently per scope from row outputs."""
    effective: dict[str, str] = {
        "account": "NORMAL",
        **{f"fund:{fund}": "NORMAL" for fund in DEFAULT_FUNDS},
        **{f"symbol:{sym}": "NORMAL" for sym in DEFAULT_FUNDS},
        "joint": "NORMAL",
    }
    for cell in rows_by_ID.values():
        scope = cell["scope"]
        if scope in ("account", "joint"):
            effective[scope] = _pick_higher_state(effective[scope], cell["state"])
        elif scope == "fund":
            for fund, sub in (cell.get("by_fund") or {}).items():
                key = f"fund:{fund}"
                effective[key] = _pick_higher_state(
                    effective.get(key, "NORMAL"), sub["state"]
                )
        elif scope == "symbol":
            for sym, sub in (cell.get("by_symbol") or {}).items():
                key = f"symbol:{sym}"
                effective[key] = _pick_higher_state(
                    effective.get(key, "NORMAL"), sub["state"]
                )
    return effective


def evaluate(
    spec_version: str,
    engine_hash: str,
    policy_hash: str,
    session: Any,
    as_of: Any,
    mode: str,
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
) -> EvaluationResult:
    """Evaluate all 24 fuse rows behind the pinned C-FUSE-EVAL signature."""
    if mode not in ALLOWED_MODES:
        raise ValueError(
            f"Unsupported mode {mode!r}; expected one of {sorted(ALLOWED_MODES)}"
        )

    rows_by_ID: dict[str, dict[str, Any]] = {}
    next_row_state: dict[str, Any] = (
        copy.deepcopy(prior_row_state)
        if isinstance(prior_row_state, dict)
        else {}
    )
    for row_id in ROW_IDS:
        if row_id in ROW_STATE_EVALUATORS:
            cell, row_next = ROW_STATE_EVALUATORS[row_id](
                validated_inputs,
                prior_row_state,
                authorized_events,
                session=session,
                as_of=as_of,
            )
            rows_by_ID[row_id] = cell
            next_row_state[row_id] = row_next
        else:
            rows_by_ID[row_id] = ROW_EVALUATORS[row_id](
                validated_inputs,
                prior_row_state,
                authorized_events,
                session=session,
                as_of=as_of,
            )
    effective_state_by_scope = _resolve_effective_states(rows_by_ID)

    return EvaluationResult(
        rows_by_ID,
        effective_state_by_scope,
        next_row_state,
        spec_version=spec_version,
        engine_hash=engine_hash,
        policy_hash=policy_hash,
        session=session,
        as_of=as_of,
        mode=mode,
    )
