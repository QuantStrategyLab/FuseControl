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
sys.path.insert(0, str(Path(__file__).parent))

from fuse_engine import evaluate
from run_matrix import (
    _extract_summary_sessions,
    build_suc11_probes,
    engine_canonical_json,
    get_suc08_gap_sessions,
)


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


def _v7_blocks_target(
    validated_inputs: Dict[str, Any],
    rows_by_ID: Dict[str, Any],
    target_sym: Optional[str],
) -> bool:
    """Return True iff V7 order suppression applies to target_sym (or whole portfolio if unset)."""
    v7 = rows_by_ID.get('V7', {})
    if not v7.get('would_have_tripped'):
        return False
    if not target_sym:
        return True
    funds = validated_inputs.get('funds')
    if not isinstance(funds, dict) or target_sym not in funds or not isinstance(funds[target_sym], dict):
        return True
    fdata = funds[target_sym]
    raw_thresh = fdata['v7_spread_width'] if 'v7_spread_width' in fdata else validated_inputs.get('v7_spread_width')
    thresh = _finite_or_none(raw_thresh)
    qs = _finite_or_none(fdata.get('quote_staleness'))
    sw = _finite_or_none(fdata.get('spread_width'))
    tp = fdata.get('trading_pause')
    st = fdata.get('session_time')
    if (
        raw_thresh in (None, 'unresolved') or thresh is None or thresh < 0.0 or
        qs is None or qs < 0.0 or qs > 1.0 or
        sw is None or sw < 0.0 or sw > thresh or
        not isinstance(tp, bool) or tp or st != 'regular'
    ):
        return True
    return False


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

    # Account or all-fund DE-RISK/HALT forces defensive reduction / stop
    fund_scopes = [k for k in effective_state_by_scope if k.startswith('fund:')]
    symbol_scopes = [k for k in effective_state_by_scope if k.startswith('symbol:')]
    if effective_state_by_scope.get('account') == 'DE-RISK':
        return 0.0
    if fund_scopes and all(effective_state_by_scope[k] in ('HALT', 'DE-RISK') for k in fund_scopes):
        return 0.0

    # Any NO-NEW-RISK, all-fund/symbol restriction, targeted-fund restriction, limit block, or order suppression forbids raising exposure
    all_funds_restricted = bool(fund_scopes) and all(
        effective_state_by_scope[k] in ('NO-NEW-RISK', 'DE-RISK', 'HALT', 'ORDER-UNKNOWN')
        for k in fund_scopes
    )
    all_symbols_restricted = bool(symbol_scopes) and all(
        effective_state_by_scope[k] in ('NO-NEW-RISK', 'DE-RISK', 'HALT', 'ORDER-UNKNOWN')
        for k in symbol_scopes
    )
    target_sym = (
        validated_inputs.get('target_fund')
        or validated_inputs.get('proposed_fund')
        or validated_inputs.get('o5_symbol')
        or validated_inputs.get('symbol')
    )
    target_blocked = bool(target_sym) and (
        effective_state_by_scope.get(f'fund:{target_sym}', 'NORMAL') != 'NORMAL'
        or effective_state_by_scope.get(f'symbol:{target_sym}', 'NORMAL') != 'NORMAL'
    )
    increases_blocked = (
        effective_state_by_scope.get('account') == 'NO-NEW-RISK'
        or effective_state_by_scope.get('joint') in ('NO-NEW-RISK', 'DE-RISK', 'HALT')
        or all_funds_restricted
        or all_symbols_restricted
        or target_blocked
        or bool(l0.get('outputs', {}).get('increases_blocked'))
        or bool(j1.get('outputs', {}).get('above_cap'))
        or bool(rows_by_ID['O2'].get('would_have_tripped'))
        or _v7_blocks_target(validated_inputs, rows_by_ID, target_sym)
        or bool(rows_by_ID['O5'].get('would_have_tripped'))
    )
    if increases_blocked:
        return min(target, joint_exp, effective_cap)

    return min(target, effective_cap)


