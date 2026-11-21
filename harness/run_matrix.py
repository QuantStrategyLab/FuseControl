"""Matrix evaluation harness comparing engine outputs against frozen goldens."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.canonical import sha256_bytes, sha256_canonical  # noqa: E402
from engine.evaluate import evaluate  # noqa: E402

TIER_REP_META_KEYS = frozenset(
    {
        "repetition_id",
        "tier",
        "row_id",
        "case",
        "inputs",
        "inputs_override",
        "prior_row_state_override",
        "authorized_events",
    }
)


def deep_merge(base: Any, override: Any) -> Any:
    """Return a fresh deep copy of base with override merged recursively."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = {k: copy.deepcopy(v) for k, v in base.items()}
        for k, v in override.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = deep_merge(merged[k], v)
            else:
                merged[k] = copy.deepcopy(v)
        return merged
    if override is None and base is not None:
        return copy.deepcopy(base) if isinstance(base, dict) else None
    return copy.deepcopy(override)


def strip_reason(obj: Any) -> Any:
    """Recursively remove free-text 'reason' keys while keeping 'reason_class' and all other fields."""
    if isinstance(obj, dict):
        return {k: strip_reason(v) for k, v in obj.items() if k != "reason"}
    if isinstance(obj, list):
        return [strip_reason(item) for item in obj]
    return obj


def json_deep_equal(a: Any, b: Any) -> bool:
    """Strict type-aware structural deep equality (bool != int)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(json_deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(json_deep_equal(x, y) for x, y in zip(a, b))
    return a == b


def file_sha256(path: Path) -> str:
    """Return SHA-256 digest of a file's raw bytes."""
    return sha256_bytes(path.read_bytes())


def compute_engine_hash(engine_dir: Path) -> str:
    """Compute a deterministic SHA-256 hash over sorted engine/*.py files."""
    manifest = [
        [
            p.relative_to(REPO_ROOT).as_posix(),
            sha256_bytes(p.read_bytes()),
        ]
        for p in sorted(engine_dir.glob("*.py"))
    ]
    return sha256_canonical(manifest)


