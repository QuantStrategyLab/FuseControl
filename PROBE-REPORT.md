# FUSE-1 Neon Fidelity Probe Report

## 1. Identity & Probe Boundaries

- **Demonstration:** FUSE-1 control-row specification and reference engine probe (`fuse-eval-spec/v1`).
- **Executor:** Antigravity Orchestrator Neon (`gemini-pro-orchestrator-neon`), run as a parallel fidelity probe.
- **Branch & Publication:** Local branch `demo/fuse1-neon-probe` only — never pushed, no PR opened, and no hosted CI run.
- **Fallback of Record:** The Sonnet demonstration remains the fallback of record.
- **Execution Envelope (`results/matrix_result.json`, `results/battery_result.json`):**
  - `spec_version`: `fuse-eval-spec/v1`
  - `observation_class`: `synthetic`
  - `enforcement_mode`: `shadow_would_have_tripped`
  - `loss_breakers_armed`: `false`
  - `kelly_applied`: `false`
  - `orders_placed`: `0`

---

## 2. Freeze Record (`goldens/FREEZE.json`)

- **Initial Freeze (before first full engine matrix run, commit `0a910dd`):**
  - `original_golden_table_sha256`: `0d2316001922789368a5d93c1629912e7d67f3290e92f7e6852bf28faa2f28ee`
  - `scenario_fixtures_sha256`: `21bfd04b8eb2395ae2b0de8c53cc26b79fd6b7acf7507ba3c893eb7144f523d6`
  - Scope frozen: `264` base cells (`11` scenarios x `24` rows) and `42` tier repetitions (`14` cases x `3` tiers).
- **Correction 1 (commit `433d0ea`):**
  - **Cells corrected:** `22` `L1`/`L3` base cells (all `11` base scenarios x `{L1, L3}`).
  - **Governance & Citation:** `BRIEF-FUSE-1.md` §6.2 rule 4; citation `BRIEF 5.1 + 4.3` (adding `L1` `locked_against_loosening`/`notify` and `L3` `cooling_off_days_remaining`/`locked_flat`/`loss_record_cleared` structured outputs on benign base evaluations to match `tier_repetitions`).
  - **Re-freeze hash (`correction_1.new_golden_table_sha256` / active `golden_table_sha256`):** `d65d3d903804c1e93c60d316a73e4298fa447ed98206721c4c1a5cf8f9a5107b`.

---

## 3. Skeleton Baseline

Recorded at commit `bf3de44` (`label: "skeleton-baseline"`, `engine_hash: 9a05c8f897fa80c114c9a127422daf1a2b1b5de15503ee0d586ced62cfeb76a8`) against the original frozen golden table (`0d2316001922789368a5d93c1629912e7d67f3290e92f7e6852bf28faa2f28ee`):

| Metric | Baseline Result |
| --- | --- |
| Base cells | `191/264` passed (`73` failed) |
| Tier repetitions | `9/42` passed (`33` failed) |
| Effective states by scope | `6/11` passed (`5` failed) |

---

## 4. Final Acceptance Matrix (`F1-A01` through `F1-A14`)

Source bundles: `results/matrix_result.json`, `results/battery_result.json`, and `tests/test_engine.py`.

