# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, unchanged relative to `710758c`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / fixture / tool / test head:** `ef79aee30e6e3a5ec904cad236f9bbfa30beb30f` (`ef79aee`, preceded by `b1e2ec6`, `9335f26`, `710758c`, `d27f51a`, `b3084d7`; followed by this bundle/docs commit)

## Status

**LOCAL REMEDIATION (R1–R8 + CODEX R3/R4 FINDINGS) VERIFIED ON `ef79aee` — REMOTE EXACT-HEAD CI / PR #3 GATES PENDING PUSH (`F1-A14` PENDING; NOT READY FOR MERGE)**

- Base: **264/264** ✓ strict raw dict equality + type equality (`True != 1`) AND **264/264** full independent §4.1 scope maps inside formal `run_matrix.run_base_cells`
- Tier (formal runner): **132/132 EXECUTED** ✓ full-key strict dict + type equality (`compare_base_outcome_exact` catches extra keys & `bool`/`int` mismatches; R5 real tier caps `0.40/0.60/0.80 × bankroll`, `tier_change` covers `balanced`+`aggressive`, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (`compare_next_row_state` enforces strict type equality `True != 1`; `SUC-08` executes all `70` sequential sessions via live state; `SUC-11` executes `2` real calls; `SUC-06/5` executes `12` calls; `SUC-07/3` executes `7` calls)
- Unit tests: **119 tests OK** (`unittest`: `Ran 119 tests` OK; `pytest`: **119 passed, 18 subtests passed**) ✓
- ID-set gate (`tools/check_id_set.py`): **PASS** (`spec=24, engine=24, expected=24`) ✓
- Spec lint (`tools/lint_spec.py`): **PASS** ✓
- Exposure/policy invariant gate (`tools/check_exposure_invariants.py`): **168/168 bundles PASS** ✓ (checks non-null `J1.outputs.cap`, exact `J1.outputs.headroom`, permits genuine reductions like `45k -> 40k` under `NO-NEW-RISK`, and permits buying unrestricted funds such as `SOXL` when only `TQQQ` is restricted)
- Golden generator (`tools/generate_golden_table.py`): **SYNCED (MEM + CLI LF)** ✓ (`generate_golden_table` CLI serialization with trailing `\n` matches frozen `goldens/golden-table.json` at `140,031` bytes & exact SHA-256)
- Deterministic: **YES** ✓ (2 independent strict runs + `PYTHONHASHSEED=1,2,3` produce byte-identical `acceptance/result-bundle.json`, AND `canonical_json` round-trip of `missing` & swapped multi-fund V5/V6 inputs produce identical bundles)
- Remote CI / PR #3 (`F1-A14`): **PENDING** (local branch unpushed; exact-head CI, `ai-review`, and R2 governance labels have not run on `ef79aee` / this head)

## Artifact Hashes (Head `ef79aee` + Unchanged v2 Refreeze)

- **Engine hash (8 sorted files incl. `canonical.py`):** `116014fc6ede62c76a07f79e3e690da0f09833d030b2ef3623e0aaf282d3bd99`
- **Bundle hash:** `660b1a97fa1df663dc8f6ef2b387ede5790bc8a63a7216c1c4fcadd8a1af2e01`
- **`acceptance/result-bundle.json` SHA-256 (973 bytes, trailing LF):** `b1cf7d6de39a010d457a46b3c6d58841391868540ab6cacbf1cd8bebc2532831`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (at `d27f51a` / `710758c`, 0 bytes modified in R3/R4 remediation):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## Codex R4 Audit Remediation Summary (`ef79aee` & this docs/bundle commit)

1. **Group 1 — V2 multi-action queue, exact bool flags & known ratio match (`src/fuse_engine/rows_vehicle.py`, `src/fuse_engine/evaluator.py`):** Second corporate action announcement (`distribution`) no longer overwrites unresolved `split`; reconciles queued actions individually while keeping `split` `HALT` until all pending actions reconcile. Completion flags (`adjustment_complete`, `exact_reconciliation`) require exact `bool` (`'false'` string latches `HALT`); known pending ratios cannot be omitted during same-type reconciliation.
2. **Group 2 — O9 single-card authorization & Q4 session/scope re-arm validation (`src/fuse_engine/canonical_state.py`, `src/fuse_engine/rows_ops.py`):** One single `parameter_change_card` must approve all changed fields in `o9_change_descriptors` (preventing multi-card stitching). Account re-arms (`O5`/`O7`/`O9`/`L2`/`L4`/`L6`/`O3`/`O6`) validate session/`as_of` date and strict `account` scope before clearing (rejecting stale prior-day, undated, or `fund:TQQQ`-scoped cards).
3. **Group 3 — Loss breakers (`src/fuse_engine/rows_loss.py`, `src/fuse_engine/evaluator.py`):** `L3` computes cooling-off elapsed days strictly from persisted `trip_session` & current date (and `L4` from persisted `trip_session` vs current session, never trusting caller `days_since_trip`/`sessions_since_trip`); `L4` fails closed on `NaN`/non-finite `one_session_loss`; `L6` scans every index in `index_one_session_returns` past invalid entries and refuses re-arm when `O3` fails reconciliation; missing `bankroll` in `L3` `loss_record` construction fails closed without `TypeError`.
4. **Group 4 — V1 `five_session_history=[]` & V4 holiday/omitted scopes (`src/fuse_engine/rows_vehicle.py`, `src/fuse_engine/evaluator.py`):** Caller `five_session_history=[]` preserves existing `prior_row_state['V1'][fund]['session_returns']`. `V4` does not increment `clearing_counter` on `holiday`/`closed` sessions, and active `V4` fund restrictions omitted from current `funds` remain in `effective_state_by_scope` and `rows_by_ID['V4']`. Note: `V1` `sessions_window=None` continues to accumulate 5-session rolling history while returning `NORMAL` on day 1 when within 0.75pp to remain strictly consistent with frozen v2 `goldens/golden-table.json` (`10` of `11` scenarios omit `sessions_window`).
5. **Group 5 — Multi-fund order-independent aggregation, V6/V7 missing inputs (`src/fuse_engine/evaluator.py`, `src/fuse_engine/rows_vehicle.py`):** Ordered fund traversal with `_fund_sort_key` (`[TQQQ, SOXL]` canonical order preserving `missing.V1` after `canonical_json` round-trip) and worst-case severity selection in `aggregate_diagnostic_row` ensure swapped fund key order yields identical `V5`/`V6` `notify`/`disposition`/`reason`. `V6` enforces canonical spec fields over synthetic thresholds and fails closed on missing inputs; `V7` requires finite `quote_staleness` and `spread_width`.
6. **Group 6 — O3 share+value integrity, O4 status whitelist, O7 missing heartbeat (`src/fuse_engine/rows_ops.py`):** `O3` requires explicit `reconciliation_tolerance` (no implicit `1.0` default) and checks both `share_count == broker_position` and `ledger_value == broker_value` per fund; `O4` ignores `terminal=True` when `status` is not a recognized terminal state; `O7` fails closed when `last_heartbeat` and `scheduled_interval` are missing.
7. **Group 7 — O5 qty×price cash derivation, canonical `settled_cash`, whitelists (`src/fuse_engine/rows_ops.py`):** Derives order notional from `qty * unit_price` when `o5_order_value` is absent, prevents `o5_settled_cash` from overriding zero canonical `settled_cash`, and reads `account_whitelist` + `symbol_whitelist` (so `BIL` passes and rogue accounts reject).
8. **Group 8 — Intra-session L5/O1 persistence & O2 token whitelist (`src/fuse_engine/rows_loss.py`, `src/fuse_engine/rows_ops.py`, `src/fuse_engine/evaluator.py`):** `L5` stays `NO-NEW-RISK` for the remainder of the trip session after halt drops and clears only on a subsequent clean session; `O1` does not increment `fresh_session_count` or clear operational trips on same-session `stale -> fresh` recovery; `O2` rejects invalid status tokens like `"n/a"`.
9. **Group 9 — J1 NaN cap, checker, runner, `engine_hash`, stub `BIL`, generator LF & docs (`rows_ops.py`, `check_exposure_invariants.py`, `run_matrix.py`, `evaluator.py`, `fixtures/stub_adapter.py`, `tools/generate_golden_table.py`, docs):** `J1` fails closed on `tier_joint_cap=NaN`; `check_exposure_invariants.py` catches missing `J1.outputs.cap` while allowing genuine reductions (`45k -> 40k`) and buying unrestricted `SOXL`; `run_matrix.py` uses `strict_value_equal` in successor `next_row_state` and full-key `compare_base_outcome_exact` in `run_tier_repetitions`; `evaluator.py` computes and binds canonical `engine_hash` directly from `src/fuse_engine/*.py`; `stub_adapter.py` enumerates `pending_orders` symbols (e.g. `BIL`); `tools/generate_golden_table.py` writes trailing LF matching frozen `140,031` bytes. Note on frozen `goldens/`: `goldens/` remains 0 bytes changed vs `710758c` (including signed `-5000.0` J1 headroom at `golden-table.json:3894` vs `DERIVATION.md:165` prose note).

## Prior History (Phase 2F, Remediation #1/#2 & Codex R2/R3)

- **Slice 1 (`86be6d7`):** Applied 30 adjudication golden corrections to `goldens/successor-cases.json` (`efb8737a... -> 499641a2...`).
- **Slices 2–4 (`f60986a -> ad404ad`) & Remediation G1–G7 (`31500c9 -> fbed307`):** Migrated state schema to canonical Q6 nested objects, implemented O4/V1/V2/V4/V5/L3/L4 mechanics, wired account `HALT` dominance over `joint`, fixed 9 fail-closed probes and V1 5-session branch, executed `SUC-11` / `SUC-06/5` / `SUC-07/3`, bound metadata fields, and resolved `PYTHONHASHSEED` determinism.
- **R2/R3 Audit & v2 Refreeze (`b3084d7 -> b1e2ec6`):** Applied owner-approved v2 refreeze (`d27f51a` for R1/R4/R5), V1 holiday history (`R2`), V2 exact reconciliation (`R3`), `SUC-08` continuous stepping (`R6`), pre-call invariant snapshots (`R7`), A03/A06–A12 fixes (`9335f26`), and acceptance alignment (`b1e2ec6`).

## Pending Before Merge

1. Push `demo/fuse1-sonnet` to origin (withheld per local-only protocol).
2. Trigger and verify passing remote exact-head GitHub CI, `ai-review`, and R2 clearing label (`agent-approved` or `owner-approved`) on PR #3 (`QuantStrategyLab/FuseControl#3`).
