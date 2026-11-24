#!/usr/bin/env python3
"""FUSE-1 trip matrix harness per BRIEF-FUSE-1 §6.

Loads frozen scenarios and golden table, executes base cells + tier repetitions + successor cases,
compares actual vs expected outcomes, writes result bundle with counts and canonical SHA-256.
"""

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add src and repo root to path
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / 'src'))
sys.path.insert(0, str(_REPO_ROOT))

from fuse_engine import evaluate
from fuse_engine.canonical import canonical_json as engine_canonical_json


def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def canonical_json(obj: Any) -> str:
    """Serialize object to canonical JSON (sorted keys, compact)."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


PRECEDENCE = ['HALT', 'ORDER-UNKNOWN', 'DE-RISK', 'NO-NEW-RISK', 'NORMAL']


def _more_restrictive(a: str, b: str) -> str:
    return a if PRECEDENCE.index(a) < PRECEDENCE.index(b) else b


def strict_value_equal(actual: Any, expected: Any) -> bool:
    """Compare nested JSON values with exact Python type checking (rejects True == 1, False == 0)."""
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        if actual.keys() != expected.keys():
            return False
        return all(strict_value_equal(actual[k], expected[k]) for k in expected)
    if isinstance(actual, list):
        if len(actual) != len(expected):
            return False
        return all(strict_value_equal(a, e) for a, e in zip(actual, expected))
    return actual == expected


def derive_expected_effective_map(
    scenario_name: str,
    scenario_data: Dict[str, Any],
    base_cells: Dict[str, Any],
    spec_data: Dict[str, Any],
) -> Dict[str, str]:
    """Independently derive expected effective_state_by_scope from frozen artifacts + §4.1."""
    vi = scenario_data['inputs']['validated_inputs']
    funds = vi.get('funds', {})
    fund_symbols = list(funds.keys())
    pending_orders = vi.get('pending_orders', {})
    prior = scenario_data['inputs'].get('prior_row_state') or {}
    symbol_universe = sorted(set(fund_symbols) | set(pending_orders.keys()) | set(prior.get('O4', {}).keys()))

    expected_map: Dict[str, str] = {'account': 'NORMAL'}
    for sym in fund_symbols:
        expected_map[f'fund:{sym}'] = 'NORMAL'
    for sym in symbol_universe:
        expected_map[f'symbol:{sym}'] = 'NORMAL'
    expected_map['joint'] = 'NORMAL'

    row_scopes = {row['id']: row['scope'] for row in spec_data['rows']}

    for row_id, scope_kind in row_scopes.items():
        outcome = base_cells[f'{scenario_name}.{row_id}']['outcome']
        state = outcome['state']
        if state == 'NORMAL':
            continue

        if scope_kind == 'account' or (row_id == 'O5' and outcome.get('latched')):
            expected_map['account'] = _more_restrictive(expected_map['account'], state)
        elif scope_kind == 'fund':
            reason = outcome.get('reason', '')
            matched_fund = None
            for sym in fund_symbols:
                if reason.endswith(f'_{sym}') or outcome.get('fund') == sym:
                    matched_fund = sym
                    break
            if matched_fund is not None:
                expected_map[f'fund:{matched_fund}'] = _more_restrictive(
                    expected_map[f'fund:{matched_fund}'], state
                )
            else:
                for sym in fund_symbols:
                    expected_map[f'fund:{sym}'] = _more_restrictive(
                        expected_map[f'fund:{sym}'], state
                    )
        elif scope_kind == 'symbol':
            sym = outcome.get('symbol')
            if sym and f'symbol:{sym}' in expected_map:
                expected_map[f'symbol:{sym}'] = _more_restrictive(
                    expected_map[f'symbol:{sym}'], state
                )
        elif scope_kind == 'joint':
            expected_map['joint'] = _more_restrictive(expected_map['joint'], state)

    # Spec §4.1: Account HALT dominates every narrower scope including joint.
    if expected_map['account'] == 'HALT':
        for scope in list(expected_map.keys()):
            expected_map[scope] = 'HALT'

    return expected_map


_CANONICAL_ROW_PROJECTION_EXTRAS = {
    None: {'outputs', 'symbols'},
    'V4': {'outputs'},
    'O4': {'symbols'},
}
_CANONICAL_OUTPUT_PROJECTION_EXTRAS = {
    None: {'disposition'},
    'V5': {'disposition'},
}
_CANONICAL_STATE_KEYS = {
    'O5': {'rejection_count', 'last_rejection_session', 'latched'},
    'L2': {'latched', 'trip_session'},
    'L3': {'latched', 'trip_session', 'cooling_off_until', 'loss_record'},
    'L4': {'latched', 'trip_session', 'details'},
    'L6': {'latched', 'trip_session', 'details'},
    'O3': {'latched', 'trip_session', 'details'},
    'O6': {'latched', 'trip_session', 'details'},
    'O7': {'latched', 'trip_session', 'details'},
    'O8': {'latched', 'trip_session'},
    'O9': {'latched', 'trip_session', 'details'},
    'V1': {'latched', 'trip_session', 'deviation', 'session_returns'},
    'V2': {'pending_adjustments', 'latched_mismatches'},
    'V3': {'latched', 'trip_session', 'details'},
    'V4': {'clearing_counter', 'last_session_below_threshold'},
    'V5': {'consecutive_beyond_tolerance', 'escalated', 'last_session'},
    'O4': {'original_order_id', 'status'},
}


def compare_outcome(
    actual: Dict[str, Any],
    expected: Dict[str, Any],
    row_id: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """Compare actual row outcome against expected golden outcome.

    Returns (matches, diff_messages).
    Enforces every key declared in expected with strict Python type equality AND
    rejects non-canonical unexpected extra keys on actual outcomes/outputs.
    """
    diffs = []

    # Required fields
    for field in ['state', 'would_have_tripped', 'kind', 'latched']:
        if not strict_value_equal(actual.get(field), expected.get(field)):
            diffs.append(f"  {field}: actual={actual.get(field)!r} != expected={expected.get(field)!r}")

    # Reason class comparison (not free text)
    actual_reason = actual.get('reason', 'none')
    expected_reason = expected.get('reason', 'none')
    if not strict_value_equal(actual_reason, expected_reason):
        diffs.append(f"  reason: actual={actual_reason!r} != expected={expected_reason!r}")

    # Enforce EVERY key declared in expected (zero ignored projection fields)
    for field, exp_val in expected.items():
        if field in ('state', 'would_have_tripped', 'kind', 'latched', 'reason'):
            continue
        if field == 'clearing_counter':
            actual_counter = actual.get('outputs', {}).get('clearing_counter')
            if not strict_value_equal(actual_counter, exp_val):
                diffs.append(
                    f"  clearing_counter: actual={actual_counter!r} (from outputs) != expected={exp_val!r} (top-level)"
                )
        elif field == 'outputs':
            actual_outputs = actual.get('outputs')
            if not isinstance(actual_outputs, dict) or not isinstance(exp_val, dict):
                if not strict_value_equal(actual_outputs, exp_val):
                    diffs.append(f"  outputs: actual={actual_outputs!r} != expected={exp_val!r}")
                continue
            for key in exp_val:
                if key not in actual_outputs:
                    diffs.append(f"  outputs.{key}: missing in actual")
                elif not strict_value_equal(actual_outputs[key], exp_val[key]):
                    diffs.append(
                        f"  outputs.{key}: actual={actual_outputs[key]!r} != expected={exp_val[key]!r}"
                    )
            allowed_out_extras = _CANONICAL_OUTPUT_PROJECTION_EXTRAS.get(row_id, set())
            extra_out_keys = sorted(set(actual_outputs.keys()) - set(exp_val.keys()) - allowed_out_extras)
            if extra_out_keys:
                diffs.append(f"  outputs extra keys in actual: {extra_out_keys}")
        else:
            if field not in actual:
                diffs.append(f"  {field}: missing in actual (expected={exp_val!r})")
            elif not strict_value_equal(actual[field], exp_val):
                diffs.append(f"  {field}: actual={actual[field]!r} != expected={exp_val!r}")

    allowed_extras = _CANONICAL_ROW_PROJECTION_EXTRAS.get(row_id, set())
    if 'clearing_counter' in expected:
        allowed_extras = allowed_extras | {'outputs'}
    extra_top_keys = sorted(set(actual.keys()) - set(expected.keys()) - allowed_extras)
    if extra_top_keys:
        diffs.append(f"  extra keys in actual: {extra_top_keys}")

    return (len(diffs) == 0, diffs)


def compare_base_outcome_exact(actual: Dict[str, Any], expected: Dict[str, Any], row_id: str) -> Tuple[bool, List[str]]:
    """Compare base cell outcome with strict full dictionary equality + exact value types (R4)."""
    if strict_value_equal(actual, expected):
        return (True, [])

    diffs = []
    missing_keys = sorted(set(expected.keys()) - set(actual.keys()))
    extra_keys = sorted(set(actual.keys()) - set(expected.keys()))
    if missing_keys:
        diffs.append(f"  missing keys: {missing_keys}")
    if extra_keys:
        diffs.append(f"  extra keys: {extra_keys}")
    for key in sorted(set(actual.keys()) & set(expected.keys())):
        if not strict_value_equal(actual[key], expected[key]):
            diffs.append(
                f"  {key}: actual={actual[key]!r} ({type(actual[key]).__name__}) != "
                f"expected={expected[key]!r} ({type(expected[key]).__name__})"
            )
    return (False, diffs)


def compare_effective_state(
    actual: Dict[str, str],
    expected: Dict[str, str],
    full_keys: bool = False,
) -> Tuple[bool, List[str]]:
    """Compare effective state by scope (subset or exact full key set)."""
    diffs = []

    if full_keys:
        extra = sorted(set(actual.keys()) - set(expected.keys()))
        if extra:
            diffs.append(f"  extra scopes in actual: {extra}")

    for scope in sorted(expected.keys()):
        if scope not in actual:
            diffs.append(f"  {scope}: missing in actual")
        elif not strict_value_equal(actual[scope], expected[scope]):
            diffs.append(f"  {scope}: actual={actual[scope]!r} != expected={expected[scope]!r}")

    return (len(diffs) == 0, diffs)


def compare_next_row_state(actual: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Compare next_row_state projections (Slice 4b).

    Compares successor state including:
    - Fund-keyed state (V4.TQQQ.clearing_counter, V1.TQQQ.deviation, etc.)
    - Symbol-keyed state (O4.TQQQ.original_order_id, etc.)
    - Empty row maps ({"L2":{}}, {"V1":{}}) after clearing
    - V4 counter and last_session_below_threshold separately

    Returns (matches, diff_messages).
    """
    diffs = []

    # Only check rows present in expected (successor cases may specify subset)
    for row_id in sorted(expected.keys()):
        expected_row_state = expected[row_id]
        actual_row_state = actual.get(row_id)

        # Strict empty row map check (G1.3): {"L2":{}} requires present empty dict {},
        # NEVER absent state (None).
        if expected_row_state == {}:
            if row_id not in actual or not strict_value_equal(actual[row_id], {}):
                actual_repr = '<absent>' if row_id not in actual else actual[row_id]
                diffs.append(f"  next_row_state.{row_id}: expected explicit empty map {{}}, got {actual_repr}")
        else:
            # Non-empty: check expected fields (actual may have extra fields like last_session)
            if actual_row_state is None:
                diffs.append(f"  next_row_state.{row_id}: missing in actual")
            elif isinstance(expected_row_state, dict) and isinstance(actual_row_state, dict):
                allowed_row_keys = _CANONICAL_STATE_KEYS.get(row_id)
                if row_id == 'O5' or (allowed_row_keys is not None and not any(isinstance(v, dict) for v in actual_row_state.values())):
                    extra_state_keys = sorted(set(actual_row_state.keys()) - set(expected_row_state.keys()) - (allowed_row_keys or set()))
                    if extra_state_keys:
                        diffs.append(f"  next_row_state.{row_id}: extra keys in actual: {extra_state_keys}")
                # Deep comparison with exact Python type checks (rejects True == 1)
                for scope_key in expected_row_state:
                    expected_scope_state = expected_row_state[scope_key]
                    actual_scope_state = actual_row_state.get(scope_key)

                    if actual_scope_state is None:
                        diffs.append(f"  next_row_state.{row_id}.{scope_key}: missing in actual")
                    elif isinstance(expected_scope_state, dict) and isinstance(actual_scope_state, dict):
                        if allowed_row_keys is not None and row_id != 'V2':
                            extra_scope_keys = sorted(set(actual_scope_state.keys()) - set(expected_scope_state.keys()) - allowed_row_keys)
                            if extra_scope_keys:
                                diffs.append(f"  next_row_state.{row_id}.{scope_key}: extra keys in actual: {extra_scope_keys}")
                        # Fund/symbol keyed: compare expected fields + reject unexpected non-canonical extras
                        for field in expected_scope_state:
                            if field not in actual_scope_state:
                                diffs.append(f"  next_row_state.{row_id}.{scope_key}.{field}: missing in actual")
                            elif not strict_value_equal(actual_scope_state[field], expected_scope_state[field]):
                                diffs.append(
                                    f"  next_row_state.{row_id}.{scope_key}.{field}: "
                                    f"actual={actual_scope_state[field]!r} != expected={expected_scope_state[field]!r}"
                                )
                    elif not strict_value_equal(actual_scope_state, expected_scope_state):
                        diffs.append(
                            f"  next_row_state.{row_id}.{scope_key}: "
                            f"actual={actual_scope_state!r} != expected={expected_scope_state!r}"
                        )
            else:
                # Non-dict: direct strict type+value comparison
                if not strict_value_equal(actual_row_state, expected_row_state):
                    diffs.append(f"  next_row_state.{row_id}: actual={actual_row_state!r} != expected={expected_row_state!r}")

    return (len(diffs) == 0, diffs)


