# Golden Derivation Record (`fuse-eval-spec/v1`)

- **Spec version:** `fuse-eval-spec/v1`
- **Observation class:** `synthetic` (`enforcement_mode: shadow_would_have_tripped`, `loss_breakers_armed: false`, `kelly_applied: false`, `orders_placed: 0`)
- **Primary binding sources:**
  - `~/workspace/quant-s2/fuse/BRIEF-FUSE-1.md` §4 (L211–L345), §5.1 (L369–L400), §5.4 (L439–L447), §6 (L449–L507), §7 (L509–L525), §12 (L596–L617)
  - `~/workspace/quant-s2/fable-roadmap/REPORT.md` §4.3 (L1204–L1239) and §4.4 (L1267–L1356)
  - `spec/fuse_eval_spec.json`, `spec/disposition_register.json`, `goldens/scenario_fixtures.json`

---

## 1. Independence Protocol (`BRIEF-FUSE-1.md` §6.2)

1. **Spec-first derivation:** Every cell in `goldens/golden_table.json` — all 264 base matrix cells (24 named rows × 11 frozen scenarios) and all 42 tier-repetition cells (14 cases × 3 tiers) — was derived solely from the frozen specification text (`BRIEF-FUSE-1.md` §4 / `REPORT.md` §4.4, §4.3 tier constants, and `§4.5` dispositions) applied to the frozen input fixtures in `goldens/scenario_fixtures.json` and the concrete tier-repetition inputs embedded in `goldens/golden_table.json`.
2. **Temporal separation:** This derivation record and `goldens/golden_table.json` are authored and SHA-256 hash-frozen in `goldens/FREEZE.json` during Phase B, prior to implementing any reference engine logic (`engine/` does not yet exist) and prior to the first full matrix run.
3. **Adjudication discipline:** Any subsequent mismatch between the reference engine and these goldens is adjudicated against the cited spec lines below; a golden cell may be modified only with a written spec citation demonstrating a misreading of §4 / §4.4, accompanied by a recorded re-freeze hash and full re-run.

---

## 2. State Model, Precedence, Whole-Set Rules & Dispositions

- **Control states and order permissions** (`BRIEF-FUSE-1.md` §4.1 L220–L230; `REPORT.md` §4.4 L1269–L1276): `NORMAL`, `NO-NEW-RISK`, `DE-RISK`, `HALT`, `ORDER-UNKNOWN`.
- **Per-scope precedence** (`BRIEF-FUSE-1.md` §4.1 L231–L237): `HALT > ORDER-UNKNOWN (symbol) > DE-RISK > NO-NEW-RISK > NORMAL`. Precedence resolves independently per scope (`account`, `fund:TQQQ`, `fund:SOXL`, `symbol:TQQQ`, `symbol:SOXL`, `joint`). A fund-scoped trip does not silently widen to `account`.
- **State contribution vs row outputs** (`BRIEF-FUSE-1.md` §4.1 L238–L244): `L0` and `J1` are `limit` rows with their own structured outputs (`cap_output`, `headroom_output`) and `state_contribution: NONE`; `L1` is an `interlock` contributing `notify` + loosening lock (`state_contribution: NONE`); `V5` and `V6` are `diagnostic` rows with `diagnostic_output`; `V7` and `O2` are order-level / session-level gates whose immediate refusal is `"the order is not sent"` / `"no order"` (`state_contribution: NONE`).
- **Interlock vs Breaker** (`BRIEF-FUSE-1.md` §4.2 L246–L258; `REPORT.md` §4.4 L1278–L1281):
  - **Interlock:** blocks while an external condition holds and clears automatically once the row's clearing condition holds for its stated duration (`L1`, `L5`, `V4`, `V7`, `O1`, `O2`).
  - **Breaker:** latches on a loss or integrity doubt (`latched: true`) and clears **only** via an explicit event in `authorized_events` (`L2`, `L3`, `L4`, `L6`, `V1`, `V3`, `O3`, `O6`, `O7`, `O9`; `V2` and `O4` have explicit auto-clear vs breaker-latch branches; `O5` latches on the third rejection in a session).
