"""Unit tests for the FUSE-1 reference control engine."""

from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine import EvaluationResult, ROW_IDS, evaluate, wrap_outputs  # noqa: E402

_FIXTURES = json.loads(
    (REPO_ROOT / "goldens" / "scenario_fixtures.json").read_text(encoding="utf-8")
)

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

DEFAULT_SESSION = "2026-01-02"
DEFAULT_AS_OF = "2026-01-02T21:00:00Z"


def _deep_merge(base: Any, override: Any) -> Any:
    """Return a deep copy of base recursively merged with override."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = {k: copy.deepcopy(v) for k, v in base.items()}
        for key, val in override.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
                merged[key] = _deep_merge(merged[key], val)
            else:
                merged[key] = copy.deepcopy(val)
        return merged
    if override is None and base is not None:
        return copy.deepcopy(base) if isinstance(base, dict) else None
    return copy.deepcopy(override)


def _make_case(
    inputs_override: dict[str, Any] | None = None,
    prior_override: dict[str, Any] | None = None,
    *,
    clear_attempted_order: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build (validated_inputs, prior_row_state) from the scenario baseline."""
    inputs = _deep_merge(_FIXTURES["baseline"], inputs_override or {})
    prior = _deep_merge(_FIXTURES["baseline_prior_row_state"], prior_override or {})
    if clear_attempted_order:
        inputs.setdefault("pretrade", {})["attempted_order"] = None

    # Keep O9 prior baseline synchronized with test tier/cap overrides unless O9 prior is explicit.
    explicit_o9 = (prior_override or {}).get("O9", {})
    o9_prior = prior.setdefault("O9", {})
    if "prior_tier" not in explicit_o9:
        o9_prior["prior_tier"] = inputs.get("tier")
    if "prior_joint_cap" not in explicit_o9 and isinstance(inputs.get("joint"), dict):
        o9_prior["prior_joint_cap"] = inputs["joint"].get("joint_cap")
    if "prior_max_loss_cap" not in explicit_o9 and isinstance(inputs.get("sizing"), dict):
        o9_prior["prior_max_loss_cap"] = inputs["sizing"].get("max_loss_cap")
    return inputs, prior


def _eval(
    inputs: dict[str, Any] | None,
    prior: dict[str, Any] | None,
    events: list[Any] | None = None,
    *,
    session: Any = DEFAULT_SESSION,
    as_of: Any = DEFAULT_AS_OF,
    mode: str = "shadow_would_have_tripped",
) -> EvaluationResult:
    """Invoke engine.evaluate with standard test metadata."""
    policy_hash = ""
    if isinstance(inputs, dict) and isinstance(inputs.get("policy"), dict):
        policy_hash = str(inputs["policy"].get("registered_hash", ""))
    return evaluate(
        "fuse-eval-spec/v1",
        "test-engine-hash",
        policy_hash,
        session,
        as_of,
        mode,
        inputs,
        prior,
        [] if events is None else events,
    )


class TestEvaluateContractAndShadowMode(unittest.TestCase):
    def test_pinned_evaluate_signature(self) -> None:
        params = list(inspect.signature(evaluate).parameters.keys())
        self.assertEqual(
            params,
            [
                "spec_version",
                "engine_hash",
                "policy_hash",
                "session",
                "as_of",
                "mode",
                "validated_inputs",
                "prior_row_state",
                "authorized_events",
            ],
        )

    def test_returns_exact_24_row_ids(self) -> None:
        inputs, prior = _make_case()
        res = _eval(inputs, prior)
        self.assertIsInstance(res, EvaluationResult)
        self.assertEqual(len(res), 3)
        rows, effective, next_state = res
        self.assertEqual(len(rows), 24)
        self.assertEqual(set(rows.keys()), EXPECTED_ROW_IDS)
        self.assertEqual(set(ROW_IDS), EXPECTED_ROW_IDS)
        self.assertIsInstance(effective, dict)
        self.assertIsInstance(next_state, dict)

    def test_shadow_mode_assertions(self) -> None:
        for mode in ("shadow_would_have_tripped", "shadow"):
            with self.subTest(mode=mode):
                inputs, prior = _make_case()
                res = _eval(inputs, prior, mode=mode)
                self.assertEqual(res.enforcement_mode, "shadow_would_have_tripped")
                self.assertIs(res.loss_breakers_armed, False)
                self.assertIs(res.kelly_applied, False)
                self.assertIs(type(res.orders_placed), int)
                self.assertEqual(res.orders_placed, 0)

                envelope = res.to_envelope()
                self.assertEqual(envelope["enforcement_mode"], "shadow_would_have_tripped")
                self.assertIs(envelope["loss_breakers_armed"], False)
                self.assertIs(envelope["kelly_applied"], False)
                self.assertIs(type(envelope["orders_placed"]), int)
                self.assertEqual(envelope["orders_placed"], 0)

                wrapped = wrap_outputs(
                    res[0],
                    res[1],
                    res[2],
                    spec_version="fuse-eval-spec/v1",
                    engine_hash="test-engine-hash",
                    policy_hash=inputs["policy"]["registered_hash"],
                    session=DEFAULT_SESSION,
                    as_of=DEFAULT_AS_OF,
                )
                self.assertEqual(wrapped["enforcement_mode"], "shadow_would_have_tripped")
                self.assertIs(wrapped["loss_breakers_armed"], False)
                self.assertIs(wrapped["kelly_applied"], False)
                self.assertIs(type(wrapped["orders_placed"]), int)
                self.assertEqual(wrapped["orders_placed"], 0)

        inputs, prior = _make_case()
        with self.assertRaises(ValueError):
            _eval(inputs, prior, mode="live")


