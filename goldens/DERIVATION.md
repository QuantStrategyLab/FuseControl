# Golden Table Derivation Notes

## Authority

All golden outcomes derived from **BRIEF-FUSE-1 §4** specification text alone, applying trigger/action/kind/clearing semantics to scenario inputs cell by cell per §6.2 independence protocol.

## Per-Row Derivation

### Loss Rows (L0-L6)

**L0 — Maximum loss cap (Limit)**
- **Source:** Brief §4.3, L0 row; §4.1 limits  
- **Trigger:** Standing (every session)  
- **Derivation:** Computes `cap`, `cap_breached`, and `increases_blocked` from `max_loss_cap`, `joint_exposure`, and `proposed_exposure`. Not a trip; always present.  
- **Tier sensitivity:** Cap value varies with D (conservative 0.15, balanced 0.30, aggressive 0.50).

**L1 — Drawdown D/3 (Interlock, notify + lock)**
- **Source:** Brief §4.3, L1 row  
- **Trigger:** `drawdown = (HWM - bankroll) / HWM >= D/3`  
- **Derivation:** Drawdown below D/3 → no trip. At/above D/3 → trip, `locked_against_loosening = true`, `notify = true`. Clears when drawdown recedes below D/3.  
- **Tier arithmetic:** D/3 = 0.05 / 0.10 / 0.166667 for conservative / balanced / aggressive.

**L2 — Drawdown 2D/3 (Breaker, NO-NEW-RISK)**
- **Source:** Brief §4.3, L2 row; ruling L2 "reaches" is inclusive  
- **Trigger:** `drawdown >= 2D/3`  
- **Derivation:** Drawdown below 2D/3 → no trip. At/above 2D/3 → trips, latches, contributes NO-NEW-RISK. Only clears via authorized re-arm event per §4.2.  
- **Tier arithmetic:** 2D/3 = 0.10 / 0.20 / 0.333333 for conservative / balanced / aggressive.  
- **Persistence:** Per §4.4 rule 3, latch survives restart, deposit, withdrawal, split, tier change (see SUC-12).

**L3 — Drawdown D (Breaker, DE-RISK + locked flat)**
- **Source:** Brief §4.3, L3 row  
- **Trigger:** `drawdown >= D`  
- **Derivation:** Drawdown below D → no trip. At/above D → trips, latches, contributes DE-RISK, sets `cooling_off_days_remaining = 30`, `locked_flat = true`, `loss_record_cleared = false`. Requires owner card with 30-day cooling-off per §4.3.  
- **Tier arithmetic:** D = 0.15 / 0.30 / 0.50.

**L4 — One-session loss D/10 (Breaker, NO-NEW-RISK)**
- **Source:** Brief §4.3, L4 row  
- **Trigger:** `one_session_loss >= D/10`  
- **Derivation:** Loss below D/10 → no trip. At/above D/10 → trips, latches, contributes NO-NEW-RISK. Clears via owner acknowledgment, not before next session.  
- **Tier arithmetic:** D/10 = 0.015 / 0.03 / 0.05.

**L5 — Market halt Level 1 or 2 (Interlock, NO-NEW-RISK)**
- **Source:** Brief §4.3, L5 row; §4.4 rule (L5/L6 levels follow [W-MWCB])  
- **Trigger:** `market_halt_level in [1, 2]`  
- **Derivation:** No halt → no trip. Level 1 or 2 → trips, contributes NO-NEW-RISK during halt and for rest of session. Clears after one clean session.  
- **External basis:** S&P 500-based market-wide circuit breaker levels per [W-MWCB], §4.4 records.

**L6 — Market halt Level 3 OR 10% index fall (Breaker, HALT)**
- **Source:** Brief §4.3, L6 row; §4.5 disposition (10% confirmed as spec)  
- **Trigger:** `market_halt_level == 3` OR `any(index_one_session_returns.values() <= -0.10)`  
- **Derivation:** Neither condition → no trip. Level 3 or 10% fall in either underlying index → trips, latches, contributes HALT. Clears via owner re-arm after reconciliation.  
- **Threshold:** 10% in index ≈ 30% in 3× fund; §4.5 disposition CONFIRMED-AS-SPEC.

### Vehicle Rows (V1-V7)

**V1 — Tracking deviation (Breaker, NO-NEW-RISK)**
- **Source:** Brief §4.3, V1 row; §4.5 disposition (0.75pp / 2.0pp confirmed)  
- **Trigger:** One-session deviation > 0.75 pp OR five-session deviation > 2.0 pp, after modelled fee/financing  
- **Derivation:** Within tolerance → no trip. Beyond tolerance → trips, latches, contributes NO-NEW-RISK in that fund. Requires data check first.  
- **Thresholds:** §4.5 CONFIRMED-AS-SPEC: 0.75 pp (1 session), 2.0 pp (5 sessions).