def validate_row_shape(rows_by_ID: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate that rows_by_ID has exactly the 24 named IDs (Slice 4b).

    Per §5.1: exactly {L0-L6, V1-V7, O1-O9, J1}, each once, with five standard fields.
    Absent IDs must NOT become empty dictionaries.

    Returns (valid, error_messages).
    """
    errors = []

    # Expected 24 IDs
    expected_ids = {
        'L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6',
        'V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7',
        'O1', 'O2', 'O3', 'O4', 'O5', 'O6', 'O7', 'O8', 'O9',
        'J1'
    }

    actual_ids = set(rows_by_ID.keys())

    # Check exact set equality
    missing = expected_ids - actual_ids
    extra = actual_ids - expected_ids

    if missing:
        errors.append(f"Missing IDs: {sorted(missing)}")
    if extra:
        errors.append(f"Extra IDs: {sorted(extra)}")

    # Check standard fields for each present row
    required_fields = {'state', 'would_have_tripped', 'kind', 'latched', 'reason'}
    for row_id in actual_ids & expected_ids:  # intersection
        row = rows_by_ID[row_id]
        if not isinstance(row, dict):
            errors.append(f"{row_id}: not a dict (got {type(row).__name__})")
            continue

        # Empty dict check: absent ID must NOT become {}
        if row == {}:
            errors.append(f"{row_id}: empty dictionary (absent row must be omitted, not empty dict)")
            continue

        # Check standard fields
        missing_fields = required_fields - set(row.keys())
        if missing_fields:
            errors.append(f"{row_id}: missing standard fields {sorted(missing_fields)}")

    return (len(errors) == 0, errors)


def execute_cell(scenario: Dict[str, Any], row_id: str, engine_hash: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Execute one matrix cell against the engine.

    Returns (row_outcome, effective_state_by_scope).
    """
    inputs = scenario['inputs']

    # Call evaluator
    rows_by_ID, effective_state_by_scope, next_row_state = evaluate(
        spec_version=inputs['spec_version'],
        engine_hash=engine_hash,
        policy_hash=inputs['policy_hash'],
        session=inputs['session'],
        as_of=inputs['as_of'],
        mode=inputs['mode'],
        validated_inputs=inputs['validated_inputs'],
        prior_row_state=inputs.get('prior_row_state'),
        authorized_events=inputs.get('authorized_events')
    )

    # Extract this row's outcome
    row_outcome = rows_by_ID.get(row_id, {})

    return (row_outcome, effective_state_by_scope)


def run_base_cells(
    scenarios: Dict[str, Any],
    golden_table: Dict[str, Any],
    engine_hash: str,
    spec_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run all 264 base matrix cells (24 rows × 11 scenarios).

    Checks both strict row outcome dicts and independent §4.1 effective_state_by_scope
    across all 264 cells (A03). Returns results dict with counts and failures.
    """
    base_cells = golden_table['base_cells']
    if spec_data is None:
        spec_data = load_json(_REPO_ROOT / 'spec' / 'spec.json')

    expected_full_maps = {
        sc_name: derive_expected_effective_map(sc_name, sc_data, base_cells, spec_data)
        for sc_name, sc_data in scenarios['scenarios'].items()
    }

    results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'failures': []
    }

    for cell_key, golden_cell in base_cells.items():
        scenario_name = golden_cell['scenario']
        row_id = golden_cell['row_id']

        results['total'] += 1

        # Execute
        scenario = scenarios['scenarios'][scenario_name]
        actual_outcome, actual_effective_state = execute_cell(scenario, row_id, engine_hash)

        # Compare outcome (R4: strict full dict equality across all 264 base cells)
        outcome_match, outcome_diffs = compare_base_outcome_exact(actual_outcome, golden_cell['outcome'], row_id)

        # Compare effective state against independent §4.1 derivation across ALL 264 cells
        state_match, state_diffs = compare_effective_state(
            actual_effective_state,
            expected_full_maps[scenario_name],
            full_keys=True,
        )
        if 'effective_state_by_scope' in golden_cell:
            subset_match, subset_diffs = compare_effective_state(
                actual_effective_state,
                golden_cell['effective_state_by_scope']
            )
            if not subset_match:
                state_match = False
                state_diffs.extend(subset_diffs)

        if outcome_match and state_match:
            results['passed'] += 1
        else:
            results['failed'] += 1
            failure = {
                'cell': cell_key,
                'scenario': scenario_name,
                'row_id': row_id,
                'diffs': []
            }
            if not outcome_match:
                failure['diffs'].append(f"Outcome mismatch:\n" + "\n".join(outcome_diffs))
            if not state_match:
                failure['diffs'].append(f"Effective state mismatch:\n" + "\n".join(state_diffs))
            results['failures'].append(failure)

    return results


def run_tier_repetitions(scenarios: Dict[str, Any], golden_table: Dict[str, Any], engine_hash: str) -> Dict[str, Any]:
    """Run tier repetitions for tier-parameterized rows (L0-L4, J1 × 3 tiers).

    Real parameterized runner per Slice 4(a): executes engine with tier-specific
    fixtures and compares actual outputs. Required for F1-A04 claim.

    Returns results dict with counts and failures.
    """
    tier_repetitions = golden_table.get('tier_repetitions', {})

    results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'failures': []
    }

    # Tier-specific parameters per spec §4.3 / goldens/DERIVATION.md (J1: 40k/60k/80k on 100k bankroll)
    tier_params = {
        'conservative': {'D': 0.15, 'joint_cap_ratio': 0.4},
        'balanced': {'D': 0.30, 'joint_cap_ratio': 0.6},
        'aggressive': {'D': 0.50, 'joint_cap_ratio': 0.8}
    }

    for cell_key, cell_data in tier_repetitions.items():
        results['total'] += 1

        scenario_name = cell_data['scenario']
        row_id = cell_data['row_id']
        tier = cell_data['tier']
        expected_outcome = cell_data['outcome']

        # Get base scenario inputs (deep copy; honour frozen priors and events per G2)
        scenario = scenarios['scenarios'][scenario_name]
        scenario_inputs = scenario['inputs']
        inputs = copy.deepcopy(scenario_inputs['validated_inputs'])

        # Apply tier-specific parameters (R5: true tier caps 0.4/0.6/0.8 × bankroll)
        inputs['tier'] = tier
        tier_param = tier_params[tier]
        inputs['tier_loss_budget_D'] = tier_param['D']
        cap = round(inputs['bankroll'] * tier_param['joint_cap_ratio'], 2)
        inputs['max_loss_cap'] = cap
        inputs['tier_joint_cap'] = cap

        prior_state = copy.deepcopy(scenario_inputs.get('prior_row_state') or {})
        auth_events = copy.deepcopy(scenario_inputs.get('authorized_events') or [])

        # Run evaluator
        try:
            rows, _, _ = evaluate(
                spec_version=scenario_inputs.get('spec_version', 'fuse-eval-spec/v1'),
                engine_hash=engine_hash,
                policy_hash=scenario_inputs.get('policy_hash', 'test-policy'),
                session=scenario_inputs['session'],
                as_of=scenario_inputs['as_of'],
                mode=scenario_inputs.get('mode', 'shadow'),
                validated_inputs=inputs,
                prior_row_state=prior_state,
                authorized_events=auth_events
            )

            actual_row = rows.get(row_id, {})

            # Compare against expected outcome using full-key strict equality (A04)
            matches, diff_msgs = compare_base_outcome_exact(actual_row, expected_outcome, row_id)
            if not matches:
                results['failed'] += 1
                results['failures'].append({
                    'cell_key': cell_key,
                    'scenario': scenario_name,
                    'row_id': row_id,
                    'tier': tier,
                    'diff': diff_msgs
                })
            else:
                results['passed'] += 1

        except Exception as e:
            results['failed'] += 1
            results['failures'].append({
                'cell_key': cell_key,
                'scenario': scenario_name,
                'row_id': row_id,
                'tier': tier,
                'error': str(e)
            })

    return results


def _deep_shape_equal(obj1: Any, obj2: Any, path: str = 'root') -> Tuple[bool, List[str]]:
    """Compare recursive dict/list shape (keys and exact value types)."""
    diffs: List[str] = []
    if type(obj1) is not type(obj2):
        diffs.append(f"{path}: type mismatch ({type(obj1).__name__} vs {type(obj2).__name__})")
        return False, diffs
    if isinstance(obj1, dict):
        k1, k2 = set(obj1.keys()), set(obj2.keys())
        if k1 != k2:
            missing = k2 - k1
            extra = k1 - k2
            if missing:
                diffs.append(f"{path}: missing keys {sorted(missing)}")
            if extra:
                diffs.append(f"{path}: extra keys {sorted(extra)}")
            return False, diffs
        ok = True
        for k in sorted(k1):
            sub_ok, sub_diffs = _deep_shape_equal(obj1[k], obj2[k], f"{path}.{k}")
            if not sub_ok:
                ok = False
                diffs.extend(sub_diffs)
        return ok, diffs
    if isinstance(obj1, list):
        if len(obj1) != len(obj2):
            diffs.append(f"{path}: list length mismatch ({len(obj1)} vs {len(obj2)})")
            return False, diffs
        ok = True
        for idx, (a, b) in enumerate(zip(obj1, obj2)):
            sub_ok, sub_diffs = _deep_shape_equal(a, b, f"{path}[{idx}]")
            if not sub_ok:
                ok = False
                diffs.extend(sub_diffs)
        return ok, diffs
    return True, []


def build_suc11_probes() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Return synthetic deep-shape validated_inputs, combined_prior, and two_fund_inputs for SUC-11."""
    common_validated = {
        'tier': 'balanced',
        'bankroll': 100000.0,
        'high_water_mark': 100000.0,
        'joint_exposure': 25000.0,
        'proposed_exposure': 30000.0,
        'max_loss_cap': 50000.0,
        'tier_joint_cap': 50000.0,
        'tier_loss_budget_D': 0.30,
        'one_session_loss': 0.0,
        'market_halt_level': None,
        'index_one_session_returns': {'SPX': 0.005, 'NDX': 0.008},
        'session_calendar_status': 'open',
        'exchange_status': 'open',
        'positions_cash': 50000.0,
        'broker_cash': 50000.0,
        'reconciliation_tolerance': 100.0,
        'loaded_policy_hash': 'synthetic-policy',
        'registered_policy_hash': 'synthetic-policy',
        'funds': {
            'TQQQ': {
                'fund_return': 0.024,
                'index_return': 0.008,
                'modelled_fee': 0.0001,
                'modelled_financing': 0.0001,
                'forecast_volatility': 0.21,
                'long_run_volatility': 0.24,
                'shortfall_observed': 0.008,
                'shortfall_predicted': 0.003,
                'v5_tolerance': 0.003,
                'v6_cost_per_unit_exposure': 0.015,
                'v6_threshold': 0.01,
                'quote_staleness': 0.5,
                'spread_width': 0.0005,
                'v7_spread_width': None,
                'trading_pause': False,
                'session_time': 'regular',
                'ledger_value': 50000.0,
                'broker_value': 50000.0,
            }
        }
    }
    prior_v4 = {'V4': {'TQQQ': {'clearing_counter': 5, 'last_session_below_threshold': '2026-01-05'}}}
    prior_v5 = {'V5': {'TQQQ': {'consecutive_beyond_tolerance': 20, 'escalated': False, 'last_session': '2026-01-05'}}}
    combined_prior = {**prior_v4, **prior_v5}

    two_fund_inputs = copy.deepcopy(common_validated)
    two_fund_inputs['funds']['SOXL'] = copy.deepcopy(common_validated['funds']['TQQQ'])
    two_fund_inputs['funds']['TQQQ']['v5_tolerance'] = None
    two_fund_inputs['funds']['SOXL']['v5_tolerance'] = None
    two_fund_inputs['funds']['TQQQ'].pop('v6_cost_per_unit_exposure', None)
    two_fund_inputs['funds']['TQQQ'].pop('v6_threshold', None)
    two_fund_inputs['funds']['SOXL'].pop('v6_cost_per_unit_exposure', None)
    two_fund_inputs['funds']['SOXL'].pop('v6_threshold', None)
    return common_validated, combined_prior, two_fund_inputs


def _execute_suc11_deep_shape(engine_hash: str) -> Tuple[bool, List[str]]:
    """Execute SUC-11 deep-shape fixture via real evaluate() calls (G1.2)."""
    diffs: List[str] = []
    common_validated, combined_prior, two_fund_inputs = build_suc11_probes()

    rows, scopes, next_state = evaluate(
        spec_version='fuse-eval-spec/v1',
        engine_hash=engine_hash,
        policy_hash='synthetic-policy',
        session='2026-01-06',
        as_of='2026-01-06T16:00:00Z',
        mode='shadow',
        validated_inputs=common_validated,
        prior_row_state=combined_prior,
        authorized_events={}
    )

    shape_ok, shape_errs = validate_row_shape(rows)
    if not shape_ok:
        diffs.extend([f"SUC-11 row shape error: {e}" for e in shape_errs])

    # Check V4 unwrapped clearing_counter
    v4_out = rows.get('V4', {}).get('outputs', {})
    if v4_out.get('clearing_counter') != 6 or 'TQQQ' in v4_out:
        diffs.append(f"SUC-11 V4 outputs shape unexpected: {v4_out}")

    # Check V5 diagnostic outputs keys and types
    v5_out = rows.get('V5', {}).get('outputs', {})
    for key, expected_type in [
        ('excess_shortfall', float),
        ('consecutive_sessions_beyond_tolerance', int),
        ('escalated_to_v1', bool),
        ('disposition', str),
    ]:
        if key not in v5_out or type(v5_out[key]) is not expected_type:
            diffs.append(f"SUC-11 V5.outputs.{key} expected {expected_type.__name__}, got {v5_out.get(key)!r}")

    # Check V6 diagnostic outputs keys and types
    v6_out = rows.get('V6', {}).get('outputs', {})
    for key, expected_type in [
        ('cost_per_unit_exposure', float),
        ('threshold', float),
        ('exceeded', bool),
        ('notify', bool),
    ]:
        if key not in v6_out or type(v6_out[key]) is not expected_type:
            diffs.append(f"SUC-11 V6.outputs.{key} expected {expected_type.__name__}, got {v6_out.get(key)!r}")

    # Second evaluate() call with two funds (matches stub shape check on multi-fund)
    two_rows, two_scopes, _ = evaluate(
        spec_version='fuse-eval-spec/v1',
        engine_hash=engine_hash,
        policy_hash='synthetic-policy',
        session='2026-01-06',
        as_of='2026-01-06T16:00:00Z',
        mode='shadow',
        validated_inputs=two_fund_inputs,
        prior_row_state={},
        authorized_events={}
    )
    from fixtures import stub_adapter
    stub_rows, stub_scopes, _ = stub_adapter.evaluate(
        'fuse-eval-spec/v1', engine_hash, 'synthetic-policy', '2026-01-06', '2026-01-06T16:00:00Z',
        'shadow', two_fund_inputs, {}, {}
    )
    rows_match, rows_diffs = _deep_shape_equal(two_rows, stub_rows, 'rows_by_ID')
    if not rows_match:
        diffs.extend([f"SUC-11 stub shape mismatch: {d}" for d in rows_diffs])
    scopes_match, scopes_diffs = _deep_shape_equal(two_scopes, stub_scopes, 'effective_state_by_scope')
    if not scopes_match:
        diffs.extend([f"SUC-11 scope shape mismatch: {d}" for d in scopes_diffs])

    # Negative control: inject nested type mismatch in V5.outputs.consecutive_sessions_beyond_tolerance
    mutated_rows = copy.deepcopy(rows)
    mutated_rows['V5']['outputs']['consecutive_sessions_beyond_tolerance'] = str(
        mutated_rows['V5']['outputs']['consecutive_sessions_beyond_tolerance']
    )
    neg_equal, neg_diffs = _deep_shape_equal(rows, mutated_rows, 'rows_by_ID')
    if neg_equal or not any('consecutive_sessions_beyond_tolerance' in d for d in neg_diffs):
        diffs.append("SUC-11 negative control failed: nested V5 type mutation not detected")

    return (len(diffs) == 0, diffs)


def _extract_summary_sessions(note: str, year_month: str = '2026-01') -> List[str]:
    """Extract ordered YYYY-MM-DD session dates from summary step note."""
    days = re.findall(r'\b(\d{1,2})\b', note.split('January')[-1].split('of 2026')[0])
    return [f"{year_month}-{int(d):02d}" for d in days]


def get_suc08_gap_sessions(prev_session: str, target_session: str, count: int) -> List[str]:
    """Return `count` strictly ascending weekday dates in (prev_session, target_session)."""
    d = date.fromisoformat(prev_session) + timedelta(days=1)
    end = date.fromisoformat(target_session)
    sessions: List[str] = []
    while d < end and len(sessions) < count:
        if d.weekday() < 5:
            sessions.append(d.isoformat())
        d += timedelta(days=1)
    if len(sessions) != count:
        raise ValueError(
            f"Expected {count} trading sessions between {prev_session} and {target_session}, got {len(sessions)}"
        )
    return sessions


def run_successor_cases(successor_cases: Dict[str, Any], engine_hash: str) -> Dict[str, Any]:
    """Run successor-state continuity cases.

    Each case has multiple steps that execute in sequence, threading real
    next_row_state from one step into the next step's prior_row_state.

    Returns results dict with counts and failures.
    """
    cases = successor_cases.get('cases', {})

    results = {
        'total': len(cases),
        'passed': 0,
        'failed': 0,
        'failures': []
    }

    for case_id, case in cases.items():
        # G1.2: SUC-11 executes deep-shape verification via real evaluate() calls
        if case_id == 'SUC-11' or (case.get('phase_3_implementation') and not case.get('steps')):
            ok, suc11_diffs = _execute_suc11_deep_shape(engine_hash)
            if ok:
                results['passed'] += 1
            else:
                results['failed'] += 1
                results['failures'].append({'case': case_id, 'diffs': suc11_diffs})
            continue

        steps = case.get('steps', [])
        case_failed = False
        case_diffs = []

        # Thread real next_row_state across steps
        prior_state: Dict[str, Any] = {}
        last_validated_inputs: Dict[str, Any] = {}
        for idx, step_data in enumerate(steps):
            step_num = step_data.get('step')

            # G1.4: Execute summary multi-session gap steps (SUC-06/5 and SUC-07/3)
            if 'inputs' not in step_data:
                summary_sessions = _extract_summary_sessions(step_data.get('note', ''))
                if not summary_sessions or not last_validated_inputs:
                    case_failed = True
                    case_diffs.append(f"Step {step_num} unexecutable summary step")
                    break

                if 'summary_counter_values' in step_data:
                    expected_counts = step_data['summary_counter_values']
                    if len(summary_sessions) != len(expected_counts):
                        case_failed = True
                        case_diffs.append(f"Step {step_num} session/counter count mismatch")
                        break
                    for sess, exp_cnt in zip(summary_sessions, expected_counts):
                        rows_by_ID, _, next_row_state = evaluate(
                            spec_version='fuse-eval-spec/v1',
                            engine_hash=engine_hash,
                            policy_hash='test_policy_hash',
                            session=sess,
                            as_of=f"{sess}T16:00:00Z",
                            mode='shadow',
                            validated_inputs=last_validated_inputs,
                            prior_row_state=prior_state,
                            authorized_events=[]
                        )
                        actual_cnt = rows_by_ID.get('V4', {}).get('outputs', {}).get('clearing_counter')
                        if not strict_value_equal(actual_cnt, exp_cnt):
                            case_failed = True
                            case_diffs.append(f"Step {step_num} ({sess}) V4 clearing_counter={actual_cnt!r} != {exp_cnt!r}")
                            break
                        prior_state = next_row_state
                    if not case_failed:
                        end_cnt = prior_state.get('V4', {}).get('TQQQ', {}).get('clearing_counter')
                        if not strict_value_equal(end_cnt, step_data.get('counter_at_step_end')):
                            case_failed = True
                            case_diffs.append(f"Step {step_num} counter_at_step_end={end_cnt!r} != {step_data.get('counter_at_step_end')!r}")
                elif 'expected_clearing_counter' in step_data:
                    final_sess = step_data.get('final_session')
                    if summary_sessions[-1] != final_sess:
                        case_failed = True
                        case_diffs.append(f"Step {step_num} final_session {summary_sessions[-1]} != {final_sess}")
                        break
                    last_rows: Dict[str, Any] = {}
                    for sess in summary_sessions:
                        last_rows, _, next_row_state = evaluate(
                            spec_version='fuse-eval-spec/v1',
                            engine_hash=engine_hash,
                            policy_hash='test_policy_hash',
                            session=sess,
                            as_of=f"{sess}T16:00:00Z",
                            mode='shadow',
                            validated_inputs=last_validated_inputs,
                            prior_row_state=prior_state,
                            authorized_events=[]
                        )
                        prior_state = next_row_state
                    v4_final = last_rows.get('V4', {})
                    if not strict_value_equal(v4_final.get('state'), step_data.get('expected_state')):
                        case_failed = True
                        case_diffs.append(f"Step {step_num} final V4 state={v4_final.get('state')!r} != {step_data.get('expected_state')!r}")
                    if not strict_value_equal(v4_final.get('outputs', {}).get('clearing_counter'), step_data.get('expected_clearing_counter')):
                        case_failed = True
                        case_diffs.append(
                            f"Step {step_num} final V4 clearing_counter={v4_final.get('outputs', {}).get('clearing_counter')!r} != {step_data.get('expected_clearing_counter')!r}"
                        )
                    if prior_state.get('V4') != {}:
                        case_failed = True
                        case_diffs.append(f"Step {step_num} expected cleared V4={{}}, got {prior_state.get('V4')!r}")
                else:
                    case_failed = True
                    case_diffs.append(f"Step {step_num} missing inputs and unrecognized summary schema")
                continue

            step_inputs = step_data['inputs']
            expected_outputs = step_data.get('expected_outputs', {})
            last_validated_inputs = step_inputs['validated_inputs']

            # R6: Execute all intermediate SUC-08 sessions (2..38 and 41..69) using continuous
            # live engine state rather than injecting frozen prior_row_state at checkpoints.
            if case_id == 'SUC-08' and step_num in (2, 4):
                prev_session = steps[idx - 1]['inputs']['session']
                if step_num == 2:
                    expected_gap_range = range(2, 39)
                    expected_gap_state = 'NORMAL'
                    expected_escalated = False
                else:
                    expected_gap_range = range(41, 70)
                    expected_gap_state = 'NO-NEW-RISK'
                    expected_escalated = True
                gap_sessions = get_suc08_gap_sessions(
                    prev_session, step_inputs['session'], len(expected_gap_range)
                )
                for sess, exp_cnt in zip(gap_sessions, expected_gap_range):
                    gap_rows, _, gap_next_state = evaluate(
                        spec_version='fuse-eval-spec/v1',
                        engine_hash=engine_hash,
                        policy_hash='test_policy_hash',
                        session=sess,
                        as_of=f"{sess}T16:00:00Z",
                        mode='shadow',
                        validated_inputs=copy.deepcopy(step_inputs['validated_inputs']),
                        prior_row_state=prior_state,
                        authorized_events=[]
                    )
                    v5_gap = gap_rows.get('V5', {})
                    v5_gap_out = v5_gap.get('outputs', {})
                    if (
                        v5_gap.get('state') != expected_gap_state or
                        v5_gap_out.get('consecutive_sessions_beyond_tolerance') != exp_cnt or
                        v5_gap_out.get('escalated_to_v1') is not expected_escalated
                    ):
                        case_failed = True
                        case_diffs.append(
                            f"SUC-08 gap session {sess} (#{exp_cnt}) mismatch: {v5_gap!r}"
                        )
                        break
                    prior_state = gap_next_state
                if case_failed:
                    break

            # Determine prior_row_state:
            # - Step 1 starts from its declared initial prior_row_state (usually {} or SUC-07 seed)
            # - All consecutive steps strictly thread real next_row_state (serializing across restart)
            frozen_prior = step_inputs.get('prior_row_state')
            if idx == 0:
                step_prior = frozen_prior if frozen_prior is not None else prior_state
            else:
                if frozen_prior and frozen_prior.get('serialization_round_trip'):
                    step_prior = json.loads(engine_canonical_json(prior_state))
                else:
                    step_prior = prior_state

            # Build evaluation inputs
            eval_inputs = {
                'spec_version': 'fuse-eval-spec/v1',
                'engine_hash': engine_hash,
                'policy_hash': 'test_policy_hash',
                'session': step_inputs['session'],
                'as_of': step_inputs.get('as_of', f"{step_inputs['session']}T16:00:00Z"),
                'mode': 'shadow',
                'validated_inputs': step_inputs['validated_inputs'],
                'prior_row_state': step_prior,
                'authorized_events': step_inputs.get('authorized_events', [])
            }

            # Execute
            try:
                rows_by_ID, effective_state_by_scope, next_row_state = evaluate(
                    **eval_inputs
                )
            except Exception as e:
                case_failed = True
                case_diffs.append(f"Step {step_num} execution error: {str(e)}")
                break

            # Validate row shape (Slice 4b): exactly 24 IDs, each once, standard fields
            shape_valid, shape_errors = validate_row_shape(rows_by_ID)
            if not shape_valid:
                case_failed = True
                case_diffs.append(f"Step {step_num} row shape validation failed:\n" + "\n".join(f"  {e}" for e in shape_errors))

            # Compare expected row outputs
            for row_id, expected_row in expected_outputs.items():
                if row_id == 'effective_state_by_scope':
                    # Compare effective state
                    actual_effective = effective_state_by_scope
                    expected_effective = expected_row
                    state_match, state_diffs = compare_effective_state(actual_effective, expected_effective)
                    if not state_match:
                        case_failed = True
                        case_diffs.append(f"Step {step_num} effective state mismatch:\n" + "\n".join(state_diffs))
                else:
                    # Compare row outcome
                    actual_row = rows_by_ID.get(row_id, {})
                    outcome_match, outcome_diffs = compare_outcome(actual_row, expected_row, row_id=row_id)
                    if not outcome_match:
                        case_failed = True
                        case_diffs.append(f"Step {step_num} row {row_id} mismatch:\n" + "\n".join(outcome_diffs))

            # Compare next_row_state if specified (Slice 4b)
            if 'next_row_state' in step_data:
                expected_next_state = step_data['next_row_state']
                state_match, state_diffs = compare_next_row_state(next_row_state, expected_next_state)
                if not state_match:
                    case_failed = True
                    case_diffs.append(f"Step {step_num} next_row_state mismatch:\n" + "\n".join(state_diffs))

            # Thread real next_row_state (never frozen projection)
            prior_state = next_row_state

        if case_failed:
            results['failed'] += 1
            results['failures'].append({
                'case': case_id,
                'diffs': case_diffs
            })
        else:
            results['passed'] += 1

    return results


_EXPECTED_ENGINE_FILES = (
    '__init__.py',
    'canonical.py',
    'canonical_state.py',
    'evaluator.py',
    'rows_loss.py',
    'rows_ops.py',
    'rows_vehicle.py',
    'state.py',
)


def compute_engine_hash() -> str:
    """Compute length-framed SHA-256 hash of the verified canonical engine bundle (§5.3)."""
    engine_dir = Path(__file__).parent.parent / 'src' / 'fuse_engine'
    py_files = sorted(
        engine_dir.rglob('*.py'),
        key=lambda p: p.relative_to(engine_dir).as_posix(),
    )
    rel_paths = [p.relative_to(engine_dir).as_posix() for p in py_files]
    if rel_paths != list(_EXPECTED_ENGINE_FILES):
        raise RuntimeError(
            f"Unexpected engine file set: expected={list(_EXPECTED_ENGINE_FILES)!r}, got={rel_paths!r}"
        )

    hasher = hashlib.sha256()
    for py_file, rel_path in zip(py_files, rel_paths):
        rel_bytes = rel_path.encode('utf-8')
        data = py_file.read_bytes()
        hasher.update(len(rel_bytes).to_bytes(4, 'big'))
        hasher.update(rel_bytes)
        hasher.update(len(data).to_bytes(8, 'big'))
        hasher.update(data)

    return hasher.hexdigest()


def verify_freeze_manifest(goldens_dir: Path, freeze: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Independently recompute SHA-256 of golden files & combined_freeze_hash from disk."""
    errors: List[str] = []
    declared_hashes = freeze.get('file_hashes', {})
    required_files = ('scenarios.json', 'golden-table.json', 'successor-cases.json')
    recomputed: Dict[str, str] = {}
    for fname in required_files:
        fpath = goldens_dir / fname
        if not fpath.exists():
            errors.append(f"Missing frozen artifact: {fpath}")
            continue
        digest = hashlib.sha256(fpath.read_bytes()).hexdigest()
        recomputed[fname] = digest
        if declared_hashes.get(fname) != digest:
            errors.append(
                f"Freeze file_hashes[{fname!r}] mismatch: manifest={declared_hashes.get(fname)!r} != disk={digest!r}"
            )
    combined = hashlib.sha256(
        "\n".join(recomputed[k] for k in sorted(recomputed.keys())).encode('utf-8')
    ).hexdigest() if len(recomputed) == len(required_files) else ''
    if freeze.get('combined_freeze_hash') != combined:
        errors.append(
            f"Freeze combined_freeze_hash mismatch: manifest={freeze.get('combined_freeze_hash')!r} != recomputed={combined!r}"
        )
    return combined, errors


def main():
    parser = argparse.ArgumentParser(description='Run FUSE-1 trip matrix')
    parser.add_argument('--output', type=Path, help='Output JSON path for results bundle')
    parser.add_argument('--strict', action='store_true', help='Exit non-zero on any failure')
    args = parser.parse_args()

    # Paths
    repo_root = Path(__file__).parent.parent
    goldens_dir = repo_root / 'goldens'

    # Load artifacts & independently verify FREEZE.json SHA-256 digests from disk
    print("Loading frozen artifacts...")
    scenarios = load_json(goldens_dir / 'scenarios.json')
    golden_table = load_json(goldens_dir / 'golden-table.json')
    successor_cases = load_json(goldens_dir / 'successor-cases.json')
    freeze = load_json(goldens_dir / 'FREEZE.json')
    recomputed_freeze_hash, freeze_errors = verify_freeze_manifest(goldens_dir, freeze)
    if freeze_errors:
        for err in freeze_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        if args.strict:
            sys.exit(1)

    # Compute engine hash
    engine_hash = compute_engine_hash()
    print(f"Engine hash: {engine_hash}")

    # Run matrix
    print("\nRunning base cells (24 rows × 11 scenarios = 264 cells)...")
    base_results = run_base_cells(scenarios, golden_table, engine_hash)
    print(f"  Base cells: {base_results['passed']}/{base_results['total']} passed")

    print("\nRunning tier repetitions...")
    tier_results = run_tier_repetitions(scenarios, golden_table, engine_hash)
    print(f"  Tier repetitions: {tier_results['passed']}/{tier_results['total']} passed")

    print("\nRunning successor cases...")
    successor_results = run_successor_cases(successor_cases, engine_hash)
    print(f"  Successor cases: {successor_results['passed']}/{successor_results['total']} passed")

    # Assemble result bundle
    result_bundle = {
        'description': 'FUSE-1 trip matrix execution results',
        'spec_version': 'fuse-eval-spec/v1',
        'engine_hash': engine_hash,
        'freeze_hash': recomputed_freeze_hash,
        'enforcement_mode': 'shadow_would_have_tripped',
        'loss_breakers_armed': False,
        'base_cells': base_results,
        'tier_repetitions': tier_results,
        'successor_cases': successor_results,
        'summary': {
            'total_base': base_results['total'],
            'total_tier': tier_results['total'],
            'total_successor': successor_results['total'],
            'passed_base': base_results['passed'],
            'passed_tier': tier_results['passed'],
            'passed_successor': successor_results['passed'],
            'failed_base': base_results['failed'],
            'failed_tier': tier_results['failed'],
            'failed_successor': successor_results['failed']
        }
    }

    # Compute bundle hash
    bundle_canonical = canonical_json(result_bundle)
    bundle_hash = hashlib.sha256(bundle_canonical.encode('utf-8')).hexdigest()
    result_bundle['bundle_hash'] = bundle_hash

    # Write output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result_bundle, f, indent=2, sort_keys=True)
            f.write('\n')
        print(f"\nResults written to {args.output}")

    print(f"\nBundle hash: {bundle_hash}")

    # Exit status
    all_passed = (base_results['failed'] == 0 and
                  tier_results['failed'] == 0 and
                  successor_results['failed'] == 0)

    if args.strict and not all_passed:
        sys.exit(1)

    return 0


if __name__ == '__main__':
    sys.exit(main())