class TestLossThresholdsAndLatch(unittest.TestCase):
    def test_l1_l2_l3_l4_threshold_boundaries_two_tiers(self) -> None:
        # Bankroll = 50000:
        # conservative (D=0.15 => 7500): D/3=2500, 2D/3=5000, D=7500, D/10=750
        # balanced (D=0.30 => 15000): D/3=5000, 2D/3=10000, D=15000, D/10=1500
        tier_cases = {
            "conservative": {
                "l1_below": "2499.99",
                "l1_at": "2500",
                "l2_below": "4999.99",
                "l2_at": "5000",
                "l3_below": "7499.99",
                "l3_at": "7500",
                "l4_below": "749.99",
                "l4_at": "750",
            },
            "balanced": {
                "l1_below": "4999.99",
                "l1_at": "5000",
                "l2_below": "9999.99",
                "l2_at": "10000",
                "l3_below": "14999.99",
                "l3_at": "15000",
                "l4_below": "1499.99",
                "l4_at": "1500",
            },
        }

        for tier, bounds in tier_cases.items():
            with self.subTest(tier=tier):
                # L1 just below D/3 vs at D/3
                inp, prior = _make_case(
                    {"tier": tier, "loss": {"drawdown_amount": bounds["l1_below"]}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                self.assertEqual(rows["L1"]["state"], "NORMAL")
                self.assertIs(rows["L1"]["would_have_tripped"], False)
                self.assertIs(rows["L1"]["locked_against_loosening"], False)
                self.assertIs(rows["L1"]["notify"], False)
                self.assertEqual(eff["account"], "NORMAL")

                inp, prior = _make_case(
                    {"tier": tier, "loss": {"drawdown_amount": bounds["l1_at"]}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                self.assertEqual(rows["L1"]["state"], "NORMAL")
                self.assertIs(rows["L1"]["would_have_tripped"], True)
                self.assertIs(rows["L1"]["latched"], False)
                self.assertEqual(rows["L1"]["reason_class"], "drawdown_reached_D_over_3")
                self.assertIs(rows["L1"]["locked_against_loosening"], True)
                self.assertIs(rows["L1"]["notify"], True)
                self.assertIs(rows["L2"]["would_have_tripped"], False)
                self.assertIs(rows["L3"]["would_have_tripped"], False)
                self.assertEqual(eff["account"], "NORMAL")

                # L2 just below 2D/3 vs at 2D/3
                inp, prior = _make_case(
                    {"tier": tier, "loss": {"drawdown_amount": bounds["l2_below"]}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                self.assertEqual(rows["L2"]["state"], "NORMAL")
                self.assertIs(rows["L2"]["would_have_tripped"], False)
                self.assertIs(rows["L2"]["latched"], False)

                inp, prior = _make_case(
                    {"tier": tier, "loss": {"drawdown_amount": bounds["l2_at"]}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                self.assertEqual(rows["L2"]["state"], "NO-NEW-RISK")
                self.assertIs(rows["L2"]["would_have_tripped"], True)
                self.assertIs(rows["L2"]["latched"], True)
                self.assertEqual(rows["L2"]["reason_class"], "drawdown_reached_2D_over_3")
                self.assertIs(rows["L3"]["would_have_tripped"], False)
                self.assertEqual(eff["account"], "NO-NEW-RISK")

                # L3 just below D vs at D
                inp, prior = _make_case(
                    {"tier": tier, "loss": {"drawdown_amount": bounds["l3_below"]}},
                    clear_attempted_order=True,
                )
                rows, _, _ = _eval(inp, prior)
                self.assertEqual(rows["L3"]["state"], "NORMAL")
                self.assertIs(rows["L3"]["would_have_tripped"], False)
                self.assertIs(rows["L3"]["latched"], False)
                self.assertIs(rows["L3"]["locked_flat"], False)
                self.assertEqual(rows["L3"]["cooling_off_days_remaining"], 0)

                inp, prior = _make_case(
                    {"tier": tier, "loss": {"drawdown_amount": bounds["l3_at"]}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                self.assertEqual(rows["L3"]["state"], "DE-RISK")
                self.assertIs(rows["L3"]["would_have_tripped"], True)
                self.assertIs(rows["L3"]["latched"], True)
                self.assertEqual(rows["L3"]["reason_class"], "drawdown_reached_D")
                self.assertIs(rows["L3"]["locked_flat"], True)
                self.assertEqual(rows["L3"]["cooling_off_days_remaining"], 30)
                self.assertIs(rows["L3"]["loss_record_cleared"], False)
                self.assertEqual(eff["account"], "DE-RISK")

                # L4 just below D/10 vs at D/10
                inp, prior = _make_case(
                    {"tier": tier, "loss": {"session_loss_amount": bounds["l4_below"]}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                self.assertEqual(rows["L4"]["state"], "NORMAL")
                self.assertIs(rows["L4"]["would_have_tripped"], False)
                self.assertIs(rows["L4"]["latched"], False)
                self.assertEqual(eff["account"], "NORMAL")

                inp, prior = _make_case(
                    {"tier": tier, "loss": {"session_loss_amount": bounds["l4_at"]}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                self.assertEqual(rows["L4"]["state"], "NO-NEW-RISK")
                self.assertIs(rows["L4"]["would_have_tripped"], True)
                self.assertIs(rows["L4"]["latched"], True)
                self.assertEqual(
                    rows["L4"]["reason_class"], "session_loss_reached_D_over_10"
                )
                self.assertEqual(eff["account"], "NO-NEW-RISK")

    def test_l2_latch_persistence_and_rearm(self) -> None:
        # Trip L2 at 2D/3 for balanced (10000)
        inp_trip, prior0 = _make_case(
            {"loss": {"drawdown_amount": "10000"}},
            clear_attempted_order=True,
        )
        rows1, eff1, next1 = _eval(inp_trip, prior0, session="2026-01-02")
        self.assertEqual(rows1["L2"]["state"], "NO-NEW-RISK")
        self.assertIs(rows1["L2"]["latched"], True)
        self.assertEqual(eff1["account"], "NO-NEW-RISK")

        # Drawdown recovers to 0 without re-arm event: latch persists
        inp_rec, _ = _make_case(
            {"loss": {"drawdown_amount": "0"}},
            clear_attempted_order=True,
        )
        rows2, eff2, next2 = _eval(inp_rec, next1, events=[], session="2026-01-05")
        self.assertEqual(rows2["L2"]["state"], "NO-NEW-RISK")
        self.assertIs(rows2["L2"]["would_have_tripped"], True)
        self.assertIs(rows2["L2"]["latched"], True)
        self.assertEqual(rows2["L2"]["reason_class"], "latched_prior_trip")
        self.assertEqual(eff2["account"], "NO-NEW-RISK")

        # Re-arm event targeting a different row must not clear L2
        rows3, _, next3 = _eval(
            inp_rec,
            next2,
            events=[{"row_id": "L4", "action": "owner_re_arm"}],
            session="2026-01-06",
        )
        self.assertEqual(rows3["L2"]["state"], "NO-NEW-RISK")
        self.assertIs(rows3["L2"]["latched"], True)

        # Re-arm event targeting L2 clears the latch
        rows4, eff4, next4 = _eval(
            inp_rec,
            next3,
            events=[{"row_id": "L2", "action": "owner_re_arm"}],
            session="2026-01-07",
        )
        self.assertEqual(rows4["L2"]["state"], "NORMAL")
        self.assertIs(rows4["L2"]["would_have_tripped"], False)
        self.assertIs(rows4["L2"]["latched"], False)
        self.assertEqual(rows4["L2"]["reason_class"], "none")
        self.assertIs(next4["L2"]["latched"], False)
        self.assertEqual(eff4["account"], "NORMAL")


class TestVehicleRows(unittest.TestCase):
    def test_v1_deviation_thresholds(self) -> None:
        # Exact thresholds (0.75pp 1s and 2.0pp 5s) do not trip (> is strict)
        inp, prior = _make_case(
            {"funds": {"TQQQ": {"tracking_dev_1s_pp": "0.75", "tracking_dev_5s_pp": "2.0"}}},
            clear_attempted_order=True,
        )
        rows, eff, _ = _eval(inp, prior)
        self.assertEqual(rows["V1"]["state"], "NORMAL")
        self.assertIs(rows["V1"]["would_have_tripped"], False)
        self.assertIs(rows["V1"]["latched"], False)
        self.assertEqual(eff["fund:TQQQ"], "NORMAL")

        # 1s > 0.75pp trips TQQQ only
        inp, prior = _make_case(
            {"funds": {"TQQQ": {"tracking_dev_1s_pp": "0.76", "tracking_dev_5s_pp": "0.30"}}},
            clear_attempted_order=True,
        )
        rows, eff, _ = _eval(inp, prior)
        tqqq = rows["V1"]["by_fund"]["TQQQ"]
        soxl = rows["V1"]["by_fund"]["SOXL"]
        self.assertEqual(tqqq["state"], "NO-NEW-RISK")
        self.assertIs(tqqq["latched"], True)
        self.assertEqual(tqqq["reason_class"], "tracking_dev_1s_exceeded")
        self.assertEqual(soxl["state"], "NORMAL")
        self.assertEqual(eff["fund:TQQQ"], "NO-NEW-RISK")
        self.assertEqual(eff["fund:SOXL"], "NORMAL")
        self.assertEqual(eff["account"], "NORMAL")

        # Negative 1s exceeding -0.75pp also trips (abs check)
        inp, prior = _make_case(
            {"funds": {"TQQQ": {"tracking_dev_1s_pp": "-0.76", "tracking_dev_5s_pp": "0.30"}}},
            clear_attempted_order=True,
        )
        rows, _, _ = _eval(inp, prior)
        self.assertEqual(rows["V1"]["by_fund"]["TQQQ"]["state"], "NO-NEW-RISK")
        self.assertEqual(
            rows["V1"]["by_fund"]["TQQQ"]["reason_class"], "tracking_dev_1s_exceeded"
        )

        # 5s > 2.0pp trips SOXL only
        inp, prior = _make_case(
            {"funds": {"SOXL": {"tracking_dev_1s_pp": "0.10", "tracking_dev_5s_pp": "2.01"}}},
            clear_attempted_order=True,
        )
        rows, eff, _ = _eval(inp, prior)
        self.assertEqual(rows["V1"]["by_fund"]["SOXL"]["state"], "NO-NEW-RISK")
        self.assertIs(rows["V1"]["by_fund"]["SOXL"]["latched"], True)
        self.assertEqual(
            rows["V1"]["by_fund"]["SOXL"]["reason_class"], "tracking_dev_5s_exceeded"
        )
        self.assertEqual(rows["V1"]["by_fund"]["TQQQ"]["state"], "NORMAL")
        self.assertEqual(eff["fund:SOXL"], "NO-NEW-RISK")

        # Both 1s and 5s exceeded
        inp, prior = _make_case(
            {"funds": {"TQQQ": {"tracking_dev_1s_pp": "0.76", "tracking_dev_5s_pp": "2.01"}}},
            clear_attempted_order=True,
        )
        rows, _, _ = _eval(inp, prior)
        self.assertEqual(
            rows["V1"]["by_fund"]["TQQQ"]["reason_class"], "tracking_dev_1s_and_5s"
        )

    def test_v2_all_three_branches(self) -> None:
        # Branch 1: pending corporate action -> HALT, not latched
        pending_ca = {
            "type": "split",
            "announced": True,
            "detected_in_price": True,
            "ledger_adjusted": False,
            "reconciles_exactly": False,
        }
        inp1, prior0 = _make_case(
            {"funds": {"TQQQ": {"corporate_action": pending_ca}}},
            clear_attempted_order=True,
        )
        rows1, eff1, next1 = _eval(inp1, prior0)
        self.assertEqual(rows1["V2"]["state"], "HALT")
        self.assertIs(rows1["V2"]["would_have_tripped"], True)
        self.assertIs(rows1["V2"]["latched"], False)
        self.assertEqual(rows1["V2"]["reason_class"], "corporate_action_pending")
        self.assertEqual(rows1["V2"]["by_fund"]["TQQQ"]["state"], "HALT")
        self.assertIs(rows1["V2"]["by_fund"]["TQQQ"]["latched"], False)
        self.assertEqual(rows1["V2"]["by_fund"]["SOXL"]["state"], "NORMAL")
        self.assertEqual(eff1["fund:TQQQ"], "HALT")
        self.assertEqual(eff1["fund:SOXL"], "NORMAL")
        self.assertEqual(eff1["account"], "NORMAL")

        # Branch 2: adjusted and exact reconciliation -> automatic clear without authorized_events
        reconciled_ca = {
            "type": "split",
            "announced": True,
            "detected_in_price": True,
            "ledger_adjusted": True,
            "reconciles_exactly": True,
        }
        inp2, _ = _make_case(
            {"funds": {"TQQQ": {"corporate_action": reconciled_ca}}},
            clear_attempted_order=True,
        )
        rows2, eff2, _ = _eval(inp2, next1, events=[])
        self.assertEqual(rows2["V2"]["state"], "NORMAL")
        self.assertIs(rows2["V2"]["would_have_tripped"], False)
        self.assertIs(rows2["V2"]["latched"], False)
        self.assertEqual(rows2["V2"]["reason_class"], "reconciled")
        self.assertEqual(rows2["V2"]["by_fund"]["TQQQ"]["state"], "NORMAL")
        self.assertEqual(rows2["V2"]["by_fund"]["TQQQ"]["reason_class"], "reconciled")
        self.assertEqual(eff2["fund:TQQQ"], "NORMAL")

        # Branch 3: adjusted but not reconciled -> HALT latched until owner re-arm
        failed_ca = {
            "type": "reverse_split",
            "announced": True,
            "detected_in_price": True,
            "ledger_adjusted": True,
            "reconciles_exactly": False,
        }
        inp3, prior3 = _make_case(
            {"funds": {"SOXL": {"corporate_action": failed_ca}}},
            clear_attempted_order=True,
        )
        rows3, eff3, next3 = _eval(inp3, prior3)
        self.assertEqual(rows3["V2"]["state"], "HALT")
        self.assertIs(rows3["V2"]["would_have_tripped"], True)
        self.assertIs(rows3["V2"]["latched"], True)
        self.assertEqual(
            rows3["V2"]["reason_class"], "corporate_action_reconciliation_failed"
        )
        self.assertEqual(rows3["V2"]["by_fund"]["SOXL"]["state"], "HALT")
        self.assertIs(rows3["V2"]["by_fund"]["SOXL"]["latched"], True)
        self.assertEqual(eff3["fund:SOXL"], "HALT")
        self.assertEqual(eff3["fund:TQQQ"], "NORMAL")

        # Clearing corporate_action without owner re-arm keeps SOXL latched HALT
        inp4, _ = _make_case(
            {"funds": {"SOXL": {"corporate_action": None}}},
            clear_attempted_order=True,
        )
        rows4, _, next4 = _eval(inp4, next3, events=[])
        self.assertEqual(rows4["V2"]["by_fund"]["SOXL"]["state"], "HALT")
        self.assertIs(rows4["V2"]["by_fund"]["SOXL"]["latched"], True)
        self.assertEqual(
            rows4["V2"]["by_fund"]["SOXL"]["reason_class"], "latched_prior_trip"
        )

        # Owner re-arm for SOXL clears V2
        rows5, eff5, _ = _eval(
            inp4,
            next4,
            events=[{"row_id": "V2", "fund": "SOXL", "action": "owner_re_arm"}],
        )
        self.assertEqual(rows5["V2"]["state"], "NORMAL")
        self.assertIs(rows5["V2"]["latched"], False)
        self.assertEqual(eff5["fund:SOXL"], "NORMAL")

    def test_v4_trip_and_ten_session_clearing_counter(self) -> None:
        # TQQQ baseline long_run_vol is 0.24 => 2x threshold is 0.48
        inp_below, prior0 = _make_case(
            {"funds": {"TQQQ": {"forecast_vol": "0.4799"}}},
            clear_attempted_order=True,
        )
        rows_below, _, _ = _eval(inp_below, prior0)
        tqqq_below = rows_below["V4"]["by_fund"]["TQQQ"]
        self.assertEqual(tqqq_below["state"], "NORMAL")
        self.assertIs(tqqq_below["active"], False)
        self.assertEqual(tqqq_below["below_threshold_sessions"], 0)

        # Trip at exact 2x (0.48)
        inp_trip, prior_trip = _make_case(
            {"funds": {"TQQQ": {"forecast_vol": "0.48"}}},
            clear_attempted_order=True,
        )
        rows_trip, eff_trip, state = _eval(inp_trip, prior_trip)
        tqqq_trip = rows_trip["V4"]["by_fund"]["TQQQ"]
        self.assertEqual(tqqq_trip["state"], "NO-NEW-RISK")
        self.assertIs(tqqq_trip["would_have_tripped"], True)
        self.assertIs(tqqq_trip["latched"], False)
        self.assertEqual(tqqq_trip["reason_class"], "forecast_vol_exceeded_2x_long_run")
        self.assertIs(tqqq_trip["active"], True)
        self.assertEqual(tqqq_trip["below_threshold_sessions"], 0)
        self.assertEqual(rows_trip["V4"]["by_fund"]["SOXL"]["state"], "NORMAL")
        self.assertEqual(eff_trip["fund:TQQQ"], "NO-NEW-RISK")

        # 9 consecutive sessions below threshold stay NO-NEW-RISK and count 1..9
        inp_calm, _ = _make_case(
            {"funds": {"TQQQ": {"forecast_vol": "0.22"}}},
            clear_attempted_order=True,
        )
        for expected_count in range(1, 10):
            rows_step, eff_step, state = _eval(inp_calm, state)
            tqqq_step = rows_step["V4"]["by_fund"]["TQQQ"]
            self.assertEqual(tqqq_step["state"], "NO-NEW-RISK")
            self.assertIs(tqqq_step["would_have_tripped"], True)
            self.assertIs(tqqq_step["latched"], False)
            self.assertEqual(tqqq_step["reason_class"], "active_clearing_counter")
            self.assertIs(tqqq_step["active"], True)
            self.assertEqual(tqqq_step["below_threshold_sessions"], expected_count)
            self.assertEqual(eff_step["fund:TQQQ"], "NO-NEW-RISK")

        # 10th session below threshold clears V4
        rows_clear, eff_clear, next_clear = _eval(inp_calm, state)
        tqqq_clear = rows_clear["V4"]["by_fund"]["TQQQ"]
        self.assertEqual(tqqq_clear["state"], "NORMAL")
        self.assertIs(tqqq_clear["would_have_tripped"], False)
        self.assertIs(tqqq_clear["latched"], False)
        self.assertEqual(tqqq_clear["reason_class"], "none")
        self.assertIs(tqqq_clear["active"], False)
        self.assertEqual(tqqq_clear["below_threshold_sessions"], 0)
        self.assertIs(next_clear["V4"]["by_fund"]["TQQQ"]["active"], False)
        self.assertEqual(eff_clear["fund:TQQQ"], "NORMAL")

        # Spike mid-countdown resets below_threshold_sessions to 0
        inp_spike, prior_mid = _make_case(
            {"funds": {"TQQQ": {"forecast_vol": "0.50"}}},
            {"V4": {"by_fund": {"TQQQ": {"active": True, "below_threshold_sessions": 4}}}},
            clear_attempted_order=True,
        )
        rows_spike, _, next_spike = _eval(inp_spike, prior_mid)
        self.assertEqual(rows_spike["V4"]["by_fund"]["TQQQ"]["state"], "NO-NEW-RISK")
        self.assertEqual(
            rows_spike["V4"]["by_fund"]["TQQQ"]["below_threshold_sessions"], 0
        )
        self.assertIs(next_spike["V4"]["by_fund"]["TQQQ"]["active"], True)


class TestOpsAndJointRows(unittest.TestCase):
    def test_o1_stale_and_missing(self) -> None:
        # age_sessions == 1 is still fresh
        inp_fresh, prior0 = _make_case(
            {"data_inputs": {"index_returns": {"age_sessions": 1}}},
            clear_attempted_order=True,
        )
        rows_fresh, eff_fresh, _ = _eval(inp_fresh, prior0)
        self.assertEqual(rows_fresh["O1"]["state"], "NORMAL")
        self.assertIs(rows_fresh["O1"]["would_have_tripped"], False)
        self.assertEqual(eff_fresh["account"], "NORMAL")

        # age_sessions == 2 trips stale_input; 1 fresh session clears it
        inp_stale, prior1 = _make_case(
            {"data_inputs": {"index_returns": {"age_sessions": 2}}},
            clear_attempted_order=True,
        )
        rows_stale, eff_stale, next_stale = _eval(inp_stale, prior1)
        self.assertEqual(rows_stale["O1"]["state"], "NO-NEW-RISK")
        self.assertIs(rows_stale["O1"]["would_have_tripped"], True)
        self.assertIs(rows_stale["O1"]["latched"], False)
        self.assertEqual(rows_stale["O1"]["reason_class"], "stale_input")
        self.assertEqual(eff_stale["account"], "NO-NEW-RISK")

        inp_clean, _ = _make_case(clear_attempted_order=True)
        rows_cleared, eff_cleared, _ = _eval(inp_clean, next_stale)
        self.assertEqual(rows_cleared["O1"]["state"], "NORMAL")
        self.assertIs(rows_cleared["O1"]["would_have_tripped"], False)
        self.assertEqual(eff_cleared["account"], "NORMAL")

        # Missing volatility data_input fails closed to NO-NEW-RISK
        inp_missing, prior2 = _make_case(
            {
                "data_inputs": {
                    "volatility": {"present": False, "age_sessions": None, "valid": False}
                }
            },
            clear_attempted_order=True,
        )
        rows_missing, eff_missing, _ = _eval(inp_missing, prior2)
        self.assertEqual(rows_missing["O1"]["state"], "NO-NEW-RISK")
        self.assertIs(rows_missing["O1"]["would_have_tripped"], True)
        self.assertIs(rows_missing["O1"]["latched"], False)
        self.assertEqual(rows_missing["O1"]["reason_class"], "missing_input")
        self.assertEqual(eff_missing["account"], "NO-NEW-RISK")

    def test_o2_holiday(self) -> None:
        inp_open, prior0 = _make_case(clear_attempted_order=True)
        rows_open, _, _ = _eval(inp_open, prior0)
        self.assertEqual(rows_open["O2"]["state"], "NORMAL")
        self.assertIs(rows_open["O2"]["would_have_tripped"], False)
        self.assertEqual(rows_open["O2"]["reason_class"], "none")

        inp_holiday, prior1 = _make_case(
            {"calendar": {"session_state": "holiday", "exchange_agrees": True}},
            clear_attempted_order=True,
        )
        rows_holiday, eff_holiday, _ = _eval(inp_holiday, prior1)
        self.assertEqual(rows_holiday["O2"]["state"], "NORMAL")
        self.assertIs(rows_holiday["O2"]["would_have_tripped"], True)
        self.assertIs(rows_holiday["O2"]["latched"], False)
        self.assertEqual(rows_holiday["O2"]["reason_class"], "calendar_closed")
        self.assertEqual(eff_holiday["account"], "NORMAL")

    def test_o4_order_unknown_scope(self) -> None:
        inp_timeout, prior0 = _make_case(
            {
                "orders": {
                    "pending": {
                        "symbol": "TQQQ",
                        "timed_out": True,
                        "terminal_status": None,
                    }
                }
            },
            clear_attempted_order=True,
        )
        rows1, eff1, next1 = _eval(inp_timeout, prior0)
        o4 = rows1["O4"]
        self.assertEqual(o4["scope"], "symbol")
        self.assertEqual(o4["state"], "ORDER-UNKNOWN")
        self.assertIs(o4["latched"], True)
        self.assertEqual(o4["reason_class"], "order_timeout_unknown")
        self.assertEqual(o4["by_symbol"]["TQQQ"]["state"], "ORDER-UNKNOWN")
        self.assertEqual(o4["by_symbol"]["SOXL"]["state"], "NORMAL")

        # Only symbol:TQQQ becomes ORDER-UNKNOWN; sibling symbol, funds, account, joint stay NORMAL
        self.assertEqual(eff1["symbol:TQQQ"], "ORDER-UNKNOWN")
        self.assertEqual(eff1["symbol:SOXL"], "NORMAL")
        self.assertEqual(eff1["account"], "NORMAL")
        self.assertEqual(eff1["fund:TQQQ"], "NORMAL")
        self.assertEqual(eff1["fund:SOXL"], "NORMAL")
        self.assertEqual(eff1["joint"], "NORMAL")

        # Without definitive terminal status, ORDER-UNKNOWN persists
        inp_none, _ = _make_case({"orders": {"pending": None}}, clear_attempted_order=True)
        rows2, eff2, next2 = _eval(inp_none, next1)
        self.assertEqual(rows2["O4"]["by_symbol"]["TQQQ"]["state"], "ORDER-UNKNOWN")
        self.assertEqual(
            rows2["O4"]["by_symbol"]["TQQQ"]["reason_class"], "latched_prior_trip"
        )
        self.assertEqual(eff2["symbol:TQQQ"], "ORDER-UNKNOWN")

        # Definitive terminal status clears symbol:TQQQ
        inp_filled, _ = _make_case(
            {
                "orders": {
                    "pending": {
                        "symbol": "TQQQ",
                        "timed_out": True,
                        "terminal_status": "filled",
                    }
                }
            },
            clear_attempted_order=True,
        )
        rows3, eff3, _ = _eval(inp_filled, next2)
        self.assertEqual(rows3["O4"]["state"], "NORMAL")
        self.assertIs(rows3["O4"]["latched"], False)
        self.assertEqual(eff3["symbol:TQQQ"], "NORMAL")

    def test_o5_rejection_counting_to_third_rejection_halt(self) -> None:
        # 1st rejection
        inp1, prior0 = _make_case({"pretrade": {"attempted_order": {"long_only": False}}})
        rows1, eff1, next1 = _eval(inp1, prior0)
        self.assertEqual(rows1["O5"]["state"], "NORMAL")
        self.assertIs(rows1["O5"]["would_have_tripped"], True)
        self.assertIs(rows1["O5"]["latched"], False)
        self.assertEqual(rows1["O5"]["reason_class"], "pretrade_limit_violation")
        self.assertEqual(rows1["O5"]["rejections_this_session"], 1)
        self.assertEqual(eff1["account"], "NORMAL")

        # 2nd rejection
        inp2, _ = _make_case(
            {"pretrade": {"attempted_order": {"within_settled_cash": False}}}
        )
        rows2, eff2, next2 = _eval(inp2, next1)
        self.assertEqual(rows2["O5"]["state"], "NORMAL")
        self.assertIs(rows2["O5"]["would_have_tripped"], True)
        self.assertIs(rows2["O5"]["latched"], False)
        self.assertEqual(rows2["O5"]["rejections_this_session"], 2)
        self.assertEqual(eff2["account"], "NORMAL")

        # 3rd rejection trips HALT and latches across all scopes
        inp3, _ = _make_case({"pretrade": {"attempted_order": {"size_within_max": False}}})
        rows3, eff3, next3 = _eval(inp3, next2)
        self.assertEqual(rows3["O5"]["state"], "HALT")
        self.assertIs(rows3["O5"]["would_have_tripped"], True)
        self.assertIs(rows3["O5"]["latched"], True)
        self.assertEqual(rows3["O5"]["rejections_this_session"], 3)
        self.assertEqual(eff3["account"], "HALT")
        self.assertTrue(all(state == "HALT" for state in eff3.values()))

        # Persists without re-arm even with no attempted order
        inp_idle, _ = _make_case(clear_attempted_order=True)
        rows4, eff4, _ = _eval(inp_idle, next3, events=[])
        self.assertEqual(rows4["O5"]["state"], "HALT")
        self.assertIs(rows4["O5"]["latched"], True)
        self.assertEqual(rows4["O5"]["reason_class"], "latched_prior_trip")
        self.assertEqual(eff4["account"], "HALT")

        # Owner re-arm resets O5 to NORMAL
        rows5, eff5, _ = _eval(
            inp_idle,
            next3,
            events=[{"row_id": "O5", "action": "owner_re_arm"}],
        )
        self.assertEqual(rows5["O5"]["state"], "NORMAL")
        self.assertIs(rows5["O5"]["would_have_tripped"], False)
        self.assertIs(rows5["O5"]["latched"], False)
        self.assertEqual(rows5["O5"]["rejections_this_session"], 0)
        self.assertEqual(eff5["account"], "NORMAL")

    def test_o6_hash_mismatch(self) -> None:
        inp_ok, prior0 = _make_case(clear_attempted_order=True)
        rows_ok, _, _ = _eval(inp_ok, prior0)
        self.assertEqual(rows_ok["O6"]["state"], "NORMAL")
        self.assertIs(rows_ok["O6"]["would_have_tripped"], False)

        inp_bad, _ = _make_case(
            {"policy": {"loaded_hash": "0" * 64}},
            clear_attempted_order=True,
        )
        rows_bad, eff_bad, next_bad = _eval(inp_bad, prior0)
        self.assertEqual(rows_bad["O6"]["state"], "HALT")
        self.assertIs(rows_bad["O6"]["would_have_tripped"], True)
        self.assertIs(rows_bad["O6"]["latched"], True)
        self.assertEqual(rows_bad["O6"]["reason_class"], "policy_hash_mismatch")
        self.assertTrue(all(state == "HALT" for state in eff_bad.values()))

        # Restoring matching hash without re-arm remains latched HALT
        rows_latched, _, next_latched = _eval(inp_ok, next_bad, events=[])
        self.assertEqual(rows_latched["O6"]["state"], "HALT")
        self.assertIs(rows_latched["O6"]["latched"], True)
        self.assertEqual(rows_latched["O6"]["reason_class"], "latched_prior_trip")

        # Owner re-arm clears after hashes match
        rows_rearmed, eff_rearmed, _ = _eval(
            inp_ok,
            next_latched,
            events=[{"row_id": "O6", "action": "owner_re_arm"}],
        )
        self.assertEqual(rows_rearmed["O6"]["state"], "NORMAL")
        self.assertIs(rows_rearmed["O6"]["latched"], False)
        self.assertEqual(eff_rearmed["account"], "NORMAL")

    def test_o8_kill_switch_via_authorized_events_only(self) -> None:
        # In-band kill_switch key in validated_inputs is ignored; only authorized_events triggers O8
        inp_ignored, prior0 = _make_case(
            {"kill_switch": True},
            clear_attempted_order=True,
        )
        rows_ignored, eff_ignored, _ = _eval(inp_ignored, prior0, events=[])
        self.assertEqual(rows_ignored["O8"]["state"], "NORMAL")
        self.assertIs(rows_ignored["O8"]["would_have_tripped"], False)
        self.assertIs(rows_ignored["O8"]["latched"], False)
        self.assertEqual(eff_ignored["account"], "NORMAL")

        inp_base, _ = _make_case(clear_attempted_order=True)
        rows_kill, eff_kill, next_kill = _eval(
            inp_base, prior0, events=[{"event_type": "kill_switch"}]
        )
        self.assertEqual(rows_kill["O8"]["state"], "HALT")
        self.assertIs(rows_kill["O8"]["would_have_tripped"], True)
        self.assertIs(rows_kill["O8"]["latched"], True)
        self.assertEqual(rows_kill["O8"]["reason_class"], "owner_kill_switch")
        self.assertTrue(all(state == "HALT" for state in eff_kill.values()))

        # Persists until explicit owner clear event
        rows_latched, _, next_latched = _eval(inp_base, next_kill, events=[])
        self.assertEqual(rows_latched["O8"]["state"], "HALT")
        self.assertIs(rows_latched["O8"]["latched"], True)
        self.assertEqual(rows_latched["O8"]["reason_class"], "latched_prior_trip")

        rows_clear, eff_clear, _ = _eval(
            inp_base,
            next_latched,
            events=[{"row_id": "O8", "action": "owner_clear"}],
        )
        self.assertEqual(rows_clear["O8"]["state"], "NORMAL")
        self.assertIs(rows_clear["O8"]["latched"], False)
        self.assertEqual(eff_clear["account"], "NORMAL")

    def test_j1_blocked_and_trim_thresholds(self) -> None:
        # Baseline joint_cap=0.60 => 110% trim threshold=0.66
        cases = [
            ("0.60", False, False, False, "none", "0.00"),
            ("0.61", True, True, False, "joint_cap_exceeded", "-0.01"),
            ("0.66", True, True, False, "joint_cap_exceeded", "-0.06"),
            ("0.67", True, True, True, "joint_cap_trim_required", "-0.07"),
        ]
        for exposure, tripped, blocked, trim_req, reason_cls, headroom in cases:
            with self.subTest(joint_exposure=exposure):
                inp, prior = _make_case(
                    {"joint": {"joint_exposure": exposure, "joint_cap": "0.60"}},
                    clear_attempted_order=True,
                )
                rows, eff, _ = _eval(inp, prior)
                j1 = rows["J1"]
                hdr = j1["headroom_output"]
                self.assertEqual(j1["scope"], "joint")
                self.assertEqual(j1["state"], "NORMAL")
                self.assertIs(j1["latched"], False)
                self.assertIs(j1["would_have_tripped"], tripped)
                self.assertEqual(j1["reason_class"], reason_cls)
                self.assertIs(hdr["increases_blocked"], blocked)
                self.assertIs(hdr["trim_required_next_session"], trim_req)
                self.assertEqual(hdr["headroom"], headroom)
                self.assertEqual(hdr["trim_threshold_110pct"], "0.66")
                self.assertEqual(eff["joint"], "NORMAL")


class TestFailClosedFixes(unittest.TestCase):
    def test_l0_missing_joint_exposure_fails_closed(self) -> None:
        for variant in ("pop", "none", "invalid"):
            with self.subTest(variant=variant):
                inp, prior = _make_case(clear_attempted_order=True)
                if variant == "pop":
                    inp["joint"].pop("joint_exposure", None)
                elif variant == "none":
                    inp["joint"]["joint_exposure"] = None
                else:
                    inp["joint"]["joint_exposure"] = "bad"

                rows, _, _ = _eval(inp, prior)
                l0 = rows["L0"]
                cap_out = l0["cap_output"]
                self.assertEqual(l0["state"], "NORMAL")
                self.assertIs(l0["would_have_tripped"], True)
                self.assertIs(l0["latched"], False)
                self.assertEqual(l0["reason_class"], "missing_input")
                self.assertIsNone(cap_out["joint_exposure"])
                self.assertEqual(cap_out["exposure_cap"], "0.50")
                self.assertEqual(cap_out["proposed_exposure"], "0.35")
                self.assertIsNone(cap_out["effective_capped_exposure"])
                self.assertIs(cap_out["cap_breached"], True)
                self.assertIs(cap_out["increases_blocked"], True)

    def test_v2_malformed_corporate_action_fails_closed(self) -> None:
        malformed_payloads: list[tuple[str, Any]] = [
            ("empty_dict", {}),
            (
                "missing_type",
                {
                    "announced": True,
                    "detected_in_price": True,
                    "ledger_adjusted": True,
                    "reconciles_exactly": True,
                },
            ),
            (
                "none_type",
                {
                    "type": None,
                    "announced": True,
                    "detected_in_price": True,
                    "ledger_adjusted": False,
                    "reconciles_exactly": False,
                },
            ),
            (
                "invalid_type",
                {
                    "type": "merger",
                    "announced": True,
                    "detected_in_price": True,
                    "ledger_adjusted": True,
                    "reconciles_exactly": True,
                },
            ),
            ("non_dict", "split"),
        ]
        for label, payload in malformed_payloads:
            with self.subTest(payload=label):
                inp, prior = _make_case(clear_attempted_order=True)
                inp["funds"]["TQQQ"]["corporate_action"] = copy.deepcopy(payload)
                rows, eff, _ = _eval(inp, prior)
                v2 = rows["V2"]
                self.assertEqual(v2["state"], "HALT")
                self.assertIs(v2["would_have_tripped"], True)
                self.assertIs(v2["latched"], False)
                self.assertEqual(v2["reason_class"], "missing_input")
                self.assertEqual(v2["by_fund"]["TQQQ"]["state"], "HALT")
                self.assertIs(v2["by_fund"]["TQQQ"]["would_have_tripped"], True)
                self.assertIs(v2["by_fund"]["TQQQ"]["latched"], False)
                self.assertEqual(v2["by_fund"]["TQQQ"]["reason_class"], "missing_input")
                self.assertEqual(v2["by_fund"]["SOXL"]["state"], "NORMAL")
                self.assertEqual(eff["fund:TQQQ"], "HALT")
                self.assertEqual(eff["fund:SOXL"], "NORMAL")
                self.assertEqual(eff["account"], "NORMAL")

        # Contrast: None means no corporate action and remains NORMAL
        inp_none, prior_none = _make_case(clear_attempted_order=True)
        inp_none["funds"]["TQQQ"]["corporate_action"] = None
        rows_none, eff_none, _ = _eval(inp_none, prior_none)
        self.assertEqual(rows_none["V2"]["state"], "NORMAL")
        self.assertIs(rows_none["V2"]["would_have_tripped"], False)
        self.assertIs(rows_none["V2"]["latched"], False)
        self.assertEqual(rows_none["V2"]["reason_class"], "none")
        self.assertEqual(rows_none["V2"]["by_fund"]["TQQQ"]["state"], "NORMAL")
        self.assertEqual(eff_none["fund:TQQQ"], "NORMAL")


if __name__ == "__main__":
    unittest.main()