**V2 — Corporate action (HALT until adjusted, interlock_or_breaker)**
- **Source:** Brief §4.3, V2 row; §5.4 C-SA-CA amended semantics; ruling V2 pending/mismatch  
- **Trigger:** Split, reverse split, or distribution announced or detected  
- **Derivation:**  
  - No corporate action → no trip.  
  - Announced/detected → trips, contributes unlatched fund HALT with pending state (see SUC-01).  
  - Exact reconciliation (adjustment complete, ledger matches broker exactly) → auto-clears.  
  - Mismatch → latches as breaker, requires human re-arm (see SUC-02).  
- **Clearing:** Per ruling V2, pending HALT is unlatched; auto-clears only on exact reconciliation per amended C-SA-CA.

**V3 — Fund event (Breaker, DE-RISK)**
- **Source:** Brief §4.3, V3 row  
- **Trigger:** Liquidation, change in multiple/objective, suspended creations, exchange halt, delisting  
- **Derivation:** No event → no trip. Event → trips, latches, contributes DE-RISK in that fund. Owner decides what follows.

**V4 — Volatility 2× (Interlock, NO-NEW-RISK)**
- **Source:** Brief §4.3, V4 row; §4.5 disposition (2× confirmed); ruling V4 restart + same-session  
- **Trigger:** `forecast_volatility >= 2 * long_run_volatility`  
- **Derivation:**  
  - Below 2× → no trip.  
  - At/above 2× → trips, contributes NO-NEW-RISK in that fund, `clearing_counter = 0`.  
  - Clears after **ten sessions** below the level. Counter increments **once per session** (not per evaluation), persists across restarts per §4.4 rule 3 (see SUC-06, SUC-07).  
- **Threshold:** §4.5 CONFIRMED-AS-SPEC: 2× long-run (≈48% for Nasdaq-100).

**V5 — Decay monitor (Diagnostic, escalates to V1 after 40 sessions)**
- **Source:** Brief §4.3, V5 row; ruling V5 fail-closed + persistence; SUC-08 derivation convention  
- **Trigger:** Shortfall vs 3× index exceeds variance/fee/financing predictions by more than stated tolerance, over 60 sessions  
- **Derivation:**  
  - **Unresolved tolerance** (§4.5 UNRESOLVED-FAIL-CLOSED): trips with `unresolved_fail_closed` reason, diagnostic output, `escalated_to_v1 = false`. Not an unconditional NORMAL per ruling V5.  
  - **Tolerance supplied:** Excess within tolerance → no trip. Excess beyond tolerance → diagnostic trip, `consecutive_sessions_beyond_tolerance` counter advances. At **40 consecutive sessions** → escalates to V1 treatment (contributes NO-NEW-RISK in that fund), `escalated_to_v1 = true`.  
- **Derivation convention (SUC-08):** "Two months" = 40 sessions. Counter counts consecutive sessions beyond tolerance. Escalation is a real state contribution per ruling V5.

**V6 — Carrying cost (Diagnostic)**
- **Source:** Brief §4.3, V6 row  
- **Trigger:** `carrying_cost_measured > (excess_return_shrunk / 4)`  
- **Derivation:** Below threshold → no trip. Above threshold → diagnostic trip, notify, policy review. Diagnostic outputs: `cost_per_unit_exposure`, `threshold`, `exceeded`, `notify`. No state contribution.

**V7 — Quote/liquidity (Interlock, order not sent)**
- **Source:** Brief §4.3, V7 row; §4.5 disposition (spread width unresolved); ruling V7 fail-closed  
- **Trigger:** Stale quote, spread above stated width, single-stock trading pause, time outside regular session  
- **Derivation:**  
  - **Unresolved spread width** (§4.5 UNRESOLVED-FAIL-CLOSED): trips with `unresolved_fail_closed` reason, order not sent. Not an unconditional NORMAL per ruling V7.  
  - **Width supplied:** Conditions absent → no trip. Stale/wide/pause/outside regular → trips, order not sent, clears when condition resolves.

### Data and Operations Rows (O1-O9, J1)

**O1 — Required input stale/missing/invalid (Interlock, NO-NEW-RISK)**
- **Source:** Brief §4.3, O1 row; ruling B3 missing source enumeration  
- **Required sources:** market_data, index_returns, volatility, positions, broker_reconciliation, session_calendar (6 classes, SUC-05).  
- **Trigger:** Any required input older than one session, missing, or fails validation  
- **Derivation:** All fresh and valid → no trip. Any stale/missing/invalid → trips, contributes NO-NEW-RISK. Clears after one session of fresh data. Zero silent passes (see SUC-05).

