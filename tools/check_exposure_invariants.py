#!/usr/bin/env python3
"""G5 (F1-A09): Exposure-baseline and policy-mutation property checks.

Verifies BRIEF-FUSE-1 §4.4 rule 1 ("A trip can block, reduce or halt. No trip can
raise exposure or change a parameter") across matrix, precedence, and fail-closed
batteries.
"""

import copy
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))

from fuse_engine import evaluate


TIER_D = {'conservative': 0.15, 'balanced': 0.30, 'aggressive': 0.50}
TIER_CAP_RATIO = {'conservative': 0.40, 'balanced': 0.60, 'aggressive': 0.80}


def _finite_or_none(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(num) or math.isinf(num)) else num


def compute_no_trip_baseline_exposure(validated_inputs: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Compute the no-trip exposure baseline from validated policy caps and proposed/current exposure."""
    max_loss_cap = _finite_or_none(validated_inputs.get('max_loss_cap'))
    tier_joint_cap = _finite_or_none(validated_inputs.get('tier_joint_cap'))
    joint_exposure = _finite_or_none(validated_inputs.get('joint_exposure'))
    proposed_exposure = _finite_or_none(validated_inputs.get('proposed_exposure'))

    caps = [c for c in (max_loss_cap, tier_joint_cap) if c is not None and c >= 0.0]
    baseline_cap = min(caps) if caps else None

    target = proposed_exposure if proposed_exposure is not None else joint_exposure
    if target is None or baseline_cap is None:
        baseline_permitted = None
    else:
        baseline_permitted = min(target, baseline_cap)

    return {
        'baseline_cap': baseline_cap,
        'max_loss_cap': max_loss_cap,
        'tier_joint_cap': tier_joint_cap,
        'joint_exposure': joint_exposure,
        'proposed_exposure': proposed_exposure,
        'baseline_permitted': baseline_permitted,
    }


def compute_permitted_exposure(
    validated_inputs: Dict[str, Any],
    rows_by_ID: Dict[str, Any],
    effective_state_by_scope: Dict[str, str],
) -> float:
    """Derive maximum permitted exposure implied by an evaluated output bundle."""
    joint_exp = _finite_or_none(validated_inputs.get('joint_exposure')) or 0.0
    proposed_exp = _finite_or_none(validated_inputs.get('proposed_exposure'))
    target = proposed_exp if proposed_exp is not None else joint_exp

    l0 = rows_by_ID['L0']
    j1 = rows_by_ID['J1']
    l0_cap = _finite_or_none(l0.get('outputs', {}).get('cap'))
    j1_cap = _finite_or_none(j1.get('outputs', {}).get('cap'))

    if effective_state_by_scope.get('account') == 'HALT' or effective_state_by_scope.get('joint') == 'HALT':
        return 0.0

    # Missing required cap evidence must fail closed to 0 permitted new exposure
    if l0_cap is None or l0.get('reason') == 'missing_input':
        return 0.0

    effective_cap = l0_cap if j1_cap is None else min(l0_cap, j1_cap)

    # Account DE-RISK forces defensive reduction
    if effective_state_by_scope.get('account') == 'DE-RISK':
        return 0.0

    # Any NO-NEW-RISK, limit block, or order suppression forbids raising exposure above current
    increases_blocked = (
        effective_state_by_scope.get('account') == 'NO-NEW-RISK'
        or effective_state_by_scope.get('joint') in ('NO-NEW-RISK', 'DE-RISK', 'HALT')
        or bool(l0.get('outputs', {}).get('increases_blocked'))
        or bool(j1.get('outputs', {}).get('above_cap'))
        or bool(rows_by_ID['O2'].get('would_have_tripped'))
        or bool(rows_by_ID['V7'].get('would_have_tripped'))
        or bool(rows_by_ID['O5'].get('would_have_tripped'))
    )
    if increases_blocked:
        return min(joint_exp, effective_cap)

    return min(target, effective_cap)


def check_bundle_against_baseline(
    label: str,
    validated_inputs: Dict[str, Any],
    rows_by_ID: Dict[str, Any],
    effective_state_by_scope: Dict[str, str],
) -> List[str]:
    """Verify permitted exposure and caps never exceed the no-trip baseline (§4.4 rule 1)."""
    errors: List[str] = []
    baseline = compute_no_trip_baseline_exposure(validated_inputs)
    permitted = compute_permitted_exposure(validated_inputs, rows_by_ID, effective_state_by_scope)

    l0_cap = _finite_or_none(rows_by_ID['L0'].get('outputs', {}).get('cap'))
    j1_cap = _finite_or_none(rows_by_ID['J1'].get('outputs', {}).get('cap'))

    if baseline['max_loss_cap'] is not None and l0_cap is not None and l0_cap > baseline['max_loss_cap']:
        errors.append(f"{label}: L0 cap {l0_cap} exceeds policy max_loss_cap {baseline['max_loss_cap']}")
    if baseline['tier_joint_cap'] is not None and j1_cap is not None and j1_cap > baseline['tier_joint_cap']:
        errors.append(f"{label}: J1 cap {j1_cap} exceeds policy tier_joint_cap {baseline['tier_joint_cap']}")

    if baseline['baseline_permitted'] is not None and permitted > baseline['baseline_permitted']:
        errors.append(
            f"{label}: permitted exposure {permitted} exceeds no-trip baseline {baseline['baseline_permitted']}"
        )

    any_trip = any(r.get('would_have_tripped') for r in rows_by_ID.values())
    if any_trip and baseline['joint_exposure'] is not None and permitted > baseline['joint_exposure']:
        # Unless only diagnostic V5/V6 tripped without blocking
        blocking_trip = any(
            r.get('would_have_tripped') and r.get('kind') != 'diagnostic'
            for r in rows_by_ID.values()
        )
        if blocking_trip:
            errors.append(
                f"{label}: blocking trip allowed exposure {permitted} > current {baseline['joint_exposure']}"
            )

    if effective_state_by_scope.get('account') == 'HALT':
        for scope, state in effective_state_by_scope.items():
            if state != 'HALT':
                errors.append(f"{label}: account HALT did not dominate {scope} ({state})")

    return errors


def check_policy_mutation_monotonicity(
    label: str,
    validated_inputs: Dict[str, Any],
    session: str = '2026-01-05',
    prior_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Verify policy tightening never raises permitted exposure and policy-hash tampering halts."""
    errors: List[str] = []
    before_inputs = copy.deepcopy(validated_inputs)
    rows_b, eff_b, _ = evaluate(
        'fuse-eval-spec/v1', 'check-hash', 'policy-v1', session, f'{session}T16:00:00Z',
        'shadow', before_inputs, prior_state or {}, []
    )
    if before_inputs != validated_inputs:
        errors.append(f"{label}: evaluate() mutated caller validated_inputs")

    perm_before = compute_permitted_exposure(validated_inputs, rows_b, eff_b)

    # Mutation 1: Tighten caps by 50% (and move tier toward conservative if applicable)
    tight_inputs = copy.deepcopy(validated_inputs)
    if _finite_or_none(tight_inputs.get('max_loss_cap')) is not None:
        tight_inputs['max_loss_cap'] = float(tight_inputs['max_loss_cap']) * 0.5
    if _finite_or_none(tight_inputs.get('tier_joint_cap')) is not None:
        tight_inputs['tier_joint_cap'] = float(tight_inputs['tier_joint_cap']) * 0.5
    tight_inputs['tier'] = 'conservative'
    tight_inputs['tier_loss_budget_D'] = 0.15

    rows_t, eff_t, _ = evaluate(
        'fuse-eval-spec/v1', 'check-hash', 'policy-v1', session, f'{session}T16:00:00Z',
        'shadow', tight_inputs, prior_state or {}, []
    )
    perm_after = compute_permitted_exposure(tight_inputs, rows_t, eff_t)
    if perm_after > perm_before:
        errors.append(f"{label}: tightening policy increased permitted exposure ({perm_before} -> {perm_after})")

    # Mutation 2: Policy hash tampering must trigger O6 HALT and 0 permitted exposure
    tamper_inputs = copy.deepcopy(validated_inputs)
    tamper_inputs['loaded_policy_hash'] = 'tampered_hash_mismatch'
    tamper_inputs['registered_policy_hash'] = 'registered_policy_hash_v1'
    rows_h, eff_h, _ = evaluate(
        'fuse-eval-spec/v1', 'check-hash', 'policy-v1', session, f'{session}T16:00:00Z',
        'shadow', tamper_inputs, prior_state or {}, []
    )
    if rows_h['O6']['state'] != 'HALT' or not rows_h['O6']['latched']:
        errors.append(f"{label}: policy hash mismatch did not latch O6 HALT")
    if compute_permitted_exposure(tamper_inputs, rows_h, eff_h) != 0.0:
        errors.append(f"{label}: policy hash mismatch permitted non-zero exposure")

    return errors


def run_all_batteries() -> Tuple[int, List[str]]:
    """Run property checks across matrix (base + tier + successor), precedence, and fail-closed."""
    scenarios = json.loads((REPO_ROOT / 'goldens' / 'scenarios.json').read_text(encoding='utf-8'))['scenarios']
    suc_cases = json.loads((REPO_ROOT / 'goldens' / 'successor-cases.json').read_text(encoding='utf-8'))['cases']

    checked = 0
    errors: List[str] = []

    # 1. Base scenarios (11)
    for sc_name, sc in scenarios.items():
        inp = sc['inputs']
        vi = copy.deepcopy(inp['validated_inputs'])
        rows, eff, _ = evaluate(
            inp['spec_version'], 'check-hash', inp['policy_hash'],
            inp['session'], inp['as_of'], inp['mode'],
            vi, inp.get('prior_row_state') or {}, inp.get('authorized_events') or []
        )
        checked += 1
        errors.extend(check_bundle_against_baseline(f"base.{sc_name}", vi, rows, eff))
        errors.extend(check_policy_mutation_monotonicity(f"policy.{sc_name}", vi, inp['session'], inp.get('prior_row_state')))

    # 2. Tier variants (11 scenarios × 2 alternate tiers = 22 full bundles covering 132 tier cells)
    for sc_name, sc in scenarios.items():
        inp = sc['inputs']
        base_tier = inp['validated_inputs']['tier']
        for tier in ('conservative', 'balanced', 'aggressive'):
            if tier == base_tier:
                continue
            vi = copy.deepcopy(inp['validated_inputs'])
            vi['tier'] = tier
            vi['tier_loss_budget_D'] = TIER_D[tier]
            cap = round(vi['bankroll'] * TIER_CAP_RATIO[tier], 2)
            vi['max_loss_cap'] = cap
            vi['tier_joint_cap'] = cap
            rows, eff, _ = evaluate(
                inp['spec_version'], 'check-hash', inp['policy_hash'],
                inp['session'], inp['as_of'], inp['mode'],
                vi, inp.get('prior_row_state') or {}, inp.get('authorized_events') or []
            )
            checked += 1
            errors.extend(check_bundle_against_baseline(f"tier.{sc_name}.{tier}", vi, rows, eff))

    # 3. Successor cases (all executable steps)
    for cid, case in suc_cases.items():
        for step in case.get('steps', []):
            if 'inputs' not in step:
                continue
            sinp = step['inputs']
            vi = copy.deepcopy(sinp['validated_inputs'])
            rows, eff, _ = evaluate(
                'fuse-eval-spec/v1', 'check-hash', 'test_policy_hash',
                sinp['session'], sinp.get('as_of', f"{sinp['session']}T16:00:00Z"),
                'shadow', vi, sinp.get('prior_row_state') or {}, sinp.get('authorized_events') or []
            )
            checked += 1
            errors.extend(check_bundle_against_baseline(f"suc.{cid}.{step['step']}", vi, rows, eff))

    # 4. Precedence & fail-closed controls
    normal_vi = copy.deepcopy(scenarios['normal']['inputs']['validated_inputs'])
    controls: List[Tuple[str, Dict[str, Any]]] = []
    v_o4 = copy.deepcopy(normal_vi)
    v_o4['pending_orders'] = {'TQQQ': {'order_id': 'o1', 'status': 'pending', 'timeout': True}}
    controls.append(('prec.o4_timeout', v_o4))
    v_mix = copy.deepcopy(v_o4)
    v_mix['broker_cash'] = 95000.0
    controls.append(('prec.o3_halt_dominance', v_mix))
    v_nan = copy.deepcopy(normal_vi)
    v_nan['funds']['TQQQ']['forecast_volatility'] = float('nan')
    controls.append(('fc.v4_nan', v_nan))
    v_ret = copy.deepcopy(normal_vi)
    v_ret['funds']['TQQQ'].pop('fund_return')
    controls.append(('fc.v1_missing_return', v_ret))
    v_4f = copy.deepcopy(normal_vi)
    for k in ('bankroll', 'high_water_mark', 'joint_exposure', 'max_loss_cap'):
        v_4f.pop(k)
    controls.append(('fc.o1_4field_missing', v_4f))

    for label, vi in controls:
        rows, eff, _ = evaluate(
            'fuse-eval-spec/v1', 'check-hash', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, []
        )
        checked += 1
        errors.extend(check_bundle_against_baseline(label, vi, rows, eff))
        errors.extend(check_policy_mutation_monotonicity(label, vi))

    return checked, errors


def main() -> int:
    checked, errors = run_all_batteries()
    if errors:
        print(f"FAIL: {len(errors)} exposure/policy invariant violation(s) across {checked} bundles:")
        for err in errors:
            print(f"  {err}")
        return 1
    print(f"PASS: All {checked} bundles satisfy exposure-baseline and policy-mutation invariants.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
