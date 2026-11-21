"""Acceptance batteries for the FUSE-1 reference engine (Phase F step 2)."""

from __future__ import annotations

import argparse
import ast
import copy
import inspect
import io
import json
import re
import subprocess
import sys
import tokenize
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine import ROW_IDS, evaluate  # noqa: E402
from engine.canonical import canonical_json, sha256_bytes, sha256_canonical  # noqa: E402
from harness.run_matrix import compute_engine_hash, deep_merge  # noqa: E402

EXPECTED_ROW_IDS: frozenset[str] = frozenset(
    {
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
    }
)

VALID_STATES: frozenset[str] = frozenset(
    {"NORMAL", "NO-NEW-RISK", "DE-RISK", "ORDER-UNKNOWN", "HALT"}
)

PINNED_EVAL_PARAMS: tuple[str, ...] = (
    "spec_version",
    "engine_hash",
    "policy_hash",
    "session",
    "as_of",
    "mode",
    "validated_inputs",
    "prior_row_state",
    "authorized_events",
)

DEFAULT_SESSION = "2026-01-02"
DEFAULT_AS_OF = "2026-01-02T21:00:00Z"
DEFAULT_MODE = "shadow_would_have_tripped"


def compute_engine_bytes_sha256(engine_dir: Path) -> str:
    """Compute SHA-256 over raw bytes of sorted engine/*.py files."""
    combined = b"".join(p.read_bytes() for p in sorted(engine_dir.glob("*.py")))
    return sha256_bytes(combined)


def load_json(rel_path: str) -> dict[str, Any]:
    """Load a JSON file relative to REPO_ROOT."""
    return json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))


def load_fixtures() -> dict[str, Any]:
    """Load frozen scenario fixtures."""
    return load_json("goldens/scenario_fixtures.json")


def load_spec() -> dict[str, Any]:
    """Load machine-readable FUSE-1 spec."""
    return load_json("spec/fuse_eval_spec.json")


def load_disposition_register() -> dict[str, Any]:
    """Load FUSE-1 disposition register."""
    return load_json("spec/disposition_register.json")


def load_golden_table() -> dict[str, Any]:
    """Load frozen golden table."""
    return load_json("goldens/golden_table.json")


def strip_label(obj: Any) -> Any:
    """Recursively remove 'label' keys from dicts while preserving everything else."""
    if isinstance(obj, dict):
        return {k: strip_label(v) for k, v in obj.items() if k != "label"}
    if isinstance(obj, list):
        return [strip_label(item) for item in obj]
    return obj