**O2 — Calendar closed/holiday/half-day (Interlock, no order)**
- **Source:** Brief §4.3, O2 row  
- **Trigger:** Session calendar says closed, holiday, or past half-day cutoff; OR calendar and exchange status disagree  
- **Derivation:** Open and agree → no trip. Closed/holiday/half-day or disagree → trips, no order. Clears when session open and calendar/exchange agree.

**O3 — Position mismatch (Breaker, HALT)**
- **Source:** Brief §4.3, O3 row  
- **Trigger:** Positions or cash differ from broker's record beyond tolerance  
- **Derivation:** Reconciles within tolerance → no trip. Mismatch → trips, latches, contributes HALT. Clears via owner re-arm after reconciliation.

**O4 — Order timeout (interlock_or_breaker, ORDER-UNKNOWN)**
- **Source:** Brief §4.3, O4 row; ruling B6 original-order identity  
- **Trigger:** Order has no terminal status within timeout  
- **Derivation:**  
  - No pending orders → no trip.  
  - Timeout → trips, contributes ORDER-UNKNOWN (symbol-scoped). Tracks **original order ID** (see SUC-09).  
  - Clears on definitive status from broker for the **original order**; terminal status for a different order or unrecognized status does NOT clear (ruling B6).  
  - Otherwise breaker (latches if no resolution).  
- **Persistence:** Survives restart per §4.4 rule 3 (see SUC-10).

**O5 — Pre-trade limits (Breaker on third rejection, HALT)**
- **Source:** Brief §4.3, O5 row; §4.5 disposition (collar unresolved); ruling O5 session boundary + count  
- **Trigger:** Whitelist, long-only, settled-cash, size, session limits, price collar violations  
- **Derivation:**  
  - **Unresolved collar** (§4.5 UNRESOLVED-FAIL-CLOSED): trips with `unresolved_fail_closed` reason, order rejected, **counts as one rejection** per ruling O5. Not an unconditional NORMAL.  
  - **Collar supplied:** No violations → no trip. Violation → order rejected, rejection count increments.  
  - **Third rejection within one session** → latches account HALT per ruling O5. Count resets at session boundary (see SUC-03, SUC-04).

**O6 — Policy hash mismatch (Breaker, HALT)**
- **Source:** Brief §4.3, O6 row  
- **Trigger:** `loaded_policy_hash != registered_policy_hash`  
- **Derivation:** Hashes match → no trip. Mismatch → trips, latches, contributes HALT. Clears via owner re-arm.

**O7 — Dead man's switch (Breaker, NO-NEW-RISK)**
- **Source:** Brief §4.3, O7 row; amended C-WA-HEALTH  
- **Trigger:** Runtime or monitor silent for longer than one scheduled interval  
- **Derivation:** Heartbeat within interval → no trip. Silent beyond interval → trips, latches, contributes NO-NEW-RISK (no increases, alarm on independent channel). Latches until human re-arm.

**O8 — Kill switch (Owner, HALT)**
- **Source:** Brief §4.3, O8 row; §5.1 authorized_events sole channel  
- **Trigger:** Owner command in `authorized_events`  
- **Derivation:** No owner command → no trip. Owner command present → trips, contributes HALT. Flattening is separate explicit second command.

**O9 — Unauthorized parameter change (Breaker, HALT)**
- **Source:** Brief §4.3, O9 row  
- **Trigger:** Tier, H, high-water mark, or limit changed without recorded owner card  
- **Derivation:** No change or card present → no trip. Unauthorized change → trips, latches, contributes HALT (see tier_change scenario, SUC-12 tier_change persistence). Clears via owner re-arm.

**J1 — Joint cap (Limit)**
- **Source:** Brief §4.3, J1 row; §4.1 limits  
- **Trigger:** Joint exposure above tier's joint cap  
- **Derivation:** Computes `headroom = max(0, joint_cap - joint_exposure)`, `above_cap`, `above_trim_threshold` (110% of cap). Increases blocked when above cap; trimmed at next session if above 110%. Automatic, symmetric. Not a trip; always present.  
- **Tier sensitivity:** Joint cap varies with tier (conservative 40000, balanced 60000, aggressive 80000 on baseline bankroll 100000).

## Tier Arithmetic

