# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, unchanged relative to `710758c`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / test / generator / disposition head:** `9335f26e4a824bc7ab8b3ff88878c37b2fa6d8b6` (`9335f26`, preceded by `710758c`, `d27f51a`, `b3084d7`; followed by this bundle/docs commit)

## Status

**LOCAL REMEDIATION (R1–R8 + CODEX R3 FINDINGS) COMPLETE & VERIFIED ON `9335f26` — REMOTE EXACT-HEAD CI / PR #3 GATES PENDING PUSH (`F1-A14` PENDING; NOT READY FOR MERGE)**

- Base: **264/264** ✓ strict raw dict equality + type equality (`True != 1`) AND **264/264** full independent §4.1 scope maps inside formal `run_matrix.run_base_cells` (checked across all 264 cells even when `effective_state_by_scope` is absent from `golden-table.json`)
- Tier (formal runner): **132/132 EXECUTED** ✓ (R5 real tier caps `0.40/0.60/0.80 × bankroll` = `40k/60k/80k` on 100k baseline, `tier_change` covers `balanced`+`aggressive`, frozen priors honoured, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (R6 `SUC-08` executes all `70` sequential sessions via live state with zero frozen-prior skips; `SUC-11` executes `2` real calls; `SUC-06/5` executes `12` calls; `SUC-07/3` executes `7` calls)
- Unit tests: **99 tests OK** (`unittest`: `Ran 99 tests` OK; `pytest`: **99 passed, 18 subtests passed**) ✓
- ID-set gate (`tools/check_id_set.py`): **PASS** (`spec=24, engine=24, expected=24`) ✓
- Spec lint (`tools/lint_spec.py`): **PASS** ✓
- Exposure/policy invariant gate (`tools/check_exposure_invariants.py`): **168/168 bundles PASS** ✓ (R7 pre-call snapshots detect `o5_collar=0.99` tampering; A09 exact `J1.outputs.headroom` check catches `+1,000,000` inflation; sole-fund `NO-NEW-RISK` blocks exposure increases)
- Golden generator (`tools/generate_golden_table.py`): **SYNCED** ✓ (`generate_golden_table(scenarios.json) == golden-table.json` v2 with 0 diffs across all 264 base cells + 132 tier repetitions)
- Deterministic: **YES** ✓ (2 independent strict runs + `PYTHONHASHSEED=1,2,3` produce byte-identical `acceptance/result-bundle.json`)
- Remote CI / PR #3 (`F1-A14`): **PENDING** (local branch unpushed; exact-head CI, `ai-review`, and R2 governance labels have not run on `9335f26` / this head)

## Artifact Hashes (Head `9335f26` + Unchanged v2 Refreeze)

- **Engine hash (8 sorted files incl. `canonical.py`):** `57340edbddbca5ec9cabd7d0466953d95c69de7061b732c637b8527bb5d28d74`
- **Bundle hash:** `d0059d0f7fc92cf9a13c032a0680de3b17b9226578cdcafa3602e14cc41392ce`
- **`acceptance/result-bundle.json` SHA-256 (973 bytes, trailing LF):** `4b1e48e4e0bb2ff080533f5870aecbf653f04076b85d747d8ceba85f69b5d898`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (at `d27f51a` / `710758c`, 0 bytes modified in R3 remediation):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## Codex R3 Audit Remediation Summary (`9335f26` & this docs/bundle commit)

1. **R3 & A12 — Complete V2 exact reconciliation & `{}` pending continuity (`src/fuse_engine/rows_vehicle.py`, `src/fuse_engine/evaluator.py`):** Exact auto-clear now requires finite matching `ledger_value == broker_value`, matching `share_count == broker_position`, `hwm_adjusted is not False`, and matching corporate action `type`/ratio against `prior_pending` (so missing shares, unadjusted HWM, or `distribution` vs `split` latch `HALT`); subsequent `corporate_action={}` preserves active `pending_adjustments` instead of overwriting/dropping pending state.
2. **R4 & A03 — Strict type equality & unconditional §4.1 scope validation in formal runner (`tools/run_matrix.py`):** Added `strict_value_equal` rejecting `bool` vs `int` mismatches (`True != 1`, `False != 0`); integrated independent §4.1 `derive_expected_effective_map` into `run_base_cells` so all 264 base cells verify exact `effective_state_by_scope` (catching `tier_change.joint -> NORMAL` mutations even inside the formal matrix runner).
3. **A06 & A11 — Fail-closed non-finite/negative validation, V1 rolling history, and V6 exact formula (`src/fuse_engine/canonical.py`, `rows_ops.py`, `rows_vehicle.py`, `evaluator.py`):** Added `finite_float` non-bool helper; O3 fails closed on `NaN`/`inf`/bool/negative balances & fund values; V1 accumulates rolling 5-session `session_returns` across open observations even when `sessions_window` is omitted (so 5 consecutive `+0.5%` days trip & latch on Day 5); V6 uses `carrying_cost_measured > (excess_return_shrunk / 4)` and fails closed on non-finite inputs; V5/V7/O5 reject `NaN`/`inf`/bool/negative thresholds and inspect top-level policy keys cleanly.
4. **A07 & O5 zero-cash bypass — O5 session counter & settled-cash enforcement (`rows_ops.py`, `evaluator.py`):** Preserved `O5` session `rejection_count` across mixed `Reject -> Reject -> Pass -> Reject` sequences (`1, 2, 2, 3 -> HALT`); replaced truthiness check so `settled_cash=0` rejects positive buy orders cleanly.
5. **A08 — O7 dead-man's switch timestamp gap & account precedence (`rows_ops.py`, `evaluator.py`):** Evaluated `(as_of - last_heartbeat) > scheduled_interval` (e.g., 7h gap > 3600s -> `NO-NEW-RISK`), preserved account-level `'NO-NEW-RISK'` on both fresh and latched prior trips (surviving concurrent fund `V1` trips), and wired Q4 `rearm` clearing.
6. **A09 — `check_exposure_invariants.py` J1 headroom & fund-scope blocking (`tools/check_exposure_invariants.py`):** Verified exact `J1.outputs.headroom` arithmetic (catching `+1,000,000` inflation) and restricted exposure increases when all `fund:*` or `symbol:*` scopes are restricted (`sole-fund NO-NEW-RISK` caps permitted exposure at `45,000`).
7. **A10 — FUSE-1 shadow-only mode contract (`evaluator.py`):** Enforced `mode == 'shadow'` (raising `ValueError` for any non-shadow mode such as `'live'`) and fixed emitted `enforcement_mode='shadow_would_have_tripped'`, `loss_breakers_armed=False`.
8. **O9 dual-signal authorization & generator/disposition sync (`rows_ops.py`, `tools/generate_golden_table.py`, `acceptance/disposition-register.json`):** Validated `tier_change_event` and `o9_change_descriptors` independently so `tier_change_card` cannot authorize unauthorized parameter descriptors; synced `generate_golden_table.py` to v2 `golden-table.json` (`0` diffs); updated V1 5-session note in `disposition-register.json`; updated docs cleanly (`F1-A14` PENDING push).

## Prior History (Phase 2F & Remediation #1/#2 + R1–R8)

- **Slice 1 (`86be6d7`):** Applied 30 adjudication golden corrections to `goldens/successor-cases.json` (`efb8737a... -> 499641a2...`).
- **Slices 2–4 (`f60986a -> ad404ad`) & Remediation G1–G7 (`31500c9 -> fbed307`):** Migrated state schema to canonical Q6 nested objects, implemented O4/V1/V2/V4/V5/L3/L4 mechanics, wired account `HALT` dominance over `joint`, fixed 9 fail-closed probes and V1 5-session branch, executed `SUC-11` / `SUC-06/5` / `SUC-07/3`, bound metadata fields, and resolved `PYTHONHASHSEED` determinism.
- **R2 Audit & v2 Refreeze (`b3084d7 -> 710758c`):** Preserved V1 5-session history across holiday/closed days (`R2`), removed V2 `reconciliation_tolerance` auto-clear (`R3`), removed `SUC-08` jump injections (`R6`), added pre-call invariant snapshots (`R7`), and applied owner-approved v2 refreeze for `R1`/`R4`/`R5` (`d27f51a`).

## Pending Before Merge

1. Push `demo/fuse1-sonnet` to origin (withheld per local-only protocol).
2. Trigger and verify passing remote exact-head GitHub CI, `ai-review`, and R2 clearing label (`agent-approved` or `owner-approved`) on PR #3 (`QuantStrategyLab/FuseControl#3`).