- **Whole-set rules** (`BRIEF-FUSE-1.md` §4.4 L301–L323; `REPORT.md` §4.4 L1347–L1354):
  - Rule 1: No trip can raise exposure or mutate a policy parameter.
  - Rule 2: No row is a price stop on a fund.
  - Rule 3: Every failure mode fails closed; trip state survives restart, deposit, withdrawal, split, and tier change.
  - Rules 4–5: `L0` and `L2–L4` are computed and recorded in shadow mode (`shadow_would_have_tripped`, `loss_breakers_armed: false`).
  - Volatility-drag rule 5 (`BRIEF-FUSE-1.md` §4.4 L319–L323; `REPORT.md` §4.4 L1330): missing volatility figure substitutes `max(last_valid, stress_default)` and blocks increases (`O1`), never returning 1 on missing.
- **Disposition register** (`BRIEF-FUSE-1.md` §4.5 L325–L345; `spec/disposition_register.json`):
  - `CONFIRMED-AS-SPEC`: `L6` 10% one-session index fall; `V1` 0.75 pp (1s) / 2.0 pp (5s); `V4` 2× long-run volatility.
  - `UNRESOLVED-FAIL-CLOSED`: `V7` spread width (`OI-COST-4` unresolved), `O5` price collar (`OI-COST-4` unresolved), `V5` 60-session decay tolerance (no stated value in frozen sources).

---

## 3. Explicit Interpretation Treatments

### 3.1 `V5` / `V7` / `O5` Unresolved-Parameter Fail-Closed at Gate Level with State Contribution `NONE`
- **Citations:** `BRIEF-FUSE-1.md` §4.5 L332–L334, L341; §12 L604–L610; §4.1 L238–L244; §4.3 L282, L284, L294; `REPORT.md` §4.4 L1303, L1305, L1340; `spec/disposition_register.json`.
- **Treatment:** Per §4.5, an `UNRESOLVED-FAIL-CLOSED` parameter exists as explicitly unresolved, must never be assigned a numeric default or `0`, and any evaluation depending on it fails closed. Per §12, the matrix must produce a determinate golden outcome for every cell, so cells depending on unresolved parameters take the fail-closed outcome as their golden. In all 11 base scenarios:
  - **`V5` (60-session decay tolerance):** `decay_shortfall_60s` and `decay_predicted_60s` cannot be cleared against an unresolved tolerance, so `V5` fails closed as a diagnostic notify (`would_have_tripped: true`, `reason_class: "unresolved_fail_closed"`, `latched: false`, `diagnostic_output.by_fund.<FUND>.notify: true`, `fail_closed: true`, `tolerance: null`, `persistent_sessions: 0 -> 1`). Because `V5` is a `diagnostic` row that escalates to `V1` (`NO-NEW-RISK`) only after persisting two months (`BRIEF-FUSE-1.md` §4.3 L282, `REPORT.md` §4.4 L1303), its single-session state contribution is `NONE` (`state: "NORMAL"`).
  - **`V7` (spread width):** Quote spread (`0.0002`) cannot clear an unresolved maximum spread width, so `V7` fails closed at its order-level interlock gate: `"the order is not sent"` (`would_have_tripped: true`, `reason_class: "unresolved_fail_closed"`, `latched: false`). Its specified action is order suppression rather than a control-state transition (`state_contribution: NONE`, `state: "NORMAL"`).
  - **`O5` (price collar):** Each scenario fixture presents one baseline compliant `attempted_order` (`pretrade.rejections_this_session: 0`). Because the `O5` price collar is `UNRESOLVED-FAIL-CLOSED`, the attempted order cannot pass pre-trade collar validation and fails closed with a single-order rejection (`would_have_tripped: true`, `reason_class: "unresolved_fail_closed"`, `rejections_this_session: 0 -> 1 < 3`). Under §4.3 L294 / `REPORT.md` §4.4 L1340, a single rejection rejects the order without raising an account control state (`state_contribution: NONE`, `state: "NORMAL"`, `latched: false`).
- **Resulting scope states:** Consequently, in `normal`, `deposit`, `withdrawal`, `tier_change`, `holiday`, and `half_day`, `effective_state_by_scope` remains `NORMAL` across all six scopes even though `V5`, `V7`, and `O5` record `would_have_tripped: true`.