def run_matrix(label: str) -> dict[str, Any]:
    """Execute the 264-cell base matrix and 42 tier repetitions and build the result bundle."""
    fixtures_path = REPO_ROOT / "goldens" / "scenario_fixtures.json"
    golden_path = REPO_ROOT / "goldens" / "golden_table.json"

    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    golden_table = json.loads(golden_path.read_text(encoding="utf-8"))

    spec_version = golden_table["spec_version"]
    engine_hash = compute_engine_hash(REPO_ROOT / "engine")
    session = "2026-01-02"
    as_of = "2026-01-02T21:00:00Z"
    mode = "shadow_would_have_tripped"

    baseline_inputs = fixtures["baseline"]
    baseline_prior = fixtures["baseline_prior_row_state"]
    baseline_events = fixtures.get("baseline_authorized_events", [])
    scenario_fixtures = fixtures["scenarios"]

    base_passed = 0
    base_failed = 0
    base_failures: list[dict[str, Any]] = []
    per_scenario: dict[str, Any] = {}

    eff_passed = 0
    eff_failed = 0
    eff_failures: list[dict[str, Any]] = []

    envelope_ref: dict[str, Any] | None = None

    for scenario_name, scenario_golden in golden_table["scenarios"].items():
        fixture_entry = scenario_fixtures[scenario_name]
        merged_inputs = deep_merge(
            baseline_inputs, fixture_entry.get("inputs_override", {})
        )
        merged_prior = deep_merge(
            baseline_prior, fixture_entry.get("prior_row_state_override", {})
        )
        events = copy.deepcopy(
            fixture_entry.get("authorized_events", baseline_events)
        )
        policy_hash = (merged_inputs.get("policy") or {}).get("registered_hash", "")

        res = evaluate(
            spec_version,
            engine_hash,
            policy_hash,
            session,
            as_of,
            mode,
            merged_inputs,
            merged_prior,
            events,
        )
        rows_by_id, effective_state_by_scope, _next_row_state = res
        envelope = res.to_envelope()
        if envelope_ref is None:
            envelope_ref = {
                "enforcement_mode": envelope["enforcement_mode"],
                "loss_breakers_armed": envelope["loss_breakers_armed"],
                "kelly_applied": envelope["kelly_applied"],
                "orders_placed": envelope["orders_placed"],
            }

        expected_cells = scenario_golden["cells"]
        if set(rows_by_id.keys()) != set(expected_cells.keys()):
            raise AssertionError(
                f"Row ID mismatch in scenario {scenario_name!r}: "
                f"missing={sorted(set(expected_cells) - set(rows_by_id))}, "
                f"extra={sorted(set(rows_by_id) - set(expected_cells))}"
            )

        envelope_match = all(
            envelope[k] == scenario_golden[k]
            for k in (
                "enforcement_mode",
                "loss_breakers_armed",
                "kelly_applied",
                "orders_placed",
            )
        )

        expected_eff = scenario_golden["effective_state_by_scope"]
        eff_match = json_deep_equal(effective_state_by_scope, expected_eff)
        if eff_match:
            eff_passed += 1
        else:
            eff_failed += 1
            eff_failures.append(
                {
                    "scenario": scenario_name,
                    "expected": expected_eff,
                    "actual": effective_state_by_scope,
                }
            )

        scen_passed = 0
        scen_failed = 0
        for row_id, expected_cell in expected_cells.items():
            exp_cmp = strip_reason(expected_cell)
            act_cmp = strip_reason(rows_by_id[row_id])
            if json_deep_equal(act_cmp, exp_cmp):
                scen_passed += 1
                base_passed += 1
            else:
                scen_failed += 1
                base_failed += 1
                base_failures.append(
                    {
                        "scenario": scenario_name,
                        "row": row_id,
                        "expected": exp_cmp,
                        "actual": act_cmp,
                    }
                )

        per_scenario[scenario_name] = {
            "passed": scen_passed,
            "failed": scen_failed,
            "total": scen_passed + scen_failed,
            "effective_state_match": eff_match,
            "effective_state_expected": expected_eff,
            "effective_state_actual": effective_state_by_scope,
            "envelope_match": envelope_match,
        }

    tier_cells = golden_table["tier_repetitions"]["cells"]
    tier_passed = 0
    tier_failed = 0
    tier_failures: list[dict[str, Any]] = []

    for rep in tier_cells:
        merged_inputs = deep_merge(
            baseline_inputs, rep.get("inputs_override", {})
        )
        merged_prior = deep_merge(
            baseline_prior, rep.get("prior_row_state_override", {})
        )
        events = copy.deepcopy(rep.get("authorized_events", baseline_events))
        policy_hash = (merged_inputs.get("policy") or {}).get("registered_hash", "")

        rows_by_id, _eff, _nxt = evaluate(
            spec_version,
            engine_hash,
            policy_hash,
            session,
            as_of,
            mode,
            merged_inputs,
            merged_prior,
            events,
        )
        row_id = rep["row_id"]
        expected_cell = {
            k: v for k, v in rep.items() if k not in TIER_REP_META_KEYS
        }
        exp_cmp = strip_reason(expected_cell)
        act_cmp = strip_reason(rows_by_id[row_id])

        if json_deep_equal(act_cmp, exp_cmp):
            tier_passed += 1
        else:
            tier_failed += 1
            tier_failures.append(
                {
                    "repetition_id": rep["repetition_id"],
                    "tier": rep["tier"],
                    "row": row_id,
                    "case": rep["case"],
                    "expected": exp_cmp,
                    "actual": act_cmp,
                }
            )

    assert envelope_ref is not None
    return {
        "label": label,
        "spec_version": spec_version,
        "engine_hash": engine_hash,
        "code_hash": engine_hash,
        "observation_class": "synthetic",
        "enforcement_mode": envelope_ref["enforcement_mode"],
        "loss_breakers_armed": envelope_ref["loss_breakers_armed"],
        "kelly_applied": envelope_ref["kelly_applied"],
        "orders_placed": envelope_ref["orders_placed"],
        "golden_table_sha256": file_sha256(golden_path),
        "scenario_fixtures_sha256": file_sha256(fixtures_path),
        "passed": base_passed,
        "failed": base_failed,
        "total": base_passed + base_failed,
        "effective_state_by_scope": {
            "passed": eff_passed,
            "failed": eff_failed,
            "total": eff_passed + eff_failed,
            "failures": eff_failures,
        },
        "per_scenario": per_scenario,
        "failures": base_failures,
        "tier_repetitions": {
            "passed": tier_passed,
            "failed": tier_failed,
            "total": tier_passed + tier_failed,
            "failures": tier_failures,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run FUSE-1 matrix evaluation against frozen goldens."
    )
    parser.add_argument(
        "--label",
        default="unlabeled",
        help="Label stored in the output result bundle.",
    )
    parser.add_argument(
        "--output",
        default="results/matrix_result.json",
        help="Output JSON path (relative to repo root if relative).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any base cell, scope state, or tier repetition fails.",
    )
    args = parser.parse_args(argv)

    bundle = run_matrix(args.label)
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    eff = bundle["effective_state_by_scope"]
    tr = bundle["tier_repetitions"]
    print(
        f"label={bundle['label']} "
        f"base={bundle['passed']}/{bundle['total']} "
        f"effective_states={eff['passed']}/{eff['total']} "
        f"tier_repetitions={tr['passed']}/{tr['total']} "
        f"output={out_path.relative_to(REPO_ROOT)}"
    )

    if args.strict and (
        bundle["failed"] > 0 or eff["failed"] > 0 or tr["failed"] > 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