| Tier | D | L1 (D/3) | L2 (2D/3) | L3 (D) | L4 (D/10) |
|------|---|----------|-----------|--------|-----------|
| Conservative | 0.15 | 0.05 | 0.10 | 0.15 | 0.015 |
| Balanced | 0.30 | 0.10 | 0.20 | 0.30 | 0.03 |
| Aggressive | 0.50 | 0.166667 | 0.333333 | 0.50 | 0.05 |

Loss rows L0-L4 and joint cap J1 are tier-parameterized; all scenarios executed at all three tiers with tier-specific expected outcomes (§6.1).

## Scenario-Specific Derivations

**normal:** All inputs fresh, no events, bankroll = HWM (no drawdown), no trips except V5/V7/O5 (unresolved parameters, fail-closed per rulings).

**deposit / withdrawal:** Flow-adjusted HWM per §4.4 7A and decision 7A/C-SA-16; loss thresholds computed on flow-adjusted basis. Latches persist per §4.4 rule 3.

**split / reverse_split:** V2 trips with pending corporate action (split TQQQ, reverse_split SOXL); fund-scoped HALT, unlatched, awaiting reconciliation.

**stale:** Volatility source `age_sessions = 2` → O1 trips, NO-NEW-RISK.

**missing:** index_returns absent → O1 trips, NO-NEW-RISK.

**restart:** Serialization round-trip marker; prior_row_state carried, latches and counters persist per §4.4 rule 3.

**tier_change:** Tier changed without authorized card → O9 trips, latches account HALT.

**holiday / half_day:** Calendar status not open → O2 trips, no order.

## Successor-State Case Derivations

Each SUC case derived from B-mechanism + brief text:

- **SUC-01 (B1):** V2 pending → unlatched HALT, carried until exact reconciliation per ruling V2.
- **SUC-02 (B1):** V2 mismatch → latched HALT, persists until authorized re-arm.
- **SUC-03 (B2):** O5 rejections reset at session boundary per ruling O5; never reaches 3 within one session.
- **SUC-04 (B2):** O5 three rejections within one session → latches HALT on third per ruling O5.
- **SUC-05 (B3):** O1 enumeration of 6 required source classes; each absence → NO-NEW-RISK; all present → NORMAL.
- **SUC-06 (B4):** V4 counter increments once per session, not per evaluation; two evaluations in session 3 → counter stays at 2.
- **SUC-07 (B4):** V4 counter persists across restart per §4.4 rule 3.
- **SUC-08 (B5):** V5 consecutive-session counter; 40 sessions (2 months per convention) → escalates to V1 treatment per ruling V5.
- **SUC-09 (B6):** O4 tracks original order ID; terminal status for different order or unrecognized status does not clear.
- **SUC-10 (B6):** O4 ORDER-UNKNOWN persists across restart per §4.4 rule 3.
- **SUC-11 (B7):** Reserved for Phase 3 stub-swap deep-shape fixture (nested V4/V5/V6 field checks).
- **SUC-12:** L2 latch persists through deposit and tier_change per §4.4 rule 3; clears only via authorized re-arm.
- **SUC-13:** V1 breaker latches; receding trigger does not clear; requires authorized re-arm.

## Effective State by Scope

Precedence per §4.1: **HALT > ORDER-UNKNOWN (symbol) > DE-RISK > NO-NEW-RISK > NORMAL**.

Account-scoped trips (L0-L6, O1-O3, O6-O9) dominate all scopes per ruling (account HALT dominance). Fund-scoped trips (V1-V4) affect only that fund. Symbol-scoped trips (O4, O5 third rejection → account HALT) affect that symbol or widen to account on latching. No silent upward propagation.

## Unresolved Parameters (§4.5, Rulings V5/V7/O5)

V5 `v5_tolerance`, V7 `v7_spread_width`, O5 `o5_collar` are **UNRESOLVED-FAIL-CLOSED**. When absent from `validated_inputs`:
- **Not an unconditional NORMAL.** Each trips with `unresolved_fail_closed` reason.
- V5: Diagnostic trip, `escalated_to_v1 = false` (unless persistence counter reaches 40 → escalation is real).
- V7: Interlock trip, order not sent.
- O5: Rejection trip, counts toward third-rejection HALT.

This encoding satisfies rulings V5/V7/O5 "fail-closed but have real semantics."

## Derivation Integrity

Golden table authored in checkpoint W2, **before** engine runs the full matrix for the first time (§6.2 temporal separation). Derivation from §4 text alone, citing spec lines per outcome above. Engine outputs not read during derivation (§6.2 rule 3). Any matrix mismatch adjudicated against specification text; a golden may be corrected only with written spec citation showing the golden misread the spec (§6.2 rule 4).

---
**End of Derivation Notes**