### 3.2 `O5` Fail-Closed Rejection Counting Toward the 3-Rejection `HALT`
- **Citations:** `BRIEF-FUSE-1.md` §4.3 L294; §4.5 L332–L334, L341; `REPORT.md` §4.4 L1340.
- **Treatment:** `O5` states: *"The order is rejected; three rejections in one session: `HALT`"* (`kind: breaker on third rejection`). A fail-closed rejection caused by the unresolved price collar is a real pre-trade rejection, not a no-op warning: each fail-closed evaluation increments `rejections_this_session` by `1` (`0 -> 1` in the single-attempt base matrix cells). If `prior_row_state.O5.rejections_this_session` (or `pretrade.rejections_this_session`) reaches `2` before the current rejection (`2 -> 3`), the third rejection trips `O5` to account-scoped `HALT` with `latched: true` requiring owner re-arm.

### 3.3 `V2` Pending-Adjustment Not Latched
- **Citations:** `BRIEF-FUSE-1.md` §4.3 L279; §5.4 L444 (`C-SA-CA`); `REPORT.md` §4.4 L1300.
- **Treatment:** `V2` (`kind: breaker-with-auto-clear-branch`, scope `fund`) triggers `HALT` in the affected fund when a split, reverse split, or distribution is announced for the next two sessions or detected in price *"until the ledger, share count and high-water mark are adjusted"*, and clears automatically **only if** the adjusted ledger reconciles **exactly** to the broker (`ledger_adjusted=true` and `reconciles_exactly=true`); otherwise it becomes a latched breaker requiring owner re-arm (`ledger_adjusted=true` and `reconciles_exactly=false`). In `split` (`TQQQ`) and `reverse_split` (`SOXL`), the fixture sets `announced: true, detected_in_price: true, ledger_adjusted: false, reconciles_exactly: false`. Because the ledger adjustment has not yet run (`ledger_adjusted: false`), the corporate action is in the **pending-adjustment** state (`state: "HALT"`, `would_have_tripped: true`, `reason_class: "corporate_action_pending"`), and `latched` is **`false`** — the auto-clear branch remains reachable once exact reconciliation completes.

### 3.4 `V4` Clearing-Counter Persistence in `restart`
- **Citations:** `BRIEF-FUSE-1.md` §4.3 L281; §4.4 L307–L309; §5.1 L385–L389; §12 L614–L617; `REPORT.md` §4.4 L1302, L1351.
- **Treatment:** `V4` is a fund-scoped `interlock` (`NO-NEW-RISK` in that fund) that *"clears after ten sessions below the level"*. Under §4.4 rule 3 and §5.1, stateful clearing counters are carried explicitly in `prior_row_state` → `next_row_state` so restart is an exact serialization round-trip. In the `restart` scenario, `prior_row_state.V4.by_fund.TQQQ` restores `{active: true, below_threshold_sessions: 4}` while inputs are baseline-normal (`TQQQ forecast_vol = 0.22 < 2 * 0.24 = 0.48`). Because `V4` requires 10 consecutive sessions below `2 × long_run_vol` to auto-clear, the restored `active` flag stays `true`, `below_threshold_sessions` advances `4 -> 5 (< 10)`, and `V4` outputs `state: "NO-NEW-RISK"`, `would_have_tripped: true`, `latched: false`, `reason_class: "active_clearing_counter"` for `fund:TQQQ` (while `fund:SOXL` remains inactive/`NORMAL`).

### 3.5 `L2` `'reaches'` Inclusivity at Exactly `2D/3`
- **Citations:** `BRIEF-FUSE-1.md` §4.3 L267–L270; §7 D8 L525; `REPORT.md` §4.3 L1215–L1219; §4.4 L1288–L1291.
- **Treatment:** Rows `L1`–`L4` all phrase their triggers with *"reaches"* (`D/3`, `2D/3`, `D`, `D/10`), and §7 D8 confirms that `L2` crosses its threshold at *"exactly `2D/3` in each tier"*. `"reaches"` is therefore **inclusive (`>=`)**:
  - `L1`: `drawdown >= D/3` (equivalently `3 * drawdown >= D`)
  - `L2`: `drawdown >= 2D/3` (equivalently `3 * drawdown >= 2 * D`)
  - `L3`: `drawdown >= D`
  - `L4`: `session_loss >= D/10`
  In contrast, rows stating *"more than"* / *"differs ... by more than"* / *"exceeds"* / *"above"* (`V1`, `V5`, `V6`, `V7` spread, `O7` longer than, `J1`) use strict `>`, while `L6` (*"10% or more"*) and `V4` (*"at or above"*) use inclusive `>=`.
