# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / test / refreeze / bundle head:** `d27f51a4f7d0c5f441503ddd28b9b239638c8e65` (preceded by `b3084d7`; followed by this docs commit)

## Status

**LOCAL REMEDIATION R1–R7 COMPLETE & VERIFIED ON `d27f51a` — REMOTE EXACT-HEAD CI / PR #3 GATES PENDING PUSH (`F1-A14` PENDING; NOT READY FOR MERGE)**

- Base: **264/264** ✓ strict raw dict equality + **264/264** §4.1 scope maps (R4 `O5.rejection_count_this_session` projection removed; R1 `missing.V1` fails closed)
- Tier (formal runner): **132/132 EXECUTED** ✓ (R5 real tier caps `0.40/0.60/0.80 × bankroll` = `40k/60k/80k` on 100k baseline, `tier_change` covers `balanced`+`aggressive`, frozen priors honoured, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (R6 `SUC-08` executes all `70` sequential sessions via live state with zero frozen-prior skips; `SUC-11` executes `2` real calls; `SUC-06/5` executes `12` calls; `SUC-07/3` executes `7` calls)
- Unit tests: **81 tests OK** (`pytest`: **81 passed, 9 subtests passed**) ✓
- ID-set gate (`tools/check_id_set.py`): **PASS** (`spec=24, engine=24, expected=24`) ✓
- Spec lint (`tools/lint_spec.py`): **PASS** ✓
- Exposure/policy invariant gate (`tools/check_exposure_invariants.py`): **168/168 bundles PASS** ✓ (R7 pre-call snapshots detect in-place caller/policy tampering such as `o5_collar=0.99`, plus continuous multi-step successor chains & `fc.v1_missing_index_return` / `fc.o1_nan_age` / `fc.o6_missing_policy_hash` / `fc.o3_missing_broker_cash` / `fc.v2_tolerance_bypass`)
- Deterministic: **YES** ✓ (2 independent strict runs + `PYTHONHASHSEED=1,2,3` produce byte-identical `acceptance/result-bundle.json`)
- Remote CI / PR #3 (`F1-A14`): **PENDING** (local branch unpushed; exact-head CI, `ai-review`, and R2 governance labels have not run on `d27f51a` / this head)

## Artifact Hashes (Head `d27f51a` + v2 Refreeze)

- **Engine hash (8 sorted files incl. `canonical.py`):** `96b0ebc4869225577e23358b530a5428b0d0d9b53d75c536f4abd84063185fa9`
- **Bundle hash:** `5244c3a365c5eaf7b19f04ab592fd506c2fd7d7b1e4119f908bde4e02561c746`
- **`acceptance/result-bundle.json` SHA-256 (trailing LF):** `a40a0c309aabda9f2d923774ea3fdf6284da962ee8b36dadcde3735a61e21515`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (`d27f51a`):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## R2 Codex Review Remediation Summary (`b3084d7` & `d27f51a`)

1. **R1 — V1 missing `index_return` fail-closed + v2 golden update (`d27f51a`):** Removed the `missing.V1` exemption in `src/fuse_engine/rows_vehicle.py` so missing `index_return` on an open window fails closed (`NO-NEW-RISK / would_have_tripped=True / reason='missing_input'`); updated `goldens/golden-table.json['base_cells']['missing.V1']` under owner-approved v2 refreeze; added regression test in `tests/test_slice3_controls.py`.
2. **R2 — V1 5-session history preserved across `market_closed`/holiday calls (`b3084d7`):** Updated `src/fuse_engine/rows_vehicle.py` and `src/fuse_engine/evaluator.py` so closed/holiday and missing-input non-observation calls retain existing `prior_row_state['V1'][fund]['session_returns']`. Verified via Jan 13–20 holiday test (`tests/test_slice3_controls.py`): 4 prior sessions survive Jan 19 holiday/closed evaluation and trip/latch V1 (`2.5251253 pp`) on Jan 20, remaining latched across subsequent zero-return sessions.
3. **R3 — V2 strict exact reconciliation without tolerance bypass (`b3084d7`):** Removed `reconciliation_tolerance` auto-clear tolerance in `src/fuse_engine/rows_vehicle.py::evaluate_V2`, enforcing `ledger_val == broker_val`. Added regression test in `tests/test_replay_proof.py` confirming `25,000` vs `24,900` with `reconciliation_tolerance=100` latches `HALT / reconciliation_mismatch`.
4. **R4 — Strict 264/264 base comparison without `O5` field stripping (`d27f51a`):** Removed the `O5.rejection_count_this_session` projection in `tools/run_matrix.py::compare_base_outcome_exact` and updated all 11 base `O5` cells in `goldens/golden-table.json` to emit `rejection_count_this_session: 1` (matching `SUC-03`/`SUC-04`). Verified `264/264` strict raw dict equality in `tests/test_full_comparator.py`.
5. **R5 — Formal tier runner using real `40k/60k/80k` caps & `balanced` `tier_change` (`d27f51a`):** Updated `tools/run_matrix.py::run_tier_repetitions` to apply `0.40/0.60/0.80 × bankroll` caps, updated `goldens/golden-table.json['tier_repetitions']` (including replacing duplicate `tier_change.*.conservative` cells with `tier_change.*.balanced`), and verified `132/132` formal pass plus `-1` J1-cap mutation detection (`110 pass / 22 fail`) in `tests/test_tier_oracles.py`.
6. **R6 — Continuous live stepping for all 70 `SUC-08` sessions (`b3084d7`):** Removed frozen `prior_row_state` injection (`is_jump_checkpoint`) on `SUC-08` steps 2 and 4 in `tools/run_matrix.py`, executing intermediate sessions `2..38` and `41..69` via continuous live state (`70` `evaluate()` calls verified in `tests/test_full_comparator.py`).
7. **R7 — Pre-call baseline snapshots & full successor chains in `check_exposure_invariants.py` (`b3084d7`, expanded `d27f51a`):** Added `_evaluate_checked` snapshotting `validated_inputs`, `prior_row_state`, and `authorized_events` before every `evaluate()` call across all batteries (including real continuous successor chains, `SUC-08` 70 sessions, `SUC-11`, and expanded fail-closed controls -> `168/168` bundles); verified in `tests/test_exposure_invariants.py` that wrapping `evaluate()` to mutate `o5_collar=0.99` or `max_loss_cap` fails immediately on every tampered call.
8. **R8 — Documentation alignment & remote gate transparency (this commit):** Recorded exact verified hashes/counts for `d27f51a`, removed premature `PASS` / `READY` claims for unpushed remote gate (`F1-A14`), and explicitly noted exact-head CI is pending push/CI run.

## Prior History (Phase 2F & Remediation #1/#2)

- **Slice 1 (`86be6d7`):** Applied 30 adjudication golden corrections to `goldens/successor-cases.json` (`efb8737a... -> 499641a2...`).
- **Slices 2–4 (`f60986a -> ad404ad`) & Remediation G1–G7 (`31500c9 -> fbed307`):** Migrated state schema to canonical Q6 nested objects, implemented O4/V1/V2/V4/V5/L3/L4 mechanics, wired account `HALT` dominance over `joint`, fixed 9 fail-closed probes and V1 5-session branch, executed `SUC-11` / `SUC-06/5` / `SUC-07/3`, bound metadata fields (`spec_version`, `engine_hash`, `enforcement_mode`, `loss_breakers_armed`), and resolved `PYTHONHASHSEED` determinism.

## Pending Before Merge

1. Push `demo/fuse1-sonnet` to origin (withheld per local-only protocol).
2. Trigger and verify passing remote exact-head GitHub CI, `ai-review`, and R2 clearing label (`agent-approved` or `owner-approved`) on PR #3 (`QuantStrategyLab/FuseControl#3`).