def check_bundle_against_baseline(
    label: str,
    validated_inputs: Dict[str, Any],
    rows_by_ID: Dict[str, Any],
    effective_state_by_scope: Dict[str, str],
) -> List[str]:
    """Verify permitted exposure, caps, and J1 headroom never exceed policy/arithmetic invariants (§4.4 rule 1)."""
    errors: List[str] = []
    baseline = compute_no_trip_baseline_exposure(validated_inputs)
    permitted = compute_permitted_exposure(validated_inputs, rows_by_ID, effective_state_by_scope)

    l0_cap = _finite_or_none(rows_by_ID['L0'].get('outputs', {}).get('cap'))
    j1_outputs = rows_by_ID['J1'].get('outputs', {})
    j1_cap = _finite_or_none(j1_outputs.get('cap'))
    j1_headroom = _finite_or_none(j1_outputs.get('headroom'))

    if l0_cap is None and rows_by_ID['L0'].get('reason') != 'missing_input':
        errors.append(f"{label}: L0.outputs.cap missing or non-finite")
    if j1_cap is None:
        errors.append(f"{label}: J1.outputs.cap missing or non-finite")

    if baseline['max_loss_cap'] is not None and l0_cap is not None and l0_cap > baseline['max_loss_cap']:
        errors.append(f"{label}: L0 cap {l0_cap} exceeds policy max_loss_cap {baseline['max_loss_cap']}")
    if baseline['tier_joint_cap'] is not None and j1_cap is not None and j1_cap > baseline['tier_joint_cap']:
        errors.append(f"{label}: J1 cap {j1_cap} exceeds policy tier_joint_cap {baseline['tier_joint_cap']}")

    # Exact J1.outputs.headroom arithmetic check (A09)
    if j1_headroom is None:
        errors.append(f"{label}: J1.outputs.headroom missing or non-finite")
    elif (
        baseline['tier_joint_cap'] is None or
        baseline['joint_exposure'] is None or
        baseline['tier_joint_cap'] < 0.0 or
        baseline['joint_exposure'] < 0.0
    ):
        if abs(j1_headroom - 0.0) > 1e-9:
            errors.append(f"{label}: J1 headroom {j1_headroom} != 0.0 on missing/negative inputs")
    else:
        raw_headroom = baseline['tier_joint_cap'] - baseline['joint_exposure']
        if validated_inputs.get('tier_change_event') and baseline['joint_exposure'] > baseline['tier_joint_cap']:
            expected_headroom = max(0.0, raw_headroom)
        else:
            expected_headroom = raw_headroom
        if abs(j1_headroom - expected_headroom) > 1e-9:
            errors.append(
                f"{label}: J1 headroom {j1_headroom} != expected {expected_headroom} "
                f"(cap={baseline['tier_joint_cap']}, exp={baseline['joint_exposure']})"
            )
        if j1_headroom > max(0.0, raw_headroom) + 1e-9:
            errors.append(
                f"{label}: J1 headroom {j1_headroom} exceeds max allowed {max(0.0, raw_headroom)}"
            )

    if baseline['baseline_permitted'] is not None and baseline['baseline_permitted'] >= 0.0 and permitted > baseline['baseline_permitted']:
        errors.append(
            f"{label}: permitted exposure {permitted} exceeds no-trip baseline {baseline['baseline_permitted']}"
        )

    # Check portfolio-wide / target-scope increase blocking only when the bundle actually blocks increases there
    fund_scopes = [k for k in effective_state_by_scope if k.startswith('fund:')]
    symbol_scopes = [k for k in effective_state_by_scope if k.startswith('symbol:')]
    all_funds_restricted = bool(fund_scopes) and all(
        effective_state_by_scope[k] in ('NO-NEW-RISK', 'DE-RISK', 'HALT', 'ORDER-UNKNOWN')
        for k in fund_scopes
    )
    all_symbols_restricted = bool(symbol_scopes) and all(
        effective_state_by_scope[k] in ('NO-NEW-RISK', 'DE-RISK', 'HALT', 'ORDER-UNKNOWN')
        for k in symbol_scopes
    )
    target_sym = (
        validated_inputs.get('target_fund')
        or validated_inputs.get('proposed_fund')
        or validated_inputs.get('o5_symbol')
        or validated_inputs.get('symbol')
    )
    target_restricted = bool(target_sym) and (
        effective_state_by_scope.get(f'fund:{target_sym}', 'NORMAL') != 'NORMAL'
        or effective_state_by_scope.get(f'symbol:{target_sym}', 'NORMAL') != 'NORMAL'
    )
    increase_must_be_blocked = (
        effective_state_by_scope.get('account') != 'NORMAL'
        or effective_state_by_scope.get('joint') != 'NORMAL'
        or all_funds_restricted
        or all_symbols_restricted
        or target_restricted
        or bool(rows_by_ID['L0'].get('outputs', {}).get('increases_blocked'))
        or bool(rows_by_ID['J1'].get('outputs', {}).get('above_cap'))
        or bool(rows_by_ID['O2'].get('would_have_tripped'))
        or bool(rows_by_ID['O5'].get('would_have_tripped'))
        or _v7_blocks_target(validated_inputs, rows_by_ID, target_sym)
    )
    if increase_must_be_blocked and baseline['joint_exposure'] is not None and baseline['joint_exposure'] >= 0.0 and permitted > baseline['joint_exposure']:
        errors.append(
            f"{label}: blocking trip allowed exposure {permitted} > current {baseline['joint_exposure']}"
        )

    if effective_state_by_scope.get('account') == 'HALT':
        for scope, state in effective_state_by_scope.items():
            if state != 'HALT':
                errors.append(f"{label}: account HALT did not dominate {scope} ({state})")

    return errors