- **Precision note for `aggressive` tier (`D = 25000`):** Exact `2D/3 = 50000/3` is repeating (`16666.666...`). Truncating downward (e.g. `16666.666`) would fall strictly below `2D/3`. The tier-repetition fixture therefore uses the 28-digit Python `Decimal` ceiling `"16666.66666666666666666666667"` (`Decimal("2") * Decimal("25000") / Decimal("3")`), satisfying both 28-digit `Decimal` equality and exact rational `3 * drawdown >= 2 * D` (`50000.00000000000000000000001 >= 50000`).

---

## 4. Per-Row Specification Citations (24 Named Rows)

| Row | Family | Scope | Kind | State Contribution | Spec Citations (`BRIEF-FUSE-1.md` / `REPORT.md`) | Base Matrix Golden Summary (11 Scenarios) |
| --- | --- | --- | --- | --- | --- | --- |
| `L0` | loss | `account` | `limit` | `NONE` (`cap_output`) | Brief §4.1 L238–L244, §4.2 L255, §4.3 L266, §4.4 L313–L314; Report §4.3 L1224, §4.4 L1287, L1353 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`cap=0.50`, `proposed=0.35`, `cap_breached: false`); flow-adjusted note in `deposit`/`withdrawal`. |
| `L1` | loss | `account` | `interlock` | `NONE` (notify + lock loosening) | Brief §4.1 L240–L241, §4.2 L248–L250, §4.3 L267; Report §4.3 L1215–L1216, §4.4 L1288 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`drawdown=0 < D/3`); `D=0.15` (`D/3=2500`) in `tier_change`, `D=0.30` (`D/3=5000`) otherwise. |
| `L2` | loss | `account` | `breaker` | `NO-NEW-RISK` | Brief §4.1 L222–L223, §4.2 L251–L254, §4.3 L268, §4.4 L307–L309, L313–L314, §7 D8 L525; Report §4.3 L1217, §4.4 L1273, L1281, L1289, L1351, L1353 | `NORMAL` in 10 scenarios; `restart` restores `latched: true` prior L2 trip -> `NO-NEW-RISK` (`reason_class: "latched_prior_trip"`). |
| `L3` | loss | `account` | `breaker` | `DE-RISK` | Brief §4.1 L224–L226, §4.2 L251–L254, §4.3 L269, §4.4 L313–L314; Report §4.3 L1218, §4.4 L1274, L1281, L1290, L1353 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`drawdown=0 < D`). |
| `L4` | loss | `account` | `breaker` | `NO-NEW-RISK` | Brief §4.1 L222–L223, §4.2 L251–L254, §4.3 L270, §4.4 L313–L314; Report §4.3 L1219, §4.4 L1273, L1281, L1291, L1353 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`session_loss=0 < D/10`). |
| `L5` | loss | `account` | `interlock` | `NO-NEW-RISK` | Brief §4.2 L248–L250, §4.3 L271, §4.5 L343–L345, §12 L611–L613; Report §4.4 L1292 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`mwcb_level=0`, `clean_session=true`). |
| `L6` | loss | `account` | `breaker` | `HALT` | Brief §4.1 L227–L228, §4.2 L251–L254, §4.3 L272, §4.5 L338, L343–L345; Report §4.4 L1275, L1293 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`mwcb_level=0`, `index_session_fall=0 < 0.10`, `CONFIRMED-AS-SPEC`). |
| `V1` | vehicle | `fund` | `breaker` | `NO-NEW-RISK` | Brief §4.1 L233–L237, §4.2 L251–L254, §4.3 L278, §4.5 L339; Report §4.4 L1299 | `NORMAL` in all 11 base scenarios (`0.10pp <= 0.75pp`, `0.30pp <= 2.0pp`, `CONFIRMED-AS-SPEC`). |
| `V2` | vehicle | `fund` | `breaker-with-auto-clear-branch` | `HALT` | Brief §4.1 L227–L228, L233–L237, §4.2 L251–L254, §4.3 L279, §5.4 L444; Report §4.4 L1300 | `NORMAL` in 9 scenarios; `HALT` (`latched: false`, `reason_class: "corporate_action_pending"`) in `fund:TQQQ` for `split` and `fund:SOXL` for `reverse_split`. |
| `V3` | vehicle | `fund` | `breaker` | `DE-RISK` | Brief §4.1 L224–L226, L233–L237, §4.2 L251–L254, §4.3 L280; Report §4.4 L1301, L1307 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`fund_event: null`). |
| `V4` | vehicle | `fund` | `interlock` | `NO-NEW-RISK` | Brief §4.1 L233–L237, §4.2 L248–L250, §4.3 L281, §4.4 L319–L323, §4.5 L340, §12 L614–L617; Report §4.4 L1302, L1329–L1330 | `NORMAL` in 9 scenarios; `NO-NEW-RISK` in both funds for `missing` (substituted vol `max(0.22, 0.70)=0.70 >= 2*long_run_vol`); `NO-NEW-RISK` in `fund:TQQQ` for `restart` (counter `4 -> 5 < 10`). |
| `V5` | vehicle | `fund` | `diagnostic` | `NONE` (escalates to `V1` after 2 months) | Brief §4.1 L241–L244, §4.2 L256–L257, §4.3 L282, §4.5 L332–L334, §12 L604–L610, L614–L617; Report §4.4 L1303 | `state: "NORMAL"`, `would_have_tripped: true`, `latched: false`, `reason_class: "unresolved_fail_closed"` in all 11 base scenarios (`diagnostic_output` fail-closed notify, `persistent_sessions: 0 -> 1`). |
| `V6` | vehicle | `fund` | `diagnostic` | `NONE` (`diagnostic_output`) | Brief §4.1 L241–L244, §4.2 L256–L257, §4.3 L283; Report §4.4 L1304 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`0.0060 <= 0.0130`, `headroom="0.0070"`). |
| `V7` | vehicle | `fund` | `interlock` | `NONE` (order-level gate) | Brief §4.1 L238–L240, §4.2 L248–L250, §4.3 L284, §4.5 L332–L334, L341, §12 L604–L610; Report §4.4 L1305 | `state: "NORMAL"`, `would_have_tripped: true`, `latched: false`, `reason_class: "unresolved_fail_closed"` in all 11 base scenarios (spread width unresolved -> order not sent). |
| `O1` | data_and_operations | `account` | `interlock` | `NO-NEW-RISK` | Brief §4.2 L248–L250, §4.3 L290, §4.4 L307, L319–L323; Report §4.4 L1330, L1336, L1351 | `NORMAL` in 9 scenarios; `NO-NEW-RISK` in `stale` (`index_returns.age_sessions=2 > 1`) and `missing` (`volatility` absent/invalid -> stress substitution `0.70`, block increases). |
| `O2` | data_and_operations | `account` | `interlock` | `NONE` (session order gate) | Brief §4.1 L238–L240, §4.2 L248–L250, §4.3 L291, §5.4 L445; Report §4.4 L1337 | `NORMAL` (`would_have_tripped: false`) in 9 scenarios; `state: "NORMAL"`, `would_have_tripped: true`, `reason_class: "calendar_closed"` in `holiday` and `half_day`. |
| `O3` | data_and_operations | `account` | `breaker` | `HALT` | Brief §4.1 L227–L228, §4.2 L251–L254, §4.3 L292; Report §4.4 L1338 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`positions_beyond_tolerance=false`, `cash_beyond_tolerance=false`). |
| `O4` | data_and_operations | `symbol` | `interlock-with-breaker-branch` | `ORDER-UNKNOWN` | Brief §4.1 L229–L235, §4.2 L248–L254, §4.3 L293; Report §4.4 L1276, L1339 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`orders.pending: null`). |
| `O5` | data_and_operations | `account` | `breaker on third rejection (stateful count)` | `HALT` on 3rd rejection (`NONE` on single rejection) | Brief §4.1 L227–L228, L234, §4.2 L251–L254, §4.3 L294, §4.5 L332–L334, L341, §12 L604–L610; Report §4.4 L1340 | `state: "NORMAL"`, `would_have_tripped: true`, `latched: false`, `reason_class: "unresolved_fail_closed"` (`rejections_this_session: 0 -> 1 < 3`) in all 11 base scenarios. |
| `O6` | data_and_operations | `account` | `breaker` | `HALT` | Brief §4.1 L227–L228, §4.2 L251–L254, §4.3 L295; Report §4.4 L1341 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`loaded_hash == registered_hash`). |
| `O7` | data_and_operations | `account` | `breaker` | `NO-NEW-RISK` | Brief §4.1 L222–L223, §4.2 L251–L254, §4.3 L296; Report §4.4 L1342 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`silence_seconds=0 <= 300`). |
| `O8` | data_and_operations | `account` | `owner` | `HALT` | Brief §4.1 L227–L228, §4.2 L258, §4.3 L297, §5.1 L390–L394; Report §4.4 L1343 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (no kill-switch event in `authorized_events`). |
| `O9` | data_and_operations | `account` | `breaker` | `HALT` | Brief §4.1 L227–L228, §4.2 L251–L254, §4.3 L298, §5.1 L390–L394; Report §4.4 L1344 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios; in `tier_change`, `OC-SYNTH-TIER-001` authorizes `balanced -> conservative`. |
| `J1` | data_and_operations | `joint` | `limit` | `NONE` (`headroom_output`) | Brief §4.1 L234, L238–L244, §4.2 L255, §4.3 L299; Report §4.3 L1213, §4.4 L1345 | `NORMAL`, `would_have_tripped: false` in all 11 base scenarios (`joint_exposure=0.35 <= joint_cap=0.60`, `headroom="0.25"`, `trim_threshold_110pct="0.66"`). |