| ID | Check | Status | Exact Evidence & Counts |
| --- | --- | --- | --- |
| `F1-A01` | `id_set_equality` | **PASS** | Set equality `24=24=24` (`expected_count=24`, `spec_count=24`, `spec_unique_count=24`, `engine_rows_by_id_count=24`, `engine_row_ids_const_count=24`, `spec_duplicates=0`). |
| `F1-A02` | `spec_linter` | **PASS** | `0` missing of `168` field checks (`24` rows x `7` required fields: `trigger`, `required_inputs`, `action`, `state_contribution`, `kind`, `scope`, `clearing`). |
| `F1-A03` | Base matrix | **PASS** | `264/264` base cells passed (`0` failed); `11/11` `effective_state_by_scope` matches; `envelope_match=true` in all `11` scenarios. |
| `F1-A04` | Tier repetitions | **PASS** | `42/42` tier repetitions passed (`0` failed; `14` cases x `3` tiers: `conservative`, `balanced`, `aggressive`). |
| `F1-A05` | `determinism` | **PASS** | `3` runs, `1` unique canonical hash (`9bf0421e270828520fff47c88451121a63e340dcaf657ccde5a6e0c28cb9e38b`), `matches_committed=1`; each run `264/264` base, `11/11` effective states, `42/42` tier repetitions. |
| `F1-A06` | `fail_closed` | **PASS** | `172` variants tested across `61` required input entries (`159` fail-closed tripped, `9` by-design exclusions recorded with `0` violations, `4` reconciled auto-cleared `V2` variants), `0` silent passes, `0` exceptions, `10/10` explicit assertions passed. |
| `F1-A07` | `persistence` | **PASS** | `5/5` round-trip equal (`restart`, `deposit`, `withdrawal`, `split`, `tier_change`; `roundtrip_equal=true`), preserving latched `L2`/`O3` and `V4` `TQQQ` `below_threshold_sessions: 4 -> 5`. |
| `F1-A08` | `precedence` | **PASS** | `4/4` fixtures passed (`a_o3_o4_v3_halt`, `b_o4_l2_scoped`, `c_v3_v1_same_fund`, `d_l6_halt`). |
| `F1-A09` | `exposure_invariant` | **PASS** | `57` evaluations checked (`11` matrix scenarios + `42` tier repetitions + `4` precedence fixtures), `0` violations. |
| `F1-A10` | `stub_swap` | **PASS** | Stub-swap shape equality across `24` rows (`0` shape mismatches, `signature_match=true`, `key_set_match=true`, `scope_match=true`, `4` engine files hashed) plus `engine_hash` echoed (`manifest_hash_echoed=true`). `engine_hash`: `f3be78a3e06001cdb9bdf71f04d4b15ffc7df0b3f4a4a2518b42a5f69ec83d70`; `engine_bytes_sha256`: `aadb1730970386d39d0077ef92c3a9f75deda97cc7b5ca08d647d57390a6cb0f`. |
| `F1-A11` | `register_proof` | **PASS** | `3` unresolved parameters `null`-valued (`V7` spread width, `O5` price collar, `V5` decay tolerance; `UNRESOLVED-FAIL-CLOSED`), `0` numeric literals in `4` engine files, `1` `tolerance: null` dict verified (`engine/rows.py:1813`), `3/3` runtime checks passed. |
| `F1-A12` | `V2` corporate-action branches | **PASS** | `V2` pending branch verified in base matrix (`split` `fund:TQQQ` `HALT` not latched; `reverse_split` `fund:SOXL` `HALT` not latched); reconciled auto-clear branch verified in `fail_closed` battery (`4` `reconciled_auto_cleared_variants`) and unit test `test_v2_all_three_branches`; mismatch latched-breaker branch verified in `tests/test_engine.py::test_v2_all_three_branches`. |
| `F1-A13` | `offline_scan` | **PASS** | Offline scan clean across `6` scanned files (`engine/*.py`, `harness/*.py`; `tests/` added in subsequent commit `1646b05`): `0` forbidden imports, `0` forbidden URLs, `0` forbidden calls, `0` forbidden tokens, `17` benign broker references (`broker_record_field` / `reconciliation_prose`), `0` disallowed broker occurrences. |
| `F1-A14` | Hosted CI / PR workflow | **NOT APPLICABLE** | Not applicable to this probe (no push, no PR, no hosted CI by instruction). |

---

## 5. Findings & Adjudications

### Fail-Closed Battery Triage (7 Initial Silent Passes)

- **2 genuine engine gaps identified and fixed (commit `1657b4c`, `engine/rows.py`):**
  1. **`L0` missing/invalid `joint_exposure`:** Previously `L0` accepted missing `joint_exposure` when `max_loss_cap` and `proposed_exposure` were valid. Updated `_eval_L0_stateful` so missing/invalid `joint_exposure` (as well as missing/invalid `max_loss_cap` or `proposed_exposure`) fails closed (`state: "NORMAL"`, `would_have_tripped: true`, `latched: false`, `reason_class: "missing_input"`, `effective_capped_exposure: null`, `cap_breached: true`, `increases_blocked: true`).
  2. **`V2` malformed `corporate_action` container:** Previously non-dict containers latched `HALT` and dicts missing/invalid `type` defaulted `type` to `"corporate_action"` and checked adjustment flags. Updated `_eval_V2_stateful` so a non-null `corporate_action` container that is not a dict or lacks a valid `type` (`split`, `reverse_split`, `distribution`) fails closed into pending-`HALT` (`state: "HALT"`, `would_have_tripped: true`, `latched: false`, `reason_class: "missing_input"` in the affected fund scope, while preserving any prior latched `V2` breaker).
- **Remaining cases recorded as `9` by-design exclusions with rationale (`0` exclusion violations in `results/battery_result.json`):**
  - `V2` `fund.corporate_action.type` (`container_key_missing`, `container_null`): absent/null `corporate_action` is the benign "no corporate action" sentinel.
  - `V3` `fund.fund_event` (`container_key_missing`, `container_null`): absent/null `fund_event` is the benign "no fund event" sentinel.
  - `O4` `orders.pending.symbol` (`container_null`): `orders.pending=null` is the benign "no pending order" sentinel (omitting the `pending` key still fails closed).
  - `O8` `authorized_events` (`none`): structural `C-FUSE-EVAL` signature argument (`null` means no owner kill-switch command issued).
  - `O9` `change_descriptors` (`omitted`, `none`): benign "no parameter changes" sentinel; `O9` `authorized_events` (`none`): structural `C-FUSE-EVAL` signature argument when no parameter changed.