def _deep_equal(a: Any, b: Any) -> bool:
    """Structural equality treating two NaN floats as equal and enforcing exact types."""
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return (math.isnan(a) and math.isnan(b)) or a == b
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_deep_equal(x, y) for x, y in zip(a, b))
    return a == b


def _evaluate_checked(
    label: str,
    spec_version: str,
    engine_hash: str,
    policy_hash: str,
    session: str,
    as_of: str,
    mode: str,
    validated_inputs: Dict[str, Any],
    prior_row_state: Optional[Dict[str, Any]],
    authorized_events: Optional[Any],
    check_baseline: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, Any], Dict[str, Any], List[str]]:
    """Snapshot caller policy/inputs BEFORE evaluate(), check immutability and baseline."""
    vi_snapshot = copy.deepcopy(validated_inputs)
    prior_norm = prior_row_state if prior_row_state is not None else {}
    events_norm = authorized_events if authorized_events is not None else []
    prior_snapshot = copy.deepcopy(prior_norm)
    events_snapshot = copy.deepcopy(events_norm)

    rows, eff, next_state = evaluate(
        spec_version,
        engine_hash,
        policy_hash,
        session,
        as_of,
        mode,
        validated_inputs,
        prior_row_state,
        authorized_events,
    )

    errors: List[str] = []
    if not _deep_equal(validated_inputs, vi_snapshot):
        errors.append(f"{label}: caller validated_inputs mutated during evaluate()")
    if not _deep_equal(prior_norm, prior_snapshot):
        errors.append(f"{label}: caller prior_row_state mutated during evaluate()")
    if not _deep_equal(events_norm, events_snapshot):
        errors.append(f"{label}: caller authorized_events mutated during evaluate()")

    if (
        'o5_collar' in vi_snapshot
        and vi_snapshot['o5_collar'] in (None, 'unresolved')
        and not prior_snapshot.get('O5', {}).get('latched')
        and not rows['O5'].get('would_have_tripped')
    ):
        errors.append(f"{label}: unresolved o5_collar did not trip O5")

    if check_baseline:
        errors.extend(check_bundle_against_baseline(label, vi_snapshot, rows, eff))

    return rows, eff, next_state, vi_snapshot, errors