---

## 5. Base Matrix Scenario Outcomes (11 Scenarios × 24 Rows = 264 Cells)

| Scenario | Perturbation (`goldens/scenario_fixtures.json`) | Effective States (`account` / `fund:TQQQ` / `fund:SOXL` / `symbol:*` / `joint`) | Scenario-Specific Row Trips (`would_have_tripped: true` beyond baseline `V5`/`V7`/`O5`) |
| --- | --- | --- | --- |
| `normal` | Baseline inputs | All `NORMAL` | None (`V5`, `V7`, `O5` fail-closed at gate/diagnostic level only) |
| `deposit` | `flows.deposit_amount: "10000"` | All `NORMAL` | None (flow-adjusted bankroll basis prevents false loss trips on `L0`–`L4`; §4 L213–L216) |
| `withdrawal` | `flows.withdrawal_amount: "10000"` | All `NORMAL` | None (flow-adjusted bankroll basis prevents false loss trips on `L0`–`L4`; §4 L213–L216) |
| `split` | `TQQQ` split announced & detected, `ledger_adjusted: false` | `fund:TQQQ: HALT`; others `NORMAL` | `V2` (`fund:TQQQ` `HALT`, `latched: false`); split-adjusted loss basis prevents `L0`–`L4` false trips |
| `reverse_split` | `SOXL` reverse split announced & detected, `ledger_adjusted: false` | `fund:SOXL: HALT`; others `NORMAL` | `V2` (`fund:SOXL` `HALT`, `latched: false`); split-adjusted loss basis prevents `L0`–`L4` false trips |
| `stale` | `data_inputs.index_returns.age_sessions: 2` | `account: NO-NEW-RISK`; others `NORMAL` | `O1` (`age_sessions=2 > 1` -> `account` `NO-NEW-RISK`) |
| `missing` | `volatility` absent/invalid, `forecast_vol: null` | `account: NO-NEW-RISK`, `fund:TQQQ: NO-NEW-RISK`, `fund:SOXL: NO-NEW-RISK`; others `NORMAL` | `O1` (`account` `NO-NEW-RISK`, vol substitution `max(0.22, 0.70)=0.70`) and `V4` (`0.70 >= 2*long_run_vol` in both funds) |
| `restart` | Prior latched `L2` and `V4` (`TQQQ` `below_threshold_sessions: 4`) | `account: NO-NEW-RISK`, `fund:TQQQ: NO-NEW-RISK`; others `NORMAL` | `L2` (`latched: true`) and `V4` (`fund:TQQQ` counter `4 -> 5 < 10`) |
| `tier_change` | `tier: conservative` + owner card `OC-SYNTH-TIER-001` | All `NORMAL` | None (`O9` satisfied by `OC-SYNTH-TIER-001`; `L1`–`L4` thresholds recomputed at `D=0.15`) |
| `holiday` | `calendar.session_state: "holiday"`, `exchange_agrees: true` | All `NORMAL` | `O2` (`would_have_tripped: true`, `reason_class: "calendar_closed"`, session gate: no order, `state: "NORMAL"`) |
| `half_day` | `calendar.session_state: "half_day_past_cutoff"`, `exchange_agrees: true` | All `NORMAL` | `O2` (`would_have_tripped: true`, `reason_class: "calendar_closed"`, session gate: no order, `state: "NORMAL"`) |

