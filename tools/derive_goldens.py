#!/usr/bin/env python3
"""Helper script to systematically derive golden outcomes from §4 specification.

This script encodes the trigger/action/kind/clearing semantics from BRIEF-FUSE-1 §4
and applies them to each scenario to derive expected outcomes. It does NOT run the
engine - it derives from specification text alone per §6.2 independence protocol.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def derive_L0_outcome(scenario_name: str, inputs: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Derive L0 (maximum loss cap limit) outcome per §4.3."""
    joint_exp = inputs["validated_inputs"]["joint_exposure"]
    max_cap = inputs["validated_inputs"]["max_loss_cap"]
    proposed_exp = inputs["validated_inputs"]["proposed_exposure"]

    cap_breached = joint_exp > max_cap
    increases_blocked = proposed_exp > joint_exp or cap_breached

    return {
        "state": "NORMAL",
        "would_have_tripped": False,  # L0 is a standing limit, not a trip
        "kind": "limit",
        "latched": False,
        "reason": "none",
        "outputs": {
            "cap": max_cap,
            "cap_breached": cap_breached,
            "increases_blocked": increases_blocked
        }
    }


def derive_L1_outcome(scenario_name: str, inputs: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Derive L1 (drawdown D/3 notify and lock) outcome per §4.3."""
    bankroll = inputs["validated_inputs"]["bankroll"]
    hwm = inputs["validated_inputs"]["high_water_mark"]
    D = inputs["validated_inputs"]["tier_loss_budget_D"]

    drawdown = (hwm - bankroll) / hwm if hwm > 0 else 0
    threshold = D / 3
    trips = drawdown >= threshold

    return {
        "state": "NORMAL",
        "would_have_tripped": trips,
        "kind": "interlock",
        "latched": False,
        "reason": "threshold_exceeded" if trips else "none",
        "outputs": {
            "locked_against_loosening": trips,
            "notify": trips
        }
    }


def derive_simple_no_trip(row_id: str, kind: str) -> Dict[str, Any]:
    """Derive outcome for rows that don't trip in normal conditions."""
    return {
        "state": "NORMAL",
        "would_have_tripped": False,
        "kind": kind,
        "latched": False,
        "reason": "none"
    }


def derive_unresolved_fail_closed(row_id: str, kind: str, state_contrib: str = "none") -> Dict[str, Any]:
    """Derive outcome for unresolved parameter fail-closed trips per interpretation ruling."""
    return {
        "state": state_contrib,
        "would_have_tripped": True,
        "kind": kind,
        "latched": False,
        "reason": "unresolved_fail_closed"
    }


def derive_golden_table_cell(row_id: str, scenario_name: str, scenario: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Derive expected outcome for one cell (row × scenario) per §4 specification."""
    inputs = scenario["inputs"]

    # This is a simplified derivation - full implementation would handle all 24 rows × 11 scenarios
    # For demonstration purposes, showing the derivation pattern

    if row_id == "L0":
        return derive_L0_outcome(scenario_name, inputs, tier)
    elif row_id == "L1":
        return derive_L1_outcome(scenario_name, inputs, tier)
    elif row_id in ["L2", "L3", "L4", "L6"]:
        # Loss rows that don't trip in normal/deposit/withdrawal/etc
        if scenario_name in ["normal", "deposit", "withdrawal", "restart"]:
            return derive_simple_no_trip(row_id, "breaker")
        # TODO: Implement specific trigger checks for each scenario
    elif row_id == "V5":
        # V5 always trips with unresolved tolerance per interpretation ruling
        result = derive_unresolved_fail_closed("V5", "diagnostic")
        result["outputs"] = {
            "excess_shortfall": None,
            "consecutive_sessions_beyond_tolerance": 0,
            "escalated_to_v1": False,
            "disposition": "UNRESOLVED-FAIL-CLOSED"
        }
        return result
    elif row_id == "V7":
        # V7 always trips with unresolved spread width per interpretation ruling
        return derive_unresolved_fail_closed("V7", "interlock")
    elif row_id == "O5":
        # O5 trips with unresolved collar per interpretation ruling
        result = derive_unresolved_fail_closed("O5", "breaker", "none")
        result["rejection_count"] = 1
        return result
    elif row_id == "O1":
        # O1 trips if any required input is stale or missing
        if scenario_name == "stale" or scenario_name == "missing":
            return {
                "state": "NO-NEW-RISK",
                "would_have_tripped": True,
                "kind": "interlock",
                "latched": False,
                "reason": "stale_input" if scenario_name == "stale" else "missing_input"
            }
        return derive_simple_no_trip("O1", "interlock")
    elif row_id == "O2":
        # O2 trips on holiday or half_day
        if scenario_name in ["holiday", "half_day"]:
            return {
                "state": "NORMAL",
                "would_have_tripped": True,
                "kind": "interlock",
                "latched": False,
                "reason": "market_closed"
            }
        return derive_simple_no_trip("O2", "interlock")
    elif row_id == "O9":
        # O9 trips on unauthorized tier_change
        if scenario_name == "tier_change":
            return {
                "state": "HALT",
                "would_have_tripped": True,
                "kind": "breaker",
                "latched": True,
                "reason": "unauthorized_parameter_change"
            }
        return derive_simple_no_trip("O9", "breaker")
    elif row_id == "V2":
        # V2 trips on split or reverse_split
        if scenario_name == "split":
            return {
                "state": "HALT",
                "would_have_tripped": True,
                "kind": "interlock_or_breaker",
                "latched": False,
                "reason": "pending_corporate_action",
                "fund": "TQQQ"
            }
        elif scenario_name == "reverse_split":
            return {
                "state": "HALT",
                "would_have_tripped": True,
                "kind": "interlock_or_breaker",
                "latched": False,
                "reason": "pending_corporate_action",
                "fund": "SOXL"
            }
        return derive_simple_no_trip("V2", "interlock_or_breaker")
    elif row_id == "J1":
        return derive_J1_outcome(scenario_name, inputs, tier)

    # Default: no trip
    return derive_simple_no_trip(row_id, "unknown")


def derive_J1_outcome(scenario_name: str, inputs: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Derive J1 (joint cap limit) outcome per §4.3."""
    joint_exp = inputs["validated_inputs"]["joint_exposure"]
    joint_cap = inputs["validated_inputs"]["tier_joint_cap"]

    above_cap = joint_exp > joint_cap
    above_trim = joint_exp > joint_cap * 1.1
    headroom = max(0, joint_cap - joint_exp)

    return {
        "state": "NORMAL",
        "would_have_tripped": False,  # J1 is a limit, not a trip
        "kind": "limit",
        "latched": False,
        "reason": "none",
        "outputs": {
            "headroom": headroom,
            "cap": joint_cap,
            "above_cap": above_cap,
            "above_trim_threshold": above_trim
        }
    }


def main():
    """Generate systematic derivation notes (not the full golden table).

    The full golden table is authored by hand per §6.2 independence protocol,
    deriving from §4 specification text cell by cell. This script demonstrates
    the derivation logic for key patterns.
    """
    repo_root = Path(__file__).parent.parent
    scenarios_path = repo_root / "goldens" / "scenarios.json"

    if not scenarios_path.exists():
        print(f"Error: scenarios.json not found at {scenarios_path}")
        return

    with open(scenarios_path, 'r') as f:
        scenarios_data = json.load(f)

    print("Derivation pattern demonstration for key cells:")
    print("=" * 60)

    for scenario_name in ["normal", "split", "stale", "tier_change"]:
        if scenario_name not in scenarios_data["scenarios"]:
            continue
        scenario = scenarios_data["scenarios"][scenario_name]
        print(f"\nScenario: {scenario_name}")
        print(f"Description: {scenario['description']}")

        for row_id in ["L0", "L1", "V5", "O1", "O9", "V2", "J1"]:
            outcome = derive_golden_table_cell(row_id, scenario_name, scenario, "balanced")
            print(f"  {row_id}: would_trip={outcome['would_have_tripped']}, state={outcome['state']}, reason={outcome['reason']}")


if __name__ == "__main__":
    main()