def check_policy_mutation_monotonicity(
    label: str,
    validated_inputs: Dict[str, Any],
    session: str = '2026-01-05',
    prior_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Verify policy tightening never raises permitted exposure and policy-hash tampering halts."""
    errors: List[str] = []
    before_inputs = copy.deepcopy(validated_inputs)
    rows_b, eff_b, _, vi_snap_b, eval_errs_b = _evaluate_checked(
        f"{label}.baseline",
        'fuse-eval-spec/v1', 'check-hash', 'policy-v1', session, f'{session}T16:00:00Z',
        'shadow', before_inputs, copy.deepcopy(prior_state or {}), [], check_baseline=False
    )
    errors.extend(eval_errs_b)
    perm_before = compute_permitted_exposure(vi_snap_b, rows_b, eff_b)

    # Mutation 1: Tighten caps by 50% (and move tier toward conservative if applicable)
    tight_inputs = copy.deepcopy(vi_snap_b)
    if _finite_or_none(tight_inputs.get('max_loss_cap')) is not None:
        tight_inputs['max_loss_cap'] = float(tight_inputs['max_loss_cap']) * 0.5
    if _finite_or_none(tight_inputs.get('tier_joint_cap')) is not None:
        tight_inputs['tier_joint_cap'] = float(tight_inputs['tier_joint_cap']) * 0.5
    tight_inputs['tier'] = 'conservative'
    tight_inputs['tier_loss_budget_D'] = 0.15

    rows_t, eff_t, _, tight_snap, eval_errs_t = _evaluate_checked(
        f"{label}.tighten",
        'fuse-eval-spec/v1', 'check-hash', 'policy-v1', session, f'{session}T16:00:00Z',
        'shadow', tight_inputs, copy.deepcopy(prior_state or {}), [], check_baseline=True
    )
    errors.extend(eval_errs_t)
    perm_after = compute_permitted_exposure(tight_snap, rows_t, eff_t)
    if perm_after > perm_before:
        errors.append(f"{label}: tightening policy increased permitted exposure ({perm_before} -> {perm_after})")

    # Mutation 2: Policy hash tampering must trigger O6 HALT and 0 permitted exposure
    tamper_inputs = copy.deepcopy(vi_snap_b)
    tamper_inputs['loaded_policy_hash'] = 'tampered_hash_mismatch'
    tamper_inputs['registered_policy_hash'] = 'registered_policy_hash_v1'
    rows_h, eff_h, _, tamper_snap, eval_errs_h = _evaluate_checked(
        f"{label}.policy_tamper",
        'fuse-eval-spec/v1', 'check-hash', 'policy-v1', session, f'{session}T16:00:00Z',
        'shadow', tamper_inputs, copy.deepcopy(prior_state or {}), [], check_baseline=True
    )
    errors.extend(eval_errs_h)
    if rows_h['O6']['state'] != 'HALT' or not rows_h['O6']['latched']:
        errors.append(f"{label}: policy hash mismatch did not latch O6 HALT")
    if compute_permitted_exposure(tamper_snap, rows_h, eff_h) != 0.0:
        errors.append(f"{label}: policy hash mismatch permitted non-zero exposure")

    return errors


def run_all_batteries() -> Tuple[int, List[str]]:
    """Run property checks across matrix (base + tier + continuous successor), precedence, and fail-closed."""
    scenarios = json.loads((REPO_ROOT / 'goldens' / 'scenarios.json').read_text(encoding='utf-8'))['scenarios']
    suc_cases = json.loads((REPO_ROOT / 'goldens' / 'successor-cases.json').read_text(encoding='utf-8'))['cases']

    checked = 0
    errors: List[str] = []

    # 1. Base scenarios (11)
    for sc_name, sc in scenarios.items():
        inp = sc['inputs']
        vi = copy.deepcopy(inp['validated_inputs'])
        prior = copy.deepcopy(inp.get('prior_row_state') or {})
        events = copy.deepcopy(inp.get('authorized_events') or [])
        _, _, _, vi_snap, eval_errs = _evaluate_checked(
            f"base.{sc_name}",
            inp['spec_version'], 'check-hash', inp['policy_hash'],
            inp['session'], inp['as_of'], inp['mode'],
            vi, prior, events, check_baseline=True
        )
        checked += 1
        errors.extend(eval_errs)
        errors.extend(check_policy_mutation_monotonicity(f"policy.{sc_name}", vi_snap, inp['session'], prior))

    # 2. Tier variants (11 scenarios × 2 alternate tiers = 22 full bundles)
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
            prior = copy.deepcopy(inp.get('prior_row_state') or {})
            events = copy.deepcopy(inp.get('authorized_events') or [])
            _, _, _, _, eval_errs = _evaluate_checked(
                f"tier.{sc_name}.{tier}",
                inp['spec_version'], 'check-hash', inp['policy_hash'],
                inp['session'], inp['as_of'], inp['mode'],
                vi, prior, events, check_baseline=True
            )
            checked += 1
            errors.extend(eval_errs)

    # 3. Successor cases (continuous real multi-step chains incl. SUC-06/5, SUC-07/3, SUC-08 70 sessions, SUC-11)
    for cid, case in suc_cases.items():
        if cid == 'SUC-11' or (case.get('phase_3_implementation') and not case.get('steps')):
            common_vi, combined_prior, two_fund_vi = build_suc11_probes()
            for sub_label, sub_vi, sub_prior in [
                ('suc.SUC-11.single', common_vi, combined_prior),
                ('suc.SUC-11.two_fund', two_fund_vi, {}),
            ]:
                _, _, _, _, eval_errs = _evaluate_checked(
                    sub_label,
                    'fuse-eval-spec/v1', 'check-hash', 'synthetic-policy',
                    '2026-01-06', '2026-01-06T16:00:00Z', 'shadow',
                    sub_vi, sub_prior, {}, check_baseline=True
                )
                checked += 1
                errors.extend(eval_errs)
            continue

        steps = case.get('steps', [])
        prior_state: Dict[str, Any] = {}
        last_validated_inputs: Dict[str, Any] = {}
        for idx, step in enumerate(steps):
            step_num = step.get('step')
            if 'inputs' not in step:
                year_month = '2026-01'
                note = step.get('note', '')
                for sess in _extract_summary_sessions(note, year_month):
                    gap_vi = copy.deepcopy(last_validated_inputs)
                    _, _, next_state, _, eval_errs = _evaluate_checked(
                        f"suc.{cid}.{step_num}.{sess}",
                        'fuse-eval-spec/v1', 'check-hash', 'test_policy_hash',
                        sess, f"{sess}T16:00:00Z", 'shadow',
                        gap_vi, prior_state, [], check_baseline=True
                    )
                    checked += 1
                    errors.extend(eval_errs)
                    prior_state = copy.deepcopy(next_state)
                continue

            sinp = step['inputs']
            last_validated_inputs = sinp['validated_inputs']

            if cid == 'SUC-08' and step_num in (2, 4):
                prev_session = steps[idx - 1]['inputs']['session']
                gap_count = 37 if step_num == 2 else 29
                for gap_idx, sess in enumerate(get_suc08_gap_sessions(prev_session, sinp['session'], gap_count), 2 if step_num == 2 else 41):
                    gap_vi = copy.deepcopy(sinp['validated_inputs'])
                    _, _, gap_next, _, eval_errs = _evaluate_checked(
                        f"suc.SUC-08.gap.{gap_idx}.{sess}",
                        'fuse-eval-spec/v1', 'check-hash', 'test_policy_hash',
                        sess, f"{sess}T16:00:00Z", 'shadow',
                        gap_vi, prior_state, [], check_baseline=True
                    )
                    checked += 1
                    errors.extend(eval_errs)
                    prior_state = copy.deepcopy(gap_next)

            frozen_prior = sinp.get('prior_row_state')
            if idx == 0:
                step_prior = copy.deepcopy(frozen_prior if frozen_prior is not None else prior_state)
            elif frozen_prior and frozen_prior.get('serialization_round_trip'):
                step_prior = json.loads(engine_canonical_json(prior_state))
            else:
                step_prior = copy.deepcopy(prior_state)

            vi = copy.deepcopy(sinp['validated_inputs'])
            events = copy.deepcopy(sinp.get('authorized_events') or [])
            _, _, next_state, _, eval_errs = _evaluate_checked(
                f"suc.{cid}.{step_num}",
                'fuse-eval-spec/v1', 'check-hash', 'test_policy_hash',
                sinp['session'], sinp.get('as_of', f"{sinp['session']}T16:00:00Z"),
                'shadow', vi, step_prior, events, check_baseline=True
            )
            checked += 1
            errors.extend(eval_errs)
            prior_state = copy.deepcopy(next_state)

    # 4. Precedence & fail-closed controls
    normal_vi = copy.deepcopy(scenarios['normal']['inputs']['validated_inputs'])
    controls: List[Tuple[str, Dict[str, Any], Optional[Tuple[str, str]]]] = []

    v_o4 = copy.deepcopy(normal_vi)
    v_o4['pending_orders'] = {'TQQQ': {'order_id': 'o1', 'status': 'pending', 'timeout': True}}
    controls.append(('prec.o4_timeout', v_o4, ('O4', 'ORDER-UNKNOWN')))

    v_mix = copy.deepcopy(v_o4)
    v_mix['broker_cash'] = 95000.0
    controls.append(('prec.o3_halt_dominance', v_mix, ('O3', 'HALT')))

    v_nan = copy.deepcopy(normal_vi)
    v_nan['funds']['TQQQ']['forecast_volatility'] = float('nan')
    controls.append(('fc.v4_nan', v_nan, ('V4', 'NO-NEW-RISK')))

    v_ret = copy.deepcopy(normal_vi)
    v_ret['funds']['TQQQ'].pop('fund_return')
    controls.append(('fc.v1_missing_return', v_ret, ('V1', 'NO-NEW-RISK')))

    v_idx = copy.deepcopy(normal_vi)
    v_idx['funds']['TQQQ']['index_return'] = None
    controls.append(('fc.v1_missing_index_return', v_idx, ('V1', 'NO-NEW-RISK')))

    v_4f = copy.deepcopy(normal_vi)
    for k in ('bankroll', 'high_water_mark', 'joint_exposure', 'max_loss_cap'):
        v_4f.pop(k)
    controls.append(('fc.o1_4field_missing', v_4f, ('O1', 'NO-NEW-RISK')))

    v_o1_nan = copy.deepcopy(normal_vi)
    v_o1_nan['source_records']['market_data']['age_sessions'] = float('nan')
    controls.append(('fc.o1_nan_age', v_o1_nan, ('O1', 'NO-NEW-RISK')))

    v_o6_missing = copy.deepcopy(normal_vi)
    v_o6_missing['loaded_policy_hash'] = None
    controls.append(('fc.o6_missing_policy_hash', v_o6_missing, ('O6', 'HALT')))

    v_o3_missing = copy.deepcopy(normal_vi)
    v_o3_missing['broker_cash'] = None
    controls.append(('fc.o3_missing_broker_cash', v_o3_missing, ('O3', 'HALT')))

    v_v2_tol = copy.deepcopy(normal_vi)
    v_v2_tol['reconciliation_tolerance'] = 100.0
    v_v2_tol['funds'] = {
        'TQQQ': {
            **copy.deepcopy(normal_vi['funds']['TQQQ']),
            'corporate_action': {'type': 'split', 'ratio': 2.0, 'adjustment_complete': True, 'exact_reconciliation': True},
            'share_count': 2000,
            'ledger_value': 25000.0,
            'broker_position': 2000,
            'broker_value': 24900.0,
            'reconciliation_tolerance': 100.0,
        }
    }
    controls.append(('fc.v2_tolerance_bypass', v_v2_tol, ('V2', 'HALT')))

    for label, vi, expected_row in controls:
        rows, _, _, vi_snap, eval_errs = _evaluate_checked(
            label,
            'fuse-eval-spec/v1', 'check-hash', 'registered_policy_hash_v1',
            '2026-01-05', '2026-01-05T16:00:00Z', 'shadow', vi, {}, [], check_baseline=True
        )
        checked += 1
        errors.extend(eval_errs)
        if expected_row is not None:
            row_id, exp_state = expected_row
            if rows[row_id]['state'] != exp_state:
                errors.append(f"{label}: expected {row_id}=={exp_state}, got {rows[row_id]['state']}")
        errors.extend(check_policy_mutation_monotonicity(label, vi_snap))

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