---

## 6. Tier Repetitions Derivation (`tier_repetitions`: 14 Cases × 3 Tiers = 42 Cells)

- **Authority:** `BRIEF-FUSE-1.md` §0.4 (L113–L115), §6.1 (L466–L473), §7 D8 (L525); `REPORT.md` §4.3 (L1208–L1239) and §4.4 (L1287–L1291, L1345).
- **Bankroll & Tier Constants (`bankroll = "50000"`):**
  - `conservative`: `D = 0.15` (`$7,500`), `D/3 = 2500`, `2D/3 = 5000`, `D/10 = 750`, `max_loss_cap = 0.09` (§4.3 Line 10 `M_0`), `joint_cap = 0.20` (§4.3 Line 3), `110% trim = 0.22`.
  - `balanced`: `D = 0.30` (`$15,000`), `D/3 = 5000`, `2D/3 = 10000`, `D/10 = 1500`, `max_loss_cap = 0.20`, `joint_cap = 0.40`, `110% trim = 0.44`.
  - `aggressive`: `D = 0.50` (`$25,000`), `D/3 = 25000/3`, `2D/3 = 50000/3`, `D/10 = 2500`, `max_loss_cap = 0.39`, `joint_cap = 0.80`, `110% trim = 0.88`.

| Row | Case Formula | Expected Golden Behavior (`state`, `would_have_tripped`, `latched`, key outputs) |
| --- | --- | --- |
| `L0` | `proposed < max_loss_cap` (`0.06` / `0.15` / `0.30`) | `NORMAL`, `would_have_tripped: false`, `latched: false`, `cap_breached: false`, `effective_capped_exposure == proposed`. |
| `L0` | `proposed > max_loss_cap` (`0.12` / `0.25` / `0.45`) | `NORMAL`, `would_have_tripped: true`, `latched: false`, `cap_breached: true`, `effective_capped_exposure == max_loss_cap`. |
| `L1` | `drawdown = 0.2D` (`1500` / `3000` / `5000`) | `NORMAL`, `would_have_tripped: false`, `latched: false`, `locked_against_loosening: false`, `notify: false`. |
| `L1` | `drawdown = 0.5D` (`3750` / `7500` / `12500`) | `NORMAL` (`state_contribution: NONE`), `would_have_tripped: true`, `latched: false`, `locked_against_loosening: true`, `notify: true`. |
| `L2` | `drawdown = 0.5D` (`3750` / `7500` / `12500`) | `NORMAL`, `would_have_tripped: false`, `latched: false`. |
| `L2` | `drawdown = 2D/3` (`5000` / `10000` / `16666.66666666666666666666667`) | `NO-NEW-RISK`, `would_have_tripped: true`, `latched: true` (`'reaches'` inclusive boundary). |
| `L2` | `drawdown = 0.8D` (`6000` / `12000` / `20000`) | `NO-NEW-RISK`, `would_have_tripped: true`, `latched: true`. |
| `L3` | `drawdown = 0.8D` (`6000` / `12000` / `20000`) | `NORMAL`, `would_have_tripped: false`, `latched: false`, `cooling_off_days_remaining: 0`, `locked_flat: false`, `loss_record_cleared: false`. |
| `L3` | `drawdown = 1.05D` (`7875` / `15750` / `26250`) | `DE-RISK`, `would_have_tripped: true`, `latched: true`, `cooling_off_days_remaining: 30`, `locked_flat: true`, `loss_record_cleared: false`. |
| `L4` | `session_loss = 0.05D` (`375` / `750` / `1250`) | `NORMAL`, `would_have_tripped: false`, `latched: false`. |
| `L4` | `session_loss = 0.12D` (`900` / `1800` / `3000`) | `NO-NEW-RISK`, `would_have_tripped: true`, `latched: true`. |
| `J1` | `joint_exposure = 0.9 × joint_cap` (`0.18` / `0.36` / `0.72`) | `NORMAL`, `would_have_tripped: false`, `increases_blocked: false`, `trim_required_next_session: false`. |
| `J1` | `joint_exposure = 1.05 × joint_cap` (`0.21` / `0.42` / `0.84`) | `NORMAL` (`state_contribution: NONE`), `would_have_tripped: true`, `increases_blocked: true`, `trim_required_next_session: false`. |
| `J1` | `joint_exposure = 1.15 × joint_cap` (`0.23` / `0.46` / `0.92`) | `NORMAL` (`state_contribution: NONE`), `would_have_tripped: true`, `increases_blocked: true`, `trim_required_next_session: true`. |