### Interpretation Treatments a Reviewer Should Check First

1. **`V5` / `V7` / `O5` unresolved-parameter fail-closed outcomes in every evaluation (`BRIEF-FUSE-1.md` §4.5 + §12):** `V5` (60-session decay tolerance), `V7` (spread width), and `O5` (price collar) carry `UNRESOLVED-FAIL-CLOSED` dispositions with `proposal_value: null`. Under §4.5 + §12, every evaluation depending on them fails closed (`would_have_tripped: true`, `reason_class: "unresolved_fail_closed"`, `latched: false`) at its diagnostic or gate level with `state_contribution: NONE` (`state: "NORMAL"`), leaving `effective_state_by_scope` at `NORMAL` in clean scenarios.
2. **`O5` fail-closed rejections counting toward the 3-rejection `HALT` (`BRIEF-FUSE-1.md` §4.3 + §4.5):** Each fail-closed pre-trade rejection on an attempted order increments `rejections_this_session` (`0 -> 1` in single-attempt base matrix evaluations) rather than emitting a non-counting warning; reaching 3 rejections in one session latches account-scoped `HALT`.
3. **`V2` pending state not latched (`BRIEF-FUSE-1.md` §4.3 + §5.4 `C-SA-CA`):** When a corporate action is announced or detected in price with `ledger_adjusted: false`, `V2` enters fund-scoped `HALT` with `latched: false` (`reason_class: "corporate_action_pending"`) so the exact-reconciliation auto-clear branch remains reachable; `V2` latches (`latched: true`) only when `ledger_adjusted: true` and `reconciles_exactly: false`.
4. **Account-scope `HALT` dominating narrower scopes (`BRIEF-FUSE-1.md` §4.1; `engine/evaluate.py:_resolve_effective_states`):** Effective states resolve independently across `account`, `fund:TQQQ`, `fund:SOXL`, `symbol:TQQQ`, `symbol:SOXL`, and `joint` using precedence `HALT > ORDER-UNKNOWN (symbol) > DE-RISK > NO-NEW-RISK > NORMAL`; when `account` reaches `HALT`, it dominates all narrower scopes (`fund:*`, `symbol:*`, `joint` forced to `HALT`), whereas fund-scoped `HALT` or symbol-scoped `ORDER-UNKNOWN` does not widen to `account`.

---

## 6. Cells the Engine Could Not Satisfy

- **None** — the final engine satisfies `264/264` base matrix cells (`11/11` scope effective states) and `42/42` tier-repetition cells with **zero failing cells**.
- **Cells passing only under the recorded interpretation treatments in Section 5** (`35` distinct base matrix cells, `0` tier-repetition cells, plus battery fixtures and unit tests):
  - **`V5` / `V7` / `O5` unresolved-parameter fail-closed outcomes (`BRIEF` §4.5 + §12):** `33` base cells — `V5`, `V7`, and `O5` across all `11` base scenarios (`normal`, `deposit`, `withdrawal`, `split`, `reverse_split`, `stale`, `missing`, `restart`, `tier_change`, `holiday`, `half_day`), together with `effective_state_by_scope` across those `11` scenarios not escalating from `V5`/`V7`/`O5`.
  - **`O5` fail-closed rejections counting toward the 3-rejection `HALT`:** the `11` `O5` base cells listed above (`rejections_this_session: 0 -> 1`, `state: "NORMAL"`, `latched: false`), plus 3rd-rejection `HALT` escalation verified in `tests/test_engine.py::test_o5_rejection_counting_to_third_rejection_halt`.
  - **`V2` pending state not latched:** `2` base cells — `split.V2` (`fund:TQQQ`) and `reverse_split.V2` (`fund:SOXL`), plus the `4` malformed-container explicit assertions in `F1-A06` (`V2_malformed_missing_type`, `V2_malformed_none_type`, `V2_malformed_invalid_type`, `V2_malformed_empty_container`).
  - **Account-scope `HALT` dominating narrower scopes (`BRIEF` §4.1):** `0` base matrix cells and `0` tier-repetition cells (no base scenario triggers account `HALT`); exercised by `2` `F1-A08` precedence fixtures (`a_o3_o4_v3_halt`, `d_l6_halt`) and `tests/test_engine.py::test_o5_rejection_counting_to_third_rejection_halt`.
- *(Completeness note: `goldens/DERIVATION.md` §3.4–§3.5 also records two additional derivation treatments outside the four above: `restart.V4` for `V4` clearing-counter persistence `4 -> 5`, and the `3` `L2` `exact_2D_over_3_trip` tier-repetition cells across `conservative`/`balanced`/`aggressive` for `'reaches'` inclusivity at `2D/3`.)*