def _make_result(
    battery_id: str,
    passed: bool,
    evidence_counts: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    """Build a uniform per-battery result record."""
    return {
        "id": battery_id,
        "passed": passed,
        "evidence_counts": evidence_counts,
        "details": details,
    }


def battery_determinism() -> dict[str, Any]:
    """(1) determinism (F1-A05): 3 fresh-import matrix runs match committed bundle hash."""
    run_script = (
        "import json, sys; "
        "from engine.canonical import sha256_canonical; "
        "from harness.run_matrix import run_matrix; "
        "strip = lambda o: {k: strip(v) for k, v in o.items() if k != 'label'} "
        "if isinstance(o, dict) else ([strip(x) for x in o] if isinstance(o, list) else o); "
        "b = run_matrix(sys.argv[1]); "
        "print(json.dumps({"
        "'hash': sha256_canonical(strip(b)), "
        "'passed': b['passed'], 'total': b['total'], "
        "'eff_passed': b['effective_state_by_scope']['passed'], "
        "'tier_passed': b['tier_repetitions']['passed']"
        "}))"
    )
    run_hashes: list[str] = []
    per_run_counts: list[dict[str, Any]] = []
    for idx in range(1, 4):
        proc = subprocess.run(
            [sys.executable, "-c", run_script, f"determinism-run-{idx}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout.strip())
        run_hashes.append(payload["hash"])
        per_run_counts.append(
            {
                "run": idx,
                "hash": payload["hash"],
                "passed": payload["passed"],
                "total": payload["total"],
                "eff_passed": payload["eff_passed"],
                "tier_passed": payload["tier_passed"],
            }
        )

    committed = load_json("results/matrix_result.json")
    committed_hash = sha256_canonical(strip_label(committed))
    unique_hashes = sorted(set(run_hashes))
    matches_committed = len(unique_hashes) == 1 and run_hashes[0] == committed_hash
    passed = len(run_hashes) == 3 and matches_committed

    return _make_result(
        "F1-A05",
        passed,
        {
            "runs": len(run_hashes),
            "unique_hashes": len(unique_hashes),
            "matches_committed": int(matches_committed),
        },
        {
            "committed_hash": committed_hash,
            "run_hashes": run_hashes,
            "per_run_counts": per_run_counts,
        },
    )


def _run_evaluate(
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
    *,
    spec_version: str = "fuse-eval-spec/v1",
    engine_hash: str | None = None,
    policy_hash: str | None = None,
    session: Any = DEFAULT_SESSION,
    as_of: Any = DEFAULT_AS_OF,
    mode: str = DEFAULT_MODE,
) -> Any:
    """Invoke engine.evaluate with default pinned metadata unless overridden."""
    if engine_hash is None:
        engine_hash = compute_engine_hash(REPO_ROOT / "engine")
    if policy_hash is None:
        if isinstance(validated_inputs, dict) and isinstance(
            validated_inputs.get("policy"), dict
        ):
            policy_hash = str(validated_inputs["policy"].get("registered_hash", ""))
        else:
            policy_hash = ""
    return evaluate(
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


def battery_id_set_equality() -> dict[str, Any]:
    """(2) id_set_equality (F1-A01): spec IDs == engine rows_by_ID == literal 24-ID set."""
    spec = load_spec()
    fixtures = load_fixtures()

    spec_id_list = [row["id"] for row in spec["rows"]]
    spec_ids = set(spec_id_list)
    spec_duplicates = len(spec_id_list) - len(spec_ids)

    res = _run_evaluate(
        copy.deepcopy(fixtures["baseline"]),
        copy.deepcopy(fixtures["baseline_prior_row_state"]),
        copy.deepcopy(fixtures.get("baseline_authorized_events", [])),
        spec_version=spec["spec_version"],
    )
    rows_by_id, _eff, _nxt = res
    engine_ids = set(rows_by_id.keys())
    engine_row_ids_const = list(ROW_IDS)
    engine_const_ids = set(engine_row_ids_const)

    passed = (
        spec_ids == engine_ids == EXPECTED_ROW_IDS
        and engine_const_ids == EXPECTED_ROW_IDS
        and len(spec_id_list) == 24
        and len(engine_row_ids_const) == 24
        and spec_duplicates == 0
    )

    return _make_result(
        "F1-A01",
        passed,
        {
            "expected_count": len(EXPECTED_ROW_IDS),
            "spec_count": len(spec_id_list),
            "spec_unique_count": len(spec_ids),
            "engine_rows_by_id_count": len(engine_ids),
            "engine_row_ids_const_count": len(engine_row_ids_const),
            "spec_duplicates": spec_duplicates,
        },
        {
            "expected_ids": sorted(EXPECTED_ROW_IDS),
            "spec_missing_from_expected": sorted(EXPECTED_ROW_IDS - spec_ids),
            "spec_extra_beyond_expected": sorted(spec_ids - EXPECTED_ROW_IDS),
            "engine_missing_from_expected": sorted(EXPECTED_ROW_IDS - engine_ids),
            "engine_extra_beyond_expected": sorted(engine_ids - EXPECTED_ROW_IDS),
            "engine_const_matches": engine_const_ids == EXPECTED_ROW_IDS,
        },
    )


def battery_spec_linter() -> dict[str, Any]:
    """(3) spec_linter (F1-A02): all 24 spec rows carry all 7 required non-empty fields."""
    spec = load_spec()
    required_fields = (
        "trigger",
        "required_inputs",
        "action",
        "state_contribution",
        "kind",
        "scope",
        "clearing",
    )
    rows = spec["rows"]
    missing_fields: list[dict[str, str]] = []

    for row in rows:
        row_id = str(row.get("id", "<unknown>"))
        for field in required_fields:
            val = row.get(field)
            if field == "required_inputs":
                valid = (
                    isinstance(val, list)
                    and len(val) > 0
                    and all(isinstance(x, str) and bool(x.strip()) for x in val)
                )
            else:
                valid = isinstance(val, str) and bool(val.strip())
            if not valid:
                missing_fields.append({"row_id": row_id, "field": field})

    rows_checked = len(rows)
    missing_count = len(missing_fields)
    passed = rows_checked == 24 and missing_count == 0

    return _make_result(
        "F1-A02",
        passed,
        {
            "rows_checked": rows_checked,
            "fields_per_row": len(required_fields),
            "total_field_checks": rows_checked * len(required_fields),
            "missing_count": missing_count,
        },
        {
            "required_fields": list(required_fields),
            "missing_fields": missing_fields,
        },
    )


_PRETRADE_KEY_MAP: dict[str, str] = {
    "symbol_whitelisted": "whitelisted_symbol",
    "account_whitelisted": "whitelisted_account",
    "long_only": "long_only",
    "within_settled_cash": "within_settled_cash",
    "within_max_order_size": "size_within_max",
    "within_max_orders_per_session": "session_orders_within_max",
    "within_max_turnover_per_session": "turnover_within_max",
}


def _fail_closed_variants_for_field(
    baseline: dict[str, Any],
    row_id: str,
    field_name: str,
    seen_containers: set[tuple[str, str]],
) -> list[tuple[str, dict[str, Any], list[Any] | None]]:
    """Build baseline variants (missing, none, and stale for data_inputs) for a spec required_input."""
    variants: list[tuple[str, dict[str, Any], list[Any] | None]] = []

    def add_dict_key_variants(
        path: tuple[str, ...],
        key: str,
        label_prefix: str = "",
        base_override: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        for mode in ("missing", "none"):
            inp = copy.deepcopy(baseline)
            if base_override is not None:
                base_override(inp)
            target: Any = inp
            for part in path:
                target = target[part]
            if mode == "missing":
                target.pop(key, None)
            else:
                target[key] = None
            vname = f"{label_prefix}{mode}" if label_prefix else mode
            variants.append((vname, inp, []))

    if field_name in ("sizing.max_loss_cap", "sizing.proposed_exposure"):
        add_dict_key_variants(("sizing",), field_name.split(".", 1)[1])
    elif field_name in ("joint.joint_exposure", "joint.joint_cap"):
        add_dict_key_variants(("joint",), field_name.split(".", 1)[1])
    elif field_name in ("loss.drawdown_amount", "loss.session_loss_amount"):
        add_dict_key_variants(("loss",), field_name.split(".", 1)[1])
    elif field_name == "tier.D":
        add_dict_key_variants((), "tier", "tier_")
        add_dict_key_variants((), "bankroll", "bankroll_")
    elif field_name in (
        "market.mwcb_level",
        "market.clean_session",
        "market.index_session_fall",
    ):
        add_dict_key_variants(("market",), field_name.split(".", 1)[1])
    elif field_name in (
        "fund.tracking_dev_1s_pp",
        "fund.tracking_dev_5s_pp",
        "fund.forecast_vol",
        "fund.long_run_vol",
        "fund.decay_shortfall_60s",
        "fund.decay_predicted_60s",
    ):
        add_dict_key_variants(("funds", "TQQQ"), field_name.split(".", 1)[1])
    elif field_name.startswith("fund.carrying_cost."):
        add_dict_key_variants(
            ("funds", "TQQQ", "carrying_cost"), field_name.split(".", 2)[2]
        )
    elif field_name.startswith("fund.quote."):
        add_dict_key_variants(("funds", "TQQQ", "quote"), field_name.split(".", 2)[2])
    elif field_name.startswith("fund.corporate_action."):
        subkey = field_name.split(".", 2)[2]
        if (row_id, "fund.corporate_action") not in seen_containers:
            seen_containers.add((row_id, "fund.corporate_action"))
            inp = copy.deepcopy(baseline)
            inp["funds"]["TQQQ"].pop("corporate_action", None)
            variants.append(("container_key_missing", inp, []))

            inp_null = copy.deepcopy(baseline)
            inp_null["funds"]["TQQQ"]["corporate_action"] = None
            variants.append(("container_null", inp_null, []))

            inp_empty = copy.deepcopy(baseline)
            inp_empty["funds"]["TQQQ"]["corporate_action"] = {}
            variants.append(("empty_container", inp_empty, []))
        reconciled_ca = {
            "type": "split",
            "announced": True,
            "detected_in_price": True,
            "ledger_adjusted": True,
            "reconciles_exactly": True,
        }

        def set_ca(inp: dict[str, Any]) -> None:
            inp["funds"]["TQQQ"]["corporate_action"] = dict(reconciled_ca)

        add_dict_key_variants(
            ("funds", "TQQQ", "corporate_action"),
            subkey,
            label_prefix="reconciled_ca_",
            base_override=set_ca,
        )
        if subkey == "type":
            inp_bad_type = copy.deepcopy(baseline)
            inp_bad_type["funds"]["TQQQ"]["corporate_action"] = {
                **reconciled_ca,
                "type": "unknown_action",
            }
            variants.append(("reconciled_ca_invalid_type", inp_bad_type, []))
    elif field_name == "fund.fund_event":
        inp = copy.deepcopy(baseline)
        inp["funds"]["TQQQ"].pop("fund_event", None)
        variants.append(("container_key_missing", inp, []))
        inp_null = copy.deepcopy(baseline)
        inp_null["funds"]["TQQQ"]["fund_event"] = None
        variants.append(("container_null", inp_null, []))
    elif field_name.startswith("data_inputs."):
        subkey = field_name.split(".", 1)[1]
        if (row_id, "data_inputs") not in seen_containers:
            seen_containers.add((row_id, "data_inputs"))
            add_dict_key_variants((), "data_inputs", "container_")
        for source_name in baseline["data_inputs"]:
            add_dict_key_variants(
                ("data_inputs", source_name),
                subkey,
                label_prefix=f"{source_name}_",
            )
            if subkey == "age_sessions":
                stale_inp = copy.deepcopy(baseline)
                stale_inp["data_inputs"][source_name]["age_sessions"] = 5
                variants.append((f"{source_name}_stale_age_5", stale_inp, []))
    elif field_name in ("calendar.session_state", "calendar.exchange_agrees"):
        add_dict_key_variants(("calendar",), field_name.split(".", 1)[1])
    elif field_name in (
        "broker_record.positions_beyond_tolerance",
        "broker_record.cash_beyond_tolerance",
    ):
        add_dict_key_variants(("broker_record",), field_name.split(".", 1)[1])
    elif field_name.startswith("orders.pending."):
        subkey = field_name.split(".", 2)[2]
        if (row_id, "orders.pending") not in seen_containers:
            seen_containers.add((row_id, "orders.pending"))
            inp = copy.deepcopy(baseline)
            inp["orders"].pop("pending", None)
            variants.append(("container_key_missing", inp, []))
            inp_null = copy.deepcopy(baseline)
            inp_null["orders"]["pending"] = None
            variants.append(("container_null", inp_null, []))
        resolved_order = {
            "symbol": "TQQQ",
            "terminal_status": "filled",
            "timed_out": True,
        }

        def set_order(inp: dict[str, Any]) -> None:
            inp["orders"]["pending"] = dict(resolved_order)

        add_dict_key_variants(
            ("orders", "pending"),
            subkey,
            label_prefix="timed_out_order_",
            base_override=set_order,
        )
    elif field_name.startswith("pretrade."):
        subkey = field_name.split(".", 1)[1]
        if subkey == "rejections_this_session":
            add_dict_key_variants(("pretrade",), "rejections_this_session")
        elif subkey == "price_collar":
            inp_missing = copy.deepcopy(baseline)
            inp_missing["pretrade"]["attempted_order"].pop("price_collar", None)
            variants.append(("missing", inp_missing, []))
            inp_none = copy.deepcopy(baseline)
            inp_none["pretrade"]["attempted_order"]["price_collar"] = None
            variants.append(("none", inp_none, []))
        elif subkey in _PRETRADE_KEY_MAP:
            add_dict_key_variants(
                ("pretrade", "attempted_order"), _PRETRADE_KEY_MAP[subkey]
            )
        else:
            raise ValueError(f"Unmapped pretrade required_input: {field_name!r}")
    elif field_name in ("policy.loaded_hash", "policy.registered_hash"):
        add_dict_key_variants(("policy",), field_name.split(".", 1)[1])
    elif field_name in (
        "runtime.silence_seconds",
        "runtime.scheduled_interval_seconds",
    ):
        add_dict_key_variants(("runtime",), field_name.split(".", 1)[1])
    elif field_name == "authorized_events":
        variants.append(("none", copy.deepcopy(baseline), None))
    elif field_name == "change_descriptors":
        inp_omitted = copy.deepcopy(baseline)
        inp_omitted.pop("change_descriptors", None)
        variants.append(("omitted", inp_omitted, []))
        inp_none = copy.deepcopy(baseline)
        inp_none["change_descriptors"] = None
        variants.append(("none", inp_none, []))
    else:
        raise ValueError(f"Unmapped spec required_input: {field_name!r}")

    return variants


BY_DESIGN_EXCLUSIONS: dict[tuple[str, str, str], tuple[str, str]] = {
    ("V2", "fund.corporate_action.type", "container_null"): (
        "corporate_action_null",
        "corporate_action=null IS the benign 'no corporate action' sentinel in the fixture model, not a missing market input.",
    ),
    ("V2", "fund.corporate_action.type", "container_key_missing"): (
        "corporate_action_null",
        "Absent corporate_action key resolves to null, which IS the benign 'no corporate action' sentinel in the fixture model.",
    ),
    ("V3", "fund.fund_event", "container_null"): (
        "fund_event_null",
        "fund_event=null IS the benign 'no fund event' sentinel in the fixture model, not a missing market input.",
    ),
    ("V3", "fund.fund_event", "container_key_missing"): (
        "fund_event_null",
        "Absent fund_event key resolves to null, which IS the benign 'no fund event' sentinel in the fixture model.",
    ),
    ("O4", "orders.pending.symbol", "container_null"): (
        "orders_pending_null",
        "orders.pending=null IS the benign 'no pending order' sentinel in the fixture model; omitting the pending key still fails closed.",
    ),
    ("O9", "change_descriptors", "omitted"): (
        "change_descriptors_omitted",
        "Omitting change_descriptors IS the benign 'no parameter changes' sentinel in the fixture model, not a missing market input.",
    ),
    ("O9", "change_descriptors", "none"): (
        "change_descriptors_omitted",
        "change_descriptors=null IS the benign 'no parameter changes' sentinel in the fixture model, not a missing market input.",
    ),
    ("O8", "authorized_events", "none"): (
        "authorized_events_structural",
        "authorized_events is a structural C-FUSE-EVAL signature argument (not a market input); null means no owner kill-switch command issued.",
    ),
    ("O9", "authorized_events", "none"): (
        "authorized_events_structural",
        "authorized_events is a structural C-FUSE-EVAL signature argument (not a market input); null means no owner cards when no parameter changed.",
    ),
}


def _check_fail_closed_explicit_assertions(
    baseline: dict[str, Any],
    prior: dict[str, Any],
    spec_version: str,
    engine_hash: str,
    policy_hash: str,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Run explicit regression assertions for L0 fail-closed and V2 malformed container fixes."""
    assertions: dict[str, dict[str, Any]] = {}

    l0_cases: list[tuple[str, Callable[[dict[str, Any]], None], dict[str, Any]]] = [
        (
            "L0_missing_joint_exposure",
            lambda inp: inp["joint"].pop("joint_exposure", None),
            {"exposure_cap": "0.50", "proposed_exposure": "0.35", "joint_exposure": None},
        ),
        (
            "L0_none_joint_exposure",
            lambda inp: inp["joint"].__setitem__("joint_exposure", None),
            {"exposure_cap": "0.50", "proposed_exposure": "0.35", "joint_exposure": None},
        ),
        (
            "L0_invalid_joint_exposure",
            lambda inp: inp["joint"].__setitem__("joint_exposure", "bad"),
            {"exposure_cap": "0.50", "proposed_exposure": "0.35", "joint_exposure": None},
        ),
        (
            "L0_missing_max_loss_cap",
            lambda inp: inp["sizing"].pop("max_loss_cap", None),
            {"exposure_cap": None, "proposed_exposure": "0.35", "joint_exposure": "0.35"},
        ),
        (
            "L0_invalid_proposed_exposure",
            lambda inp: inp["sizing"].__setitem__("proposed_exposure", "-0.1"),
            {"exposure_cap": "0.50", "proposed_exposure": None, "joint_exposure": "0.35"},
        ),
    ]

    for name, mutator, expected_fields in l0_cases:
        inp = copy.deepcopy(baseline)
        mutator(inp)
        rows, _eff, _nxt = _run_evaluate(
            inp,
            copy.deepcopy(prior),
            [],
            spec_version=spec_version,
            engine_hash=engine_hash,
            policy_hash=policy_hash,
        )
        cell = rows["L0"]
        cap_out = cell.get("cap_output", {})
        checks = {
            "state_normal": cell["state"] == "NORMAL",
            "would_have_tripped_true": cell["would_have_tripped"] is True,
            "latched_false": cell["latched"] is False,
            "reason_class_missing_input": cell["reason_class"] == "missing_input",
            "exposure_cap_eq": cap_out.get("exposure_cap") == expected_fields["exposure_cap"],
            "proposed_exposure_eq": cap_out.get("proposed_exposure")
            == expected_fields["proposed_exposure"],
            "joint_exposure_eq": cap_out.get("joint_exposure")
            == expected_fields["joint_exposure"],
            "effective_capped_exposure_null": cap_out.get("effective_capped_exposure")
            is None,
            "increases_blocked_true": cap_out.get("increases_blocked") is True,
            "cap_breached_true": cap_out.get("cap_breached") is True,
        }
        assertions[name] = {
            "passed": all(checks.values()),
            "checks": checks,
            "observed": {
                "state": cell["state"],
                "would_have_tripped": cell["would_have_tripped"],
                "reason_class": cell["reason_class"],
                "cap_output": cap_out,
            },
        }

    v2_malformed_cases: list[tuple[str, Any]] = [
        (
            "V2_malformed_missing_type",
            {
                "announced": True,
                "detected_in_price": True,
                "ledger_adjusted": True,
                "reconciles_exactly": True,
            },
        ),
        (
            "V2_malformed_none_type",
            {
                "type": None,
                "announced": True,
                "detected_in_price": True,
                "ledger_adjusted": False,
                "reconciles_exactly": False,
            },
        ),
        (
            "V2_malformed_invalid_type",
            {
                "type": "merger",
                "announced": True,
                "detected_in_price": True,
                "ledger_adjusted": True,
                "reconciles_exactly": True,
            },
        ),
        ("V2_malformed_empty_container", {}),
    ]

    for name, payload in v2_malformed_cases:
        inp = copy.deepcopy(baseline)
        inp["funds"]["TQQQ"]["corporate_action"] = copy.deepcopy(payload)
        rows, eff, _nxt = _run_evaluate(
            inp,
            copy.deepcopy(prior),
            [],
            spec_version=spec_version,
            engine_hash=engine_hash,
            policy_hash=policy_hash,
        )
        cell = rows["V2"]
        tqqq = cell["by_fund"]["TQQQ"]
        soxl = cell["by_fund"]["SOXL"]
        checks = {
            "cell_state_halt": cell["state"] == "HALT",
            "cell_would_have_tripped_true": cell["would_have_tripped"] is True,
            "cell_latched_false": cell["latched"] is False,
            "cell_reason_class_missing_input": cell["reason_class"] == "missing_input",
            "tqqq_state_halt": tqqq["state"] == "HALT",
            "tqqq_would_have_tripped_true": tqqq["would_have_tripped"] is True,
            "tqqq_latched_false": tqqq["latched"] is False,
            "tqqq_reason_class_missing_input": tqqq["reason_class"] == "missing_input",
            "soxl_state_normal": soxl["state"] == "NORMAL",
            "eff_fund_tqqq_halt": eff["fund:TQQQ"] == "HALT",
            "eff_fund_soxl_normal": eff["fund:SOXL"] == "NORMAL",
            "eff_account_normal": eff["account"] == "NORMAL",
        }
        assertions[name] = {
            "passed": all(checks.values()),
            "checks": checks,
            "observed": {
                "V2_state": cell["state"],
                "V2_latched": cell["latched"],
                "V2_reason_class": cell["reason_class"],
                "V2_TQQQ": tqqq,
                "effective_state_by_scope": eff,
            },
        }

    inp_null = copy.deepcopy(baseline)
    inp_null["funds"]["TQQQ"]["corporate_action"] = None
    rows_null, eff_null, _nxt_null = _run_evaluate(
        inp_null,
        copy.deepcopy(prior),
        [],
        spec_version=spec_version,
        engine_hash=engine_hash,
        policy_hash=policy_hash,
    )
    cell_null = rows_null["V2"]
    tqqq_null = cell_null["by_fund"]["TQQQ"]
    null_checks = {
        "cell_state_normal": cell_null["state"] == "NORMAL",
        "cell_would_have_tripped_false": cell_null["would_have_tripped"] is False,
        "cell_latched_false": cell_null["latched"] is False,
        "cell_reason_class_none": cell_null["reason_class"] == "none",
        "tqqq_state_normal": tqqq_null["state"] == "NORMAL",
        "eff_fund_tqqq_normal": eff_null["fund:TQQQ"] == "NORMAL",
    }
    assertions["V2_null_corporate_action_benign"] = {
        "passed": all(null_checks.values()),
        "checks": null_checks,
        "observed": {
            "V2_state": cell_null["state"],
            "V2_latched": cell_null["latched"],
            "V2_reason_class": cell_null["reason_class"],
            "V2_TQQQ": tqqq_null,
        },
    }

    return assertions, all(item["passed"] for item in assertions.values())


def battery_fail_closed() -> dict[str, Any]:
    """(4) fail_closed (F1-A06): missing/None/stale/malformed required inputs fail closed with explicit by-design exclusions."""
    spec = load_spec()
    fixtures = load_fixtures()
    baseline = fixtures["baseline"]
    prior = fixtures["baseline_prior_row_state"]
    policy_hash = baseline["policy"]["registered_hash"]
    engine_hash = compute_engine_hash(REPO_ROOT / "engine")

    seen_containers: set[tuple[str, str]] = set()
    variants_tested = 0
    fields_covered = 0
    fail_closed_tripped_count = 0
    by_design_exclusions: list[dict[str, Any]] = []
    by_design_exclusion_violations: list[dict[str, Any]] = []
    reconciled_auto_cleared_variants: list[dict[str, Any]] = []
    silent_passes: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    for row in spec["rows"]:
        row_id = row["id"]
        for field_name in row["required_inputs"]:
            fields_covered += 1
            variants = _fail_closed_variants_for_field(
                baseline, row_id, field_name, seen_containers
            )
            for variant_name, inp, ev in variants:
                variants_tested += 1
                try:
                    rows_by_id, _eff, _nxt = _run_evaluate(
                        inp,
                        copy.deepcopy(prior),
                        ev,
                        spec_version=spec["spec_version"],
                        engine_hash=engine_hash,
                        policy_hash=policy_hash,
                    )
                except Exception as exc:  # noqa: BLE001
                    exceptions.append(
                        {
                            "row_id": row_id,
                            "field": field_name,
                            "variant": variant_name,
                            "exception": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue

                cell = rows_by_id[row_id]
                key = (row_id, field_name, variant_name)

                if key in BY_DESIGN_EXCLUSIONS:
                    category, rationale = BY_DESIGN_EXCLUSIONS[key]
                    is_benign = (
                        cell["state"] == "NORMAL"
                        and cell["would_have_tripped"] is False
                        and cell["latched"] is False
                        and cell["reason_class"] == "none"
                    )
                    record = {
                        "row_id": row_id,
                        "field": field_name,
                        "variant": variant_name,
                        "category": category,
                        "state": cell["state"],
                        "would_have_tripped": cell["would_have_tripped"],
                        "reason_class": cell["reason_class"],
                        "rationale": rationale,
                    }
                    by_design_exclusions.append(record)
                    if not is_benign:
                        by_design_exclusion_violations.append(record)
                elif (
                    cell["would_have_tripped"] is True
                    and cell["reason_class"] != "none"
                ):
                    fail_closed_tripped_count += 1
                elif row_id == "V2" and cell["reason_class"] == "reconciled":
                    reconciled_auto_cleared_variants.append(
                        {
                            "row_id": row_id,
                            "field": field_name,
                            "variant": variant_name,
                            "state": cell["state"],
                            "would_have_tripped": cell["would_have_tripped"],
                            "reason_class": cell["reason_class"],
                            "rationale": "V2 corporate action carries valid type='split' with ledger_adjusted=True and reconciles_exactly=True, triggering the documented auto-clear branch.",
                        }
                    )
                else:
                    silent_passes.append(
                        {
                            "row_id": row_id,
                            "field": field_name,
                            "variant": variant_name,
                            "state": cell["state"],
                            "would_have_tripped": cell["would_have_tripped"],
                            "reason_class": cell["reason_class"],
                        }
                    )

    explicit_assertions, explicit_ok = _check_fail_closed_explicit_assertions(
        baseline,
        prior,
        spec["spec_version"],
        engine_hash,
        policy_hash,
    )

    required_exclusion_categories = {
        "corporate_action_null",
        "fund_event_null",
        "orders_pending_null",
        "change_descriptors_omitted",
        "authorized_events_structural",
    }
    observed_exclusion_categories = {
        entry["category"] for entry in by_design_exclusions
    }
    exclusions_complete = (
        observed_exclusion_categories == required_exclusion_categories
        and len(by_design_exclusions) == len(BY_DESIGN_EXCLUSIONS)
        and len(by_design_exclusion_violations) == 0
    )

    silent_pass_count = len(silent_passes)
    exception_count = len(exceptions)
    passed = (
        silent_pass_count == 0
        and exception_count == 0
        and explicit_ok
        and exclusions_complete
    )

    return _make_result(
        "F1-A06",
        passed,
        {
            "required_input_entries_covered": fields_covered,
            "variants_tested": variants_tested,
            "fail_closed_tripped_count": fail_closed_tripped_count,
            "by_design_exclusion_count": len(by_design_exclusions),
            "reconciled_auto_cleared_count": len(reconciled_auto_cleared_variants),
            "silent_pass_count": silent_pass_count,
            "exception_count": exception_count,
            "explicit_assertions_passed": sum(
                1 for item in explicit_assertions.values() if item["passed"]
            ),
            "explicit_assertions_total": len(explicit_assertions),
        },
        {
            "explicit_assertions": explicit_assertions,
            "by_design_exclusions": by_design_exclusions,
            "by_design_exclusion_violations": by_design_exclusion_violations,
            "reconciled_auto_cleared_variants": reconciled_auto_cleared_variants,
            "silent_passes": silent_passes,
            "exceptions": exceptions,
        },
    )


def battery_persistence() -> dict[str, Any]:
    """(5) persistence (F1-A07): latched L2 & O3 + mid-count V4 survive serialize/restore and scenarios."""
    spec = load_spec()
    fixtures = load_fixtures()
    baseline = fixtures["baseline"]
    prior = fixtures["baseline_prior_row_state"]
    policy_hash = baseline["policy"]["registered_hash"]
    engine_hash = compute_engine_hash(REPO_ROOT / "engine")

    # Session 1: trip L2 (2D/3 = 10000 < D=15000), O3 (positions beyond tolerance), V4 TQQQ (forecast_vol >= 2*0.24)
    trip_inputs = copy.deepcopy(baseline)
    trip_inputs["loss"]["drawdown_amount"] = "10000"
    trip_inputs["broker_record"]["positions_beyond_tolerance"] = True
    trip_inputs["funds"]["TQQQ"]["forecast_vol"] = "0.60"

    _r1, _e1, state = _run_evaluate(
        trip_inputs,
        copy.deepcopy(prior),
        [],
        spec_version=spec["spec_version"],
        engine_hash=engine_hash,
        policy_hash=policy_hash,
        session="2026-01-02",
        as_of="2026-01-02T21:00:00Z",
    )

    # Sessions 2-5: 4 calm sessions to advance V4 TQQQ below_threshold_sessions 0 -> 4 (mid-count < 10)
    for step_idx in range(1, 5):
        day = f"2026-01-0{2 + step_idx}"
        _r, _e, state = _run_evaluate(
            copy.deepcopy(baseline),
            state,
            [],
            spec_version=spec["spec_version"],
            engine_hash=engine_hash,
            policy_hash=policy_hash,
            session=day,
            as_of=f"{day}T21:00:00Z",
        )

    serialized = canonical_json(state)
    restored = json.loads(serialized)
    roundtrip_equal = restored == state and canonical_json(restored) == serialized

    pre_l2_latched = restored["L2"]["latched"] is True
    pre_o3_latched = restored["O3"]["latched"] is True
    pre_v4_active = restored["V4"]["by_fund"]["TQQQ"]["active"] is True
    pre_v4_count = restored["V4"]["by_fund"]["TQQQ"]["below_threshold_sessions"] == 4
    preconditions_ok = (
        roundtrip_equal
        and pre_l2_latched
        and pre_o3_latched
        and pre_v4_active
        and pre_v4_count
    )

    scenario_names = ("restart", "deposit", "withdrawal", "split", "tier_change")
    per_scenario: dict[str, dict[str, Any]] = {}
    scenarios_passed = 0

    for sname in scenario_names:
        fx = fixtures["scenarios"][sname]
        merged_inputs = deep_merge(baseline, fx.get("inputs_override", {}))
        events = copy.deepcopy(fx.get("authorized_events", []))
        scen_policy_hash = (merged_inputs.get("policy") or {}).get(
            "registered_hash", policy_hash
        )

        rows, _eff, nxt = _run_evaluate(
            merged_inputs,
            copy.deepcopy(restored),
            events,
            spec_version=spec["spec_version"],
            engine_hash=engine_hash,
            policy_hash=scen_policy_hash,
            session="2026-01-07",
            as_of="2026-01-07T21:00:00Z",
        )

        v4_tqqq_cell = rows["V4"]["by_fund"]["TQQQ"]
        v4_tqqq_next = nxt["V4"]["by_fund"]["TQQQ"]
        checks = {
            "l2_row_latched": rows["L2"]["latched"] is True,
            "l2_next_latched": nxt["L2"]["latched"] is True,
            "l2_latch_reason_eq": nxt["L2"]["latch_reason"]
            == restored["L2"]["latch_reason"],
            "o3_row_latched": rows["O3"]["latched"] is True,
            "o3_next_latched": nxt["O3"]["latched"] is True,
            "o3_latch_reason_eq": nxt["O3"]["latch_reason"]
            == restored["O3"]["latch_reason"],
            "v4_prior_counter_eq_4": v4_tqqq_cell["prior_below_threshold_sessions"]
            == 4,
            "v4_row_active": v4_tqqq_cell["active"] is True,
            "v4_next_active": v4_tqqq_next["active"] is True,
            "v4_row_counter_eq_5": v4_tqqq_cell["below_threshold_sessions"] == 5,
            "v4_next_counter_eq_5": v4_tqqq_next["below_threshold_sessions"] == 5,
        }
        ok = all(checks.values())
        if ok:
            scenarios_passed += 1
        per_scenario[sname] = {
            "passed": ok,
            "checks": checks,
            "observed": {
                "L2_next": nxt["L2"],
                "O3_next": nxt["O3"],
                "V4_TQQQ_next": v4_tqqq_next,
            },
        }

    passed = preconditions_ok and scenarios_passed == len(scenario_names)
    return _make_result(
        "F1-A07",
        passed,
        {
            "scenarios_checked": len(scenario_names),
            "scenarios_passed": scenarios_passed,
            "roundtrip_equal": roundtrip_equal,
        },
        {
            "preconditions": {
                "roundtrip_equal": roundtrip_equal,
                "pre_l2_latched": pre_l2_latched,
                "pre_o3_latched": pre_o3_latched,
                "pre_v4_active": pre_v4_active,
                "pre_v4_count_4": pre_v4_count,
                "restored_L2": restored["L2"],
                "restored_O3": restored["O3"],
                "restored_V4_TQQQ": restored["V4"]["by_fund"]["TQQQ"],
            },
            "per_scenario": per_scenario,
        },
    )


def build_precedence_fixtures(
    baseline: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Construct the 4 precedence test input fixtures from baseline."""
    f_a = copy.deepcopy(baseline)
    f_a["broker_record"]["positions_beyond_tolerance"] = True
    f_a["orders"]["pending"] = {
        "symbol": "TQQQ",
        "terminal_status": None,
        "timed_out": True,
    }
    f_a["funds"]["TQQQ"]["fund_event"] = "issuer_liquidation_notice"

    f_b = copy.deepcopy(baseline)
    f_b["orders"]["pending"] = {
        "symbol": "TQQQ",
        "terminal_status": None,
        "timed_out": True,
    }
    f_b["loss"]["drawdown_amount"] = "10000"

    f_c = copy.deepcopy(baseline)
    f_c["funds"]["TQQQ"]["fund_event"] = "exchange_halt"
    f_c["funds"]["TQQQ"]["tracking_dev_1s_pp"] = "1.50"

    f_d = copy.deepcopy(baseline)
    f_d["market"]["index_session_fall"] = "0.10"

    return [
        ("a_o3_o4_v3_halt", f_a),
        ("b_o4_l2_scoped", f_b),
        ("c_v3_v1_same_fund", f_c),
        ("d_l6_halt", f_d),
    ]


def battery_precedence() -> dict[str, Any]:
    """(6) precedence (F1-A08): multi-trip fixtures resolve per scope precedence and HALT dominance."""
    spec = load_spec()
    fixtures = load_fixtures()
    baseline = fixtures["baseline"]
    prior = fixtures["baseline_prior_row_state"]
    policy_hash = baseline["policy"]["registered_hash"]
    engine_hash = compute_engine_hash(REPO_ROOT / "engine")

    expected_scopes: dict[str, dict[str, str]] = {
        "a_o3_o4_v3_halt": {
            "account": "HALT",
            "fund:TQQQ": "HALT",
            "fund:SOXL": "HALT",
            "symbol:TQQQ": "HALT",
            "symbol:SOXL": "HALT",
            "joint": "HALT",
        },
        "b_o4_l2_scoped": {
            "account": "NO-NEW-RISK",
            "fund:TQQQ": "NORMAL",
            "fund:SOXL": "NORMAL",
            "symbol:TQQQ": "ORDER-UNKNOWN",
            "symbol:SOXL": "NORMAL",
            "joint": "NORMAL",
        },
        "c_v3_v1_same_fund": {
            "account": "NORMAL",
            "fund:TQQQ": "DE-RISK",
            "fund:SOXL": "NORMAL",
            "symbol:TQQQ": "NORMAL",
            "symbol:SOXL": "NORMAL",
            "joint": "NORMAL",
        },
        "d_l6_halt": {
            "account": "HALT",
            "fund:TQQQ": "HALT",
            "fund:SOXL": "HALT",
            "symbol:TQQQ": "HALT",
            "symbol:SOXL": "HALT",
            "joint": "HALT",
        },
    }

    per_fixture: dict[str, dict[str, Any]] = {}
    fixtures_passed = 0
    prec_fixtures = build_precedence_fixtures(baseline)

    for fname, finput in prec_fixtures:
        rows, eff, _nxt = _run_evaluate(
            finput,
            copy.deepcopy(prior),
            [],
            spec_version=spec["spec_version"],
            engine_hash=engine_hash,
            policy_hash=policy_hash,
        )
        exp_eff = expected_scopes[fname]
        eff_match = eff == exp_eff

        if fname == "a_o3_o4_v3_halt":
            row_checks = {
                "O3_HALT": rows["O3"]["state"] == "HALT",
                "O4_TQQQ_ORDER_UNKNOWN": rows["O4"]["by_symbol"]["TQQQ"]["state"]
                == "ORDER-UNKNOWN",
                "V3_TQQQ_DE_RISK": rows["V3"]["by_fund"]["TQQQ"]["state"] == "DE-RISK",
            }
        elif fname == "b_o4_l2_scoped":
            row_checks = {
                "O4_TQQQ_ORDER_UNKNOWN": rows["O4"]["by_symbol"]["TQQQ"]["state"]
                == "ORDER-UNKNOWN",
                "L2_NO_NEW_RISK": rows["L2"]["state"] == "NO-NEW-RISK",
            }
        elif fname == "c_v3_v1_same_fund":
            row_checks = {
                "V3_TQQQ_DE_RISK": rows["V3"]["by_fund"]["TQQQ"]["state"] == "DE-RISK",
                "V1_TQQQ_NO_NEW_RISK": rows["V1"]["by_fund"]["TQQQ"]["state"]
                == "NO-NEW-RISK",
            }
        else:
            row_checks = {
                "L6_HALT": rows["L6"]["state"] == "HALT",
            }

        ok = eff_match and all(row_checks.values())
        if ok:
            fixtures_passed += 1
        per_fixture[fname] = {
            "passed": ok,
            "row_checks": row_checks,
            "effective_state_match": eff_match,
            "expected_effective_state_by_scope": exp_eff,
            "actual_effective_state_by_scope": eff,
        }

    passed = fixtures_passed == len(prec_fixtures)
    return _make_result(
        "F1-A08",
        passed,
        {
            "fixtures_checked": len(prec_fixtures),
            "fixtures_passed": fixtures_passed,
        },
        {"per_fixture": per_fixture},
    )


def battery_exposure_invariant() -> dict[str, Any]:
    """(7) exposure_invariant (F1-A09): capped exposure <= cap and policy_hash/spec_version unaltered."""
    spec = load_spec()
    fixtures = load_fixtures()
    golden_table = load_golden_table()

    spec_version = golden_table["spec_version"]
    engine_hash = compute_engine_hash(REPO_ROOT / "engine")
    baseline = fixtures["baseline"]
    baseline_prior = fixtures["baseline_prior_row_state"]
    baseline_events = fixtures.get("baseline_authorized_events", [])

    cases: list[tuple[str, str, dict[str, Any], dict[str, Any], list[Any]]] = []

    for sname, fx in fixtures["scenarios"].items():
        cases.append(
            (
                "matrix_scenario",
                sname,
                deep_merge(baseline, fx.get("inputs_override", {})),
                deep_merge(baseline_prior, fx.get("prior_row_state_override", {})),
                copy.deepcopy(fx.get("authorized_events", baseline_events)),
            )
        )

    for rep in golden_table["tier_repetitions"]["cells"]:
        cases.append(
            (
                "tier_repetition",
                str(rep["repetition_id"]),
                deep_merge(baseline, rep.get("inputs_override", {})),
                deep_merge(baseline_prior, rep.get("prior_row_state_override", {})),
                copy.deepcopy(rep.get("authorized_events", baseline_events)),
            )
        )

    for fname, finput in build_precedence_fixtures(baseline):
        cases.append(
            (
                "precedence_fixture",
                fname,
                finput,
                copy.deepcopy(baseline_prior),
                [],
            )
        )

    violations: list[dict[str, Any]] = []
    counts_by_group = {"matrix_scenario": 0, "tier_repetition": 0, "precedence_fixture": 0}

    for group, case_id, merged_inputs, merged_prior, events in cases:
        counts_by_group[group] += 1
        policy_hash = (merged_inputs.get("policy") or {}).get("registered_hash", "")
        inputs_before = copy.deepcopy(merged_inputs)

        res = _run_evaluate(
            merged_inputs,
            merged_prior,
            events,
            spec_version=spec_version,
            engine_hash=engine_hash,
            policy_hash=policy_hash,
        )
        rows_by_id, _eff, _nxt = res
        env = res.to_envelope()

        cap_out = rows_by_id["L0"]["cap_output"]
        eff_exp = Decimal(str(cap_out["effective_capped_exposure"]))
        exp_cap = Decimal(str(cap_out["exposure_cap"]))
        prop_exp = Decimal(str(cap_out["proposed_exposure"]))

        case_issues: list[str] = []
        if not (Decimal("0") <= eff_exp <= exp_cap and eff_exp <= prop_exp):
            case_issues.append(
                f"L0 cap invariant violated: effective={eff_exp}, cap={exp_cap}, proposed={prop_exp}"
            )

        headroom_out = rows_by_id["J1"]["headroom_output"]
        j_exp = Decimal(str(headroom_out["joint_exposure"]))
        j_cap = Decimal(str(headroom_out["joint_cap"]))
        if j_exp > j_cap and headroom_out.get("increases_blocked") is not True:
            case_issues.append(
                f"J1 increases_blocked not True when joint_exposure={j_exp} > joint_cap={j_cap}"
            )

        if res.policy_hash != policy_hash or env["policy_hash"] != policy_hash:
            case_issues.append("policy_hash altered in output")
        if res.spec_version != spec_version or env["spec_version"] != spec_version:
            case_issues.append("spec_version altered in output")
        if merged_inputs != inputs_before:
            case_issues.append("validated_inputs mutated by evaluate")

        if case_issues:
            violations.append(
                {"group": group, "case": case_id, "issues": case_issues}
            )

    passed = len(violations) == 0 and len(cases) == 57
    return _make_result(
        "F1-A09",
        passed,
        {
            "evaluations_checked": len(cases),
            "matrix_scenarios": counts_by_group["matrix_scenario"],
            "tier_repetitions": counts_by_group["tier_repetition"],
            "precedence_fixtures": counts_by_group["precedence_fixture"],
            "violations": len(violations),
        },
        {
            "spec_version": spec["spec_version"],
            "violations": violations,
        },
    )


def stub_evaluate(
    spec_version: str,
    engine_hash: str,
    policy_hash: str,
    session: Any,
    as_of: Any,
    mode: str,
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, Any]]:
    """Trivial in-battery stub implementing the pinned 9-arg C-FUSE-EVAL signature."""
    del spec_version, engine_hash, policy_hash, session, as_of, mode, prior_row_state, authorized_events
    spec = load_spec()
    funds = list(((validated_inputs or {}).get("funds") or {}).keys()) or ["TQQQ", "SOXL"]

    rows_by_id: dict[str, dict[str, Any]] = {}
    for row in spec["rows"]:
        rid = row["id"]
        cell: dict[str, Any] = {
            "scope": row["scope"],
            "state": "NORMAL",
            "would_have_tripped": False,
            "kind": row["kind"],
            "latched": False,
            "reason_class": "none",
            "reason": "synthetic stub normal",
        }
        if rid == "L0":
            cell["cap_output"] = {
                "exposure_cap": "0",
                "proposed_exposure": "0",
                "joint_exposure": "0",
                "effective_capped_exposure": "0",
                "cap_breached": False,
            }
        elif rid == "L1":
            cell["locked_against_loosening"] = False
            cell["notify"] = False
        elif rid == "L3":
            cell["cooling_off_days_remaining"] = 0
            cell["locked_flat"] = False
            cell["loss_record_cleared"] = False
        elif rid in ("V1", "V2", "V3", "V4", "V5", "V6", "V7"):
            cell["by_fund"] = {
                f: {
                    "state": "NORMAL",
                    "would_have_tripped": False,
                    "latched": False,
                    "reason_class": "none",
                    "reason": "stub",
                }
                for f in funds
            }
            if rid in ("V5", "V6"):
                cell["diagnostic_output"] = {"by_fund": {f: {} for f in funds}}
        elif rid == "O4":
            cell["by_symbol"] = {
                f: {
                    "state": "NORMAL",
                    "would_have_tripped": False,
                    "latched": False,
                    "reason_class": "none",
                    "reason": "stub",
                }
                for f in funds
            }
        elif rid == "O5":
            cell["rejections_this_session"] = 0
        elif rid == "J1":
            cell["headroom_output"] = {
                "joint_exposure": "0",
                "joint_cap": "0",
                "headroom": "0",
                "trim_threshold_110pct": "0",
                "increases_blocked": False,
                "trim_required_next_session": False,
            }
        rows_by_id[rid] = cell

    effective_state_by_scope: dict[str, str] = {
        "account": "NORMAL",
        **{f"fund:{f}": "NORMAL" for f in funds},
        **{f"symbol:{f}": "NORMAL" for f in funds},
        "joint": "NORMAL",
    }
    return rows_by_id, effective_state_by_scope, {}


def consume_evaluator(
    evaluator: Callable[..., Any],
    *,
    spec_version: str,
    engine_hash: str,
    policy_hash: str,
    session: Any,
    as_of: Any,
    mode: str,
    validated_inputs: dict[str, Any] | None,
    prior_row_state: dict[str, Any] | None,
    authorized_events: list[Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], Any, Any]:
    """Single consumer path calling any C-FUSE-EVAL evaluator with pinned positional args."""
    raw_res = evaluator(
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
    rows_by_id, effective_state_by_scope, next_row_state = raw_res
    return rows_by_id, effective_state_by_scope, next_row_state, raw_res


def battery_stub_swap() -> dict[str, Any]:
    """(8) stub_swap (F1-A10): consumer path interchangeable between stub and real engine + engine_hash check."""
    spec = load_spec()
    fixtures = load_fixtures()
    committed_matrix = load_json("results/matrix_result.json")
    engine_dir = REPO_ROOT / "engine"
    engine_files = sorted(engine_dir.glob("*.py"))
    engine_bytes_sha256 = compute_engine_bytes_sha256(engine_dir)
    manifest_engine_hash = compute_engine_hash(engine_dir)

    baseline = fixtures["baseline"]
    prior = fixtures["baseline_prior_row_state"]
    events = fixtures.get("baseline_authorized_events", [])
    policy_hash = baseline["policy"]["registered_hash"]

    real_sig = tuple(inspect.signature(evaluate).parameters.keys())
    stub_sig = tuple(inspect.signature(stub_evaluate).parameters.keys())
    signature_match = real_sig == stub_sig == PINNED_EVAL_PARAMS

    call_kwargs = {
        "spec_version": spec["spec_version"],
        "engine_hash": engine_bytes_sha256,
        "policy_hash": policy_hash,
        "session": DEFAULT_SESSION,
        "as_of": DEFAULT_AS_OF,
        "mode": DEFAULT_MODE,
        "validated_inputs": copy.deepcopy(baseline),
        "prior_row_state": copy.deepcopy(prior),
        "authorized_events": copy.deepcopy(events),
    }
    stub_rows, stub_eff, _stub_nxt, _stub_raw = consume_evaluator(
        stub_evaluate, **call_kwargs
    )
    real_rows, real_eff, _real_nxt, real_res = consume_evaluator(
        evaluate, **call_kwargs
    )
    real_env = real_res.to_envelope()

    key_set_match = set(real_rows.keys()) == set(stub_rows.keys()) == EXPECTED_ROW_IDS
    shape_mismatches: list[dict[str, Any]] = []
    for rid in sorted(EXPECTED_ROW_IDS):
        r_keys = set(real_rows.get(rid, {}).keys())
        s_keys = set(stub_rows.get(rid, {}).keys())
        if r_keys != s_keys:
            shape_mismatches.append(
                {
                    "row_id": rid,
                    "missing_in_real": sorted(s_keys - r_keys),
                    "extra_in_real": sorted(r_keys - s_keys),
                }
            )

    scope_match = set(real_eff.keys()) == set(stub_eff.keys()) and all(
        v in VALID_STATES for v in real_eff.values()
    )
    engine_hash_echoed = (
        real_res.engine_hash == engine_bytes_sha256
        and real_env["engine_hash"] == engine_bytes_sha256
        and real_env["code_hash"] == engine_bytes_sha256
    )

    manifest_kwargs = dict(call_kwargs)
    manifest_kwargs["engine_hash"] = manifest_engine_hash
    _mr, _me, _mn, m_res = consume_evaluator(evaluate, **manifest_kwargs)
    m_env = m_res.to_envelope()
    manifest_hash_echoed = (
        manifest_engine_hash == committed_matrix["engine_hash"]
        and m_res.engine_hash == manifest_engine_hash
        and m_env["engine_hash"] == manifest_engine_hash
        and m_env["code_hash"] == manifest_engine_hash
    )

    passed = (
        signature_match
        and key_set_match
        and len(shape_mismatches) == 0
        and scope_match
        and engine_hash_echoed
        and manifest_hash_echoed
    )

    return _make_result(
        "F1-A10",
        passed,
        {
            "rows_compared": len(EXPECTED_ROW_IDS),
            "row_shape_mismatches": len(shape_mismatches),
            "engine_files_hashed": len(engine_files),
            "engine_hash_echoed": engine_hash_echoed,
        },
        {
            "signature_match": signature_match,
            "pinned_params": list(PINNED_EVAL_PARAMS),
            "key_set_match": key_set_match,
            "scope_match": scope_match,
            "shape_mismatches": shape_mismatches,
            "engine_files": [
                p.relative_to(REPO_ROOT).as_posix() for p in engine_files
            ],
            "engine_bytes_sha256": engine_bytes_sha256,
            "manifest_engine_hash": manifest_engine_hash,
            "manifest_hash_echoed": manifest_hash_echoed,
        },
    )


def _is_numeric_ast_literal(node: ast.AST | None) -> tuple[bool, bool]:
    """Return (is_numeric_literal, is_zero) for int/float/Decimal AST literal nodes."""
    if node is None:
        return False, False
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return True, node.value == 0
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _is_numeric_ast_literal(node.operand)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Decimal"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, (str, int, float))
        and not isinstance(node.args[0].value, bool)
    ):
        try:
            dec = Decimal(str(node.args[0].value))
        except Exception:  # noqa: BLE001
            return True, False
        return True, dec == 0
    return False, False


def battery_register_proof() -> dict[str, Any]:
    """(9) register_proof (F1-A11): unresolved parameters stay null/UNRESOLVED-FAIL-CLOSED with no engine numeric literals."""
    register = load_disposition_register()
    spec = load_spec()
    fixtures = load_fixtures()

    expected_unresolved = {
        "V7": "V7 spread width",
        "O5": "O5 price collar",
        "V5": "V5 decay tolerance",
    }

    entries = register.get("entries", [])
    by_row = {entry.get("row_id"): entry for entry in entries if isinstance(entry, dict)}

    register_checks: dict[str, Any] = {}
    for rid, expected_param in expected_unresolved.items():
        entry = by_row.get(rid)
        register_checks[rid] = {
            "present": entry is not None,
            "parameter_matches": entry is not None and entry.get("parameter") == expected_param,
            "disposition_unresolved": entry is not None
            and entry.get("disposition") == "UNRESOLVED-FAIL-CLOSED",
            "proposal_value_is_null": entry is not None
            and entry.get("proposal_value") is None,
            "entry": entry,
        }

    all_unresolved_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("disposition") == "UNRESOLVED-FAIL-CLOSED"
    ]
    unresolved_row_ids = {entry.get("row_id") for entry in all_unresolved_entries}
    register_set_valid = (
        unresolved_row_ids == set(expected_unresolved.keys())
        and all(entry.get("proposal_value") is None for entry in all_unresolved_entries)
        and all(
            c["present"]
            and c["parameter_matches"]
            and c["disposition_unresolved"]
            and c["proposal_value_is_null"]
            for c in register_checks.values()
        )
    )

    param_name_pattern = re.compile(
        r"(?:spread_width|price_collar|decay_tolerance|v7_spread|o5_collar|v5_tolerance|max_spread|spread_threshold|collar_threshold|decay_threshold)",
        re.IGNORECASE,
    )
    dict_key_names = {
        "spread_width",
        "price_collar",
        "decay_tolerance",
        "tolerance",
        "collar",
        "max_spread",
    }
    target_eval_funcs = {
        "_eval_V5_stateful",
        "_eval_V7_stateful",
        "_eval_O5_stateful",
        "_check_o5_order",
    }
    sensitive_compare_vars = {
        "spread_width",
        "price_collar",
        "decay_tolerance",
        "tolerance",
        "collar",
        "spread_dec",
        "spread_raw",
        "shortfall_dec",
        "predicted_dec",
        "excess_str",
    }
    always_disallow_zero_vars = {
        "spread_width",
        "price_collar",
        "decay_tolerance",
        "tolerance",
        "collar",
    }
    line_regex = re.compile(
        r"(?:spread_width|price_collar|decay_tolerance)\s*[:=]\s*(?:[-+]?\d|Decimal\s*\()",
        re.IGNORECASE,
    )

    engine_dir = REPO_ROOT / "engine"
    engine_files = sorted(engine_dir.glob("*.py"))
    numeric_literal_hits: list[dict[str, Any]] = []
    tolerance_null_dicts_verified: list[dict[str, Any]] = []

    def check_assign_target(target: ast.AST, value: ast.AST | None, rel_path: str, lineno: int) -> None:
        if isinstance(target, ast.Name):
            if param_name_pattern.search(target.id):
                is_num, _ = _is_numeric_ast_literal(value)
                if is_num:
                    numeric_literal_hits.append(
                        {
                            "file": rel_path,
                            "line": lineno,
                            "kind": "assignment",
                            "symbol": target.id,
                            "source": ast.unparse(value) if value is not None else "",
                        }
                    )
        elif isinstance(target, (ast.Tuple, ast.List)):
            for idx, elt in enumerate(target.elts):
                sub_val = (
                    value.elts[idx]
                    if isinstance(value, (ast.Tuple, ast.List)) and idx < len(value.elts)
                    else None
                )
                check_assign_target(elt, sub_val, rel_path, lineno)

    for path in engine_files:
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        src = path.read_text(encoding="utf-8")
        lines = src.splitlines()
        for lineno, line_text in enumerate(lines, start=1):
            if line_regex.search(line_text):
                numeric_literal_hits.append(
                    {
                        "file": rel_path,
                        "line": lineno,
                        "kind": "regex",
                        "symbol": "unresolved_parameter_literal",
                        "source": line_text.strip(),
                    }
                )

        tree = ast.parse(src, filename=rel_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    check_assign_target(tgt, node.value, rel_path, node.lineno)
            elif isinstance(node, ast.AnnAssign):
                check_assign_target(node.target, node.value, rel_path, node.lineno)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pos_args = list(node.args.posonlyargs) + list(node.args.args)
                offset = len(pos_args) - len(node.args.defaults)
                for idx, default in enumerate(node.args.defaults):
                    arg_name = pos_args[offset + idx].arg
                    if param_name_pattern.search(arg_name):
                        is_num, _ = _is_numeric_ast_literal(default)
                        if is_num:
                            numeric_literal_hits.append(
                                {
                                    "file": rel_path,
                                    "line": node.lineno,
                                    "kind": "default_arg",
                                    "symbol": arg_name,
                                    "source": ast.unparse(default),
                                }
                            )
                for kw_arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                    if default is not None and param_name_pattern.search(kw_arg.arg):
                        is_num, _ = _is_numeric_ast_literal(default)
                        if is_num:
                            numeric_literal_hits.append(
                                {
                                    "file": rel_path,
                                    "line": node.lineno,
                                    "kind": "kw_default_arg",
                                    "symbol": kw_arg.arg,
                                    "source": ast.unparse(default),
                                }
                            )

                if node.name in target_eval_funcs:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Compare):
                            operands = [sub.left, *sub.comparators]
                            var_names = [
                                op.id
                                for op in operands
                                if isinstance(op, ast.Name) and op.id in sensitive_compare_vars
                            ]
                            if not var_names:
                                continue
                            disallow_zero = any(v in always_disallow_zero_vars for v in var_names)
                            for op in operands:
                                is_num, is_zero = _is_numeric_ast_literal(op)
                                if is_num and (disallow_zero or not is_zero):
                                    numeric_literal_hits.append(
                                        {
                                            "file": rel_path,
                                            "line": sub.lineno,
                                            "kind": "compare",
                                            "symbol": ",".join(var_names),
                                            "source": ast.unparse(sub),
                                        }
                                    )
            elif isinstance(node, ast.Dict):
                for k_node, v_node in zip(node.keys, node.values):
                    if (
                        isinstance(k_node, ast.Constant)
                        and isinstance(k_node.value, str)
                        and k_node.value in dict_key_names
                    ):
                        is_num, _ = _is_numeric_ast_literal(v_node)
                        if is_num:
                            numeric_literal_hits.append(
                                {
                                    "file": rel_path,
                                    "line": node.lineno,
                                    "kind": "dict_literal",
                                    "symbol": k_node.value,
                                    "source": ast.unparse(v_node),
                                }
                            )
                        elif (
                            k_node.value == "tolerance"
                            and isinstance(v_node, ast.Constant)
                            and v_node.value is None
                        ):
                            tolerance_null_dicts_verified.append(
                                {"file": rel_path, "line": node.lineno, "key": k_node.value}
                            )

    baseline = fixtures["baseline"]
    prior = fixtures["baseline_prior_row_state"]
    rows, _eff, _nxt = _run_evaluate(
        copy.deepcopy(baseline),
        copy.deepcopy(prior),
        [],
        spec_version=spec["spec_version"],
    )
    runtime_checks = {
        "V5_fail_closed": rows["V5"]["would_have_tripped"] is True
        and rows["V5"]["reason_class"] == "unresolved_fail_closed"
        and rows["V5"]["diagnostic_output"]["tolerance_disposition"]
        == "UNRESOLVED-FAIL-CLOSED"
        and all(
            entry.get("tolerance") is None and entry.get("fail_closed") is True
            for entry in rows["V5"]["diagnostic_output"]["by_fund"].values()
        ),
        "V7_fail_closed": rows["V7"]["would_have_tripped"] is True
        and rows["V7"]["reason_class"] == "unresolved_fail_closed",
        "O5_fail_closed": rows["O5"]["would_have_tripped"] is True
        and rows["O5"]["reason_class"] == "unresolved_fail_closed",
    }

    passed = (
        register_set_valid
        and len(numeric_literal_hits) == 0
        and len(tolerance_null_dicts_verified) >= 1
        and all(runtime_checks.values())
    )

    return _make_result(
        "F1-A11",
        passed,
        {
            "unresolved_entries_verified": len(all_unresolved_entries),
            "engine_files_scanned": len(engine_files),
            "numeric_literal_hits": len(numeric_literal_hits),
            "tolerance_null_dicts_verified": len(tolerance_null_dicts_verified),
            "runtime_checks_passed": sum(1 for v in runtime_checks.values() if v),
        },
        {
            "register_checks": register_checks,
            "unresolved_row_ids": sorted(r for r in unresolved_row_ids if r is not None),
            "engine_files": [p.relative_to(REPO_ROOT).as_posix() for p in engine_files],
            "numeric_literal_hits": numeric_literal_hits,
            "tolerance_null_dicts_verified": tolerance_null_dicts_verified,
            "runtime_checks": runtime_checks,
        },
    )


def battery_offline_scan() -> dict[str, Any]:
    """(10) offline_scan (F1-A13): verify zero network/secret tokens and classify every 'broker' occurrence."""
    scan_dirs = ("engine", "harness", "tests")
    forbidden_net_modules = frozenset(
        {
            "http",
            "socket",
            "urllib",
            "urllib3",
            "requests",
            "httpx",
            "aiohttp",
            "ftplib",
            "smtplib",
            "ssl",
            "xmlrpc",
            "grpc",
            "websocket",
            "websockets",
        }
    )
    forbidden_token_regex = re.compile(
        r"(?:http|socket|urllib|requests|api_key|secret)", re.IGNORECASE
    )
    url_scheme_regex = re.compile(r"\b(?:https?|wss?)://", re.IGNORECASE)
    disallowed_broker_context_regex = re.compile(
        r"(?://|endpoint|api_key|secret|connect\(|client\b|login)", re.IGNORECASE
    )
    broker_get_regex = re.compile(
        r"""\bbroker\.get\(\s*["'](?:positions_beyond_tolerance|cash_beyond_tolerance)["']\s*\)"""
    )

    prose_token_types: set[int] = {tokenize.STRING, tokenize.COMMENT}
    for attr_name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        tok_type = getattr(tokenize, attr_name, None)
        if isinstance(tok_type, int):
            prose_token_types.add(tok_type)

    existing_dirs: list[str] = []
    absent_dirs: list[str] = []
    scanned_files: list[Path] = []
    for dirname in scan_dirs:
        dpath = REPO_ROOT / dirname
        if dpath.is_dir():
            existing_dirs.append(dirname)
            for py_path in sorted(dpath.rglob("*.py")):
                if "__pycache__" not in py_path.parts:
                    scanned_files.append(py_path)
        else:
            absent_dirs.append(dirname)

    self_file_rel = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    self_src = Path(__file__).resolve().read_text(encoding="utf-8")
    self_tree = ast.parse(self_src, filename=self_file_rel)
    self_func_span: tuple[int, int] | None = None
    for node in ast.walk(self_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "battery_offline_scan":
            self_func_span = (node.lineno, node.end_lineno or node.lineno)
            break

    forbidden_imports: list[dict[str, Any]] = []
    forbidden_urls: list[dict[str, Any]] = []
    forbidden_calls: list[dict[str, Any]] = []
    forbidden_token_hits: list[dict[str, Any]] = []
    broker_occurrences: list[dict[str, Any]] = []
    disallowed_broker_occurrences: list[dict[str, Any]] = []

    for py_path in scanned_files:
        rel_path = py_path.relative_to(REPO_ROOT).as_posix()
        src = py_path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=rel_path)

        # 100% AST inspection (including battery_offline_scan itself, zero line exclusions)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in forbidden_net_modules:
                        forbidden_imports.append(
                            {"file": rel_path, "line": node.lineno, "module": alias.name}
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0] if mod else ""
                if top in forbidden_net_modules:
                    forbidden_imports.append(
                        {"file": rel_path, "line": node.lineno, "module": mod}
                    )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if url_scheme_regex.search(node.value):
                    forbidden_urls.append(
                        {
                            "file": rel_path,
                            "line": node.lineno,
                            "snippet": node.value[:120],
                        }
                    )
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id in forbidden_net_modules:
                    forbidden_calls.append(
                        {
                            "file": rel_path,
                            "line": node.lineno,
                            "expr": ast.unparse(node),
                        }
                    )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_net_modules:
                    forbidden_calls.append(
                        {
                            "file": rel_path,
                            "line": node.lineno,
                            "expr": ast.unparse(node),
                        }
                    )

        tokens_by_line: dict[int, list[tokenize.TokenInfo]] = {}
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            tokens_by_line.setdefault(tok.start[0], []).append(tok)

        for lineno, line_text in enumerate(src.splitlines(), start=1):
            if (
                rel_path == self_file_rel
                and self_func_span is not None
                and self_func_span[0] <= lineno <= self_func_span[1]
            ):
                continue

            match_tok = forbidden_token_regex.search(line_text)
            if match_tok:
                forbidden_token_hits.append(
                    {
                        "file": rel_path,
                        "line": lineno,
                        "token": match_tok.group(0),
                        "text": line_text.strip(),
                    }
                )

            if "broker" in line_text.lower():
                line_toks = [
                    tok for tok in tokens_by_line.get(lineno, []) if "broker" in tok.string.lower()
                ]
                if disallowed_broker_context_regex.search(line_text):
                    classification = "disallowed"
                elif "broker_record" in line_text.lower() or broker_get_regex.search(line_text):
                    classification = "broker_record_field"
                elif line_toks and all(tok.type in prose_token_types for tok in line_toks):
                    classification = "reconciliation_prose"
                else:
                    classification = "disallowed"

                entry = {
                    "file": rel_path,
                    "line": lineno,
                    "classification": classification,
                    "text": line_text.strip(),
                }
                broker_occurrences.append(entry)
                if classification == "disallowed":
                    disallowed_broker_occurrences.append(entry)

    passed = (
        len(scanned_files) > 0
        and len(forbidden_imports) == 0
        and len(forbidden_urls) == 0
        and len(forbidden_calls) == 0
        and len(forbidden_token_hits) == 0
        and len(disallowed_broker_occurrences) == 0
    )

    return _make_result(
        "F1-A13",
        passed,
        {
            "files_scanned": len(scanned_files),
            "forbidden_import_count": len(forbidden_imports),
            "forbidden_url_count": len(forbidden_urls),
            "forbidden_call_count": len(forbidden_calls),
            "forbidden_token_count": len(forbidden_token_hits),
            "broker_occurrences_count": len(broker_occurrences),
            "disallowed_broker_count": len(disallowed_broker_occurrences),
        },
        {
            "scan_dirs_present": existing_dirs,
            "scan_dirs_absent": absent_dirs,
            "scanned_files": [p.relative_to(REPO_ROOT).as_posix() for p in scanned_files],
            "scanner_self_scope": (
                {
                    "file": self_file_rel,
                    "start_line": self_func_span[0],
                    "end_line": self_func_span[1],
                    "note": "AST import/URL/call checks still inspect 100% of all files including this function; only raw token self-scan skips this definition span.",
                }
                if self_func_span is not None
                else None
            ),
            "forbidden_imports": forbidden_imports,
            "forbidden_urls": forbidden_urls,
            "forbidden_calls": forbidden_calls,
            "forbidden_token_hits": forbidden_token_hits,
            "broker_occurrences": broker_occurrences,
            "disallowed_broker_occurrences": disallowed_broker_occurrences,
        },
    )


BATTERIES: tuple[tuple[str, Callable[[], dict[str, Any]]], ...] = (
    ("determinism", battery_determinism),
    ("id_set_equality", battery_id_set_equality),
    ("spec_linter", battery_spec_linter),
    ("fail_closed", battery_fail_closed),
    ("persistence", battery_persistence),
    ("precedence", battery_precedence),
    ("exposure_invariant", battery_exposure_invariant),
    ("stub_swap", battery_stub_swap),
    ("register_proof", battery_register_proof),
    ("offline_scan", battery_offline_scan),
)


def run_all_batteries(output_path: Path) -> tuple[dict[str, Any], int]:
    """Execute registered batteries, write JSON bundle, and return (bundle, exit_code)."""
    spec = load_spec()
    engine_dir = REPO_ROOT / "engine"
    engine_hash = compute_engine_hash(engine_dir)
    engine_bytes_sha256 = compute_engine_bytes_sha256(engine_dir)

    results: dict[str, dict[str, Any]] = {}
    passed_count = 0
    failed_count = 0

    for name, fn in BATTERIES:
        try:
            entry = fn()
        except Exception as exc:  # noqa: BLE001
            entry = _make_result(
                "UNKNOWN",
                False,
                {"unexpected_exception": 1},
                {"exception": f"{type(exc).__name__}: {exc}"},
            )
        results[name] = entry
        if entry["passed"]:
            passed_count += 1
            status = "PASS"
        else:
            failed_count += 1
            status = "FAIL"
        print(
            f"{name} ({entry['id']}): {status} "
            f"evidence={json.dumps(entry['evidence_counts'], sort_keys=True)}"
        )

    total = passed_count + failed_count
    bundle: dict[str, Any] = {
        "spec_version": spec["spec_version"],
        "engine_hash": engine_hash,
        "engine_bytes_sha256": engine_bytes_sha256,
        "observation_class": "synthetic",
        "summary": {
            "total": total,
            "passed": passed_count,
            "failed": failed_count,
            "all_passed": failed_count == 0,
        },
        "batteries": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return bundle, 0 if failed_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for running FUSE-1 acceptance batteries."""
    parser = argparse.ArgumentParser(
        description="Run FUSE-1 acceptance batteries against engine.evaluate."
    )
    parser.add_argument(
        "--output",
        default="results/battery_result.json",
        help="Output JSON path (relative to repo root if relative).",
    )
    args = parser.parse_args(argv)
    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    _bundle, exit_code = run_all_batteries(out_path)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