---

## 7. Process Notes

- Four long orchestrator runs were lost to provider `503`s / interruptions with zero or partial artifacts.
- The probe was completed via small single-deliverable dispatches with checkpoint commits and two disk-state recoveries.
- The `agy-pool` picker failed mid-session (its probe model `gemini-4-carbon-low` was no longer recognized), and later dispatches went through `dev-run.sh` directly under the same guard.

---

## 8. Unit Tests

- **Suite:** `tests/test_engine.py` (commit `1646b05`), run via `python3 -m unittest discover -s tests -v`.
- **Result:** **17 run, all passing** (`Ran 17 tests in 0.070s — OK`).
- **Coverage across 5 test classes:**
  - `TestEvaluateContractAndShadowMode` (`3`): pinned `evaluate` signature, exact 24 row IDs, shadow-mode invariants.
  - `TestLossThresholdsAndLatch` (`2`): `L1`–`L4` threshold boundaries across two tiers, `L2` latch persistence and owner re-arm.
  - `TestVehicleRows` (`3`): `V1` deviation thresholds, `V2` all three branches (pending unlatched `HALT`, reconciled auto-clear, mismatch latched `HALT` + re-arm), `V4` trip and 10-session clearing counter.
  - `TestOpsAndJointRows` (`7`): `O1` stale/missing, `O2` holiday, `O4` symbol-scoped `ORDER-UNKNOWN`, `O5` 3-rejection `HALT` counting + re-arm, `O6` hash mismatch, `O8` kill switch via `authorized_events` only, `J1` blocked and trim thresholds.
  - `TestFailClosedFixes` (`2`): `L0` missing `joint_exposure` fail-closed regression, `V2` malformed `corporate_action` fail-closed regression.

---

## 9. Full Commit List

All probe checkpoints on `demo/fuse1-neon-probe` prior to this report commit (plus the `PROBE-REPORT.md` commit itself at `HEAD`):

| # | Short Hash | Full Hash | Timestamp | Subject |
| --- | --- | --- | --- | --- |
| 1 | `1d91884` | `1d91884326b806cfc84847b2707a0c9c7e0a2e06` | `2026-11-22 01:40:49 +0800` | `chore: neon probe workspace check` |
| 2 | `d642c0a` | `d642c0aa92da5cef6c3135cf245eacc1899b572b` | `2026-11-22 01:45:15 +0800` | `feat(spec): add fuse-eval-spec v1 and disposition register` |
| 3 | `2d0406a` | `2d0406a6aaf0961b8651ebf82fe0249890e424bc` | `2026-11-22 01:54:22 +0800` | `feat(goldens): add frozen scenario input fixtures` |
| 4 | `caaf4d4` | `caaf4d49a57747b8ba6e75d9774aaf5fba34f959` | `2026-11-22 02:02:12 +0800` | `feat(goldens): derive 264-cell golden table from spec` |
| 5 | `0a910dd` | `0a910ddea6712cb0425681fc089c6e57570a3d69` | `2026-11-22 02:13:52 +0800` | `feat(goldens): add tier repetitions, derivation record, freeze` |
| 6 | `bf3de44` | `bf3de44b370ce47aa6a1e575ab544a08cee96f6f` | `2026-11-22 02:21:15 +0800` | `feat(harness): add skeleton engine, matrix harness, baseline` |
| 7 | `056f2b9` | `056f2b9c5a3a6144b4c979c464365e85349aa854` | `2026-11-22 02:40:42 +0800` | `feat(engine): implement loss rows L0-L6` |
| 8 | `433d0ea` | `433d0ea233d1fc563eb8c84904b6ba17190c1002` | `2026-11-22 02:45:24 +0800` | `fix(goldens): correct L1/L3 base cells per brief 5.1 citation` |
| 9 | `0a8c891` | `0a8c891ac76232814b61a9873b543bf8be58ae65` | `2026-11-22 03:00:44 +0800` | `feat(engine): implement vehicle rows V1-V7` |
| 10 | `5bcf4fe` | `5bcf4fed322106e39e651aa26ce782a1e23ee8d2` | `2026-11-22 03:14:38 +0800` | `feat(engine): implement ops rows and precedence aggregation` |
| 11 | `1657b4c` | `1657b4cb2ec6402729b42bbf7f71b0e0af194ff6` | `2026-11-22 03:38:07 +0800` | `fix(engine): fail closed on missing L0 inputs and malformed V2` |
| 12 | `1646b05` | `1646b050462fcc384cc2f94e8d8e65fc34385712` | `2026-11-22 03:44:47 +0800` | `test(fuse): add engine unit tests` |
