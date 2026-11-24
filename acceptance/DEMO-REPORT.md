# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, unchanged relative to `710758c`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / fixture / tool / test head:** `440373c125b0f620323b60619b7bff9f11db2f8d` (`440373c`, preceded by `3a14e18`, `f9b6b3a`, `841b7cb`, `e3a7aba`, `18f8cdd`, `3277881`, `ef79aee`, `b1e2ec6`, `9335f26`, `710758c`, `d27f51a`, `b3084d7`; followed by this bundle/docs commit)

## Status

**LOCAL R7 P1 REMEDIATION VERIFIED ON `440373c` (v2 `goldens/` FREEZE PRESERVED AT 0 DIFF BYTES; REMOTE CI / PR #3 `F1-A14` PENDING PUSH)**

- Base: **264/264** ✓ strict raw dict equality + type equality (`True != 1`) AND **264/264** full independent §4.1 scope maps inside formal `run_matrix.run_base_cells`
- Tier (formal runner): **132/132 EXECUTED** ✓ full-key strict dict + type equality (`compare_base_outcome_exact` catches extra keys & `bool`/`int` mismatches; R5 real tier caps `0.40/0.60/0.80 × bankroll`, `tier_change` covers `balanced`+`aggressive`, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (every declared key in `expected` enforced; canonical-extra-only output/state enforcement rejects spoofed keys; summary integer vs float `6 != 6.0` enforced; `SUC-08` runs all `70` sequential sessions via live state; `SUC-11` runs `2` real calls; `SUC-06/5` runs `12` calls; `SUC-07/3` runs `7` calls)
- Unit tests: **139 tests OK** (`unittest`: `Ran 139 tests` OK; `pytest`: **139 passed, 18 subtests passed**) ✓
- ID-set gate (`tools/check_id_set.py`): **PASS** (`spec=24, engine=24, expected=24`) ✓
- Spec lint (`tools/lint_spec.py`): **PASS** ✓
- Exposure/policy invariant gate (`tools/check_exposure_invariants.py`): **168/168 bundles PASS** ✓ (`symbol` field included in target scope, per-symbol V7 scoping avoids clamping unrestricted `SOXL`, negative `joint_exposure` fail-closed headroom `0.0` handled cleanly)
- Golden generator (`tools/generate_golden_table.py`): **SYNCED (MEM + CLI LF)** ✓ (`140,031` bytes, `git diff 710758c -- goldens/` = **0 bytes**)
- Freeze manifest integrity: **VERIFIED FROM DISK** ✓ (`run_matrix.py` independently recomputes `scenarios.json`, `golden-table.json`, `successor-cases.json`, and `combined_freeze_hash` SHA-256 digests and fails `--strict` on mismatch)
- Deterministic: **YES** ✓ (`run_matrix --strict` + `PYTHONHASHSEED=1,2,3` produce byte-identical `acceptance/result-bundle.json`, and `evaluate()` performs zero file I/O)
- **Option A / Documented v2 Frozen-Oracle Bounds (Preserving `710758c` Freeze `1da74ca5...` at 0 Diff Bytes):**
  1. `L6` & `O1` open-market `index_one_session_returns=None`: frozen `missing.L6` (`goldens/golden-table.json`) stays `NORMAL` (while `{}` and `< 2` dicts fail closed as `HALT`), AND `O1` flags missing/non-finite open-market `index_one_session_returns` whenever an operational payload is present (including contradictory `market_closed=True` alongside open calendar/exchange statuses, leaving genuine `holiday`/`closed` `O1 == NORMAL`), clamping `compute_permitted_exposure` against exposure raises (`45,000` stays `45,000`).
  2. `O1` `missing_required_source_*` intra-session clearing vs frozen `SUC-05` Step 7 (`goldens/successor-cases.json` chains Steps 1–7 on single session `2026-01-05` with minimal `['source_records', 'tier']` inputs expecting `NORMAL` at Step 7): all real operational calls (`stale_or_missing_input`) retain same-session `clearing_period` (`NO-NEW-RISK`); only non-operational minimal `SUC-05` `missing_required_source_*` preserves Step 7 parity.
- Remote CI / PR #3 (`F1-A14`): **PENDING** (local branch unpushed; exact-head CI, `ai-review`, and R2 governance labels pending push)

## Artifact Hashes (Head `440373c` + Unchanged v2 Refreeze)

- **Engine hash (8 sorted files incl. `canonical.py`):** `5bb3a4e448d78d5c5572008a60b8b6a53640b6cfda71f6ba1d96a47e7d5b490c`
- **Bundle hash:** `43e708c0864e2eb6967033c8c7d6b1382f5e8c2045ba476b2b3c0d65650756f4`
- **`acceptance/result-bundle.json` SHA-256 (973 bytes, trailing LF):** `3c0ea7c49e9ecf11395c9860a426ae2d6b53690ad559e830794f2cf4fe350c8b`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (at `d27f51a` / `710758c`, 0 bytes modified in R3–R7 remediation):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## Codex R7 P1 Loophole Fixes (`440373c` & this docs/bundle commit)

1. **`O5` conflicting qty aliases (`rows_ops.py`):** Inspects all supplied qty keys (`o5_order_size`, `order_size`, `o5_order_qty`, `order_qty`, `qty`) and rejects non-finite or numerically disagreeing aliases (`invalid_order_size`), blocking both `order_size=2, o5_order_size=0` buys and `order_size=1001, o5_order_size=1` oversells.
2. **`O5` unbounded explicit buys (`rows_ops.py`):** Explicit buy checks (`side='buy'` or omitted-side order qty) with neither `order_value` nor finite `order_size * price` fail closed (`exceeds_settled_cash`).
3. **`O5` empty `account_whitelist=[]` (`rows_ops.py`):** Active order checks with `account_whitelist=[]` / `o5_account_whitelist=[]` (or non-string entries) fail closed (`account_not_whitelisted`) even when `account` is omitted.
4. **`V2` same-type different-details enqueue (`canonical_state.py`, `rows_vehicle.py`, `evaluator.py`):** Tracks normalized `canonical_ca_identity` across `latched_mismatch_actions` and `pending_action_identities` (without altering frozen `SUC-01`/`SUC-02` state schemas) so `split(ratio=3)` announced during a latched `split(ratio=2)` mismatch is queued and remains `HALT` after mismatch Q4 re-arm.
5. **`V2` non-maskable `hwm_adjusted` validation (`evaluator.py`, `rows_vehicle.py`):** Passes top-level `hwm_adjusted` via `_top_hwm_adjusted` and independently requires strict boolean `True` for every present `hwm_adjusted` key across `validated_inputs`, `funds[sym]`, and `corporate_action`.
6. **`O9` required tier-change target (`rows_ops.py`):** Requires explicit non-empty string target tier (`to`/`new`/`target`/`new_tier`) on both `tier_change_event` and `tier_change_card` strictly matching runtime `tier`.
7. **`O9` consumer-scope & full-fund parameter binding (`rows_ops.py`):** Classifies `reconciliation_tolerance` under `account_only_fields` (matching `O3` top-level consumption so `funds.TQQQ.reconciliation_tolerance=1` cannot spoof `O3=1000`); requires account-level overridable policy cards (`v5_tolerance`, `v7_spread_width`, `v6_threshold`) to bind every configured fund to the approved target value when top-level policy omits it.
8. **`O1` contradictory `market_closed=True` guard (`rows_ops.py`):** Never treats the market as closed in `O1` when `calendar_state`/`session_calendar_status` or `exchange_status` explicitly reads `'open'` without closed tokens, preserving `holiday`/`closed` `O1 == NORMAL` while failing closed on open-market `index_one_session_returns=None` even if `market_closed=True` is injected.

## Prior Codex R6 & History (`31500c9 -> 3a14e18`)

Retains all validated R5 & R6 fixes (`18f8cdd`, `841b7cb`, `f9b6b3a`, `3a14e18`) including `V5` missing-shortfall 40-session escalation preservation, unified `canonical_session_date()`, `O8` latch/clear, `O4` BIL lock survival, `L3`/`L4`/`L6`/`O3`/`O6`/`V1`/`V4`/`V7` hardening, zero-I/O `evaluate()`, disk manifest verification, and `check_exposure_invariants.py`.

## Pending Before Merge

1. Push `demo/fuse1-sonnet` to origin.
2. Trigger and verify passing remote exact-head GitHub CI, `ai-review`, and R2 clearing label (`agent-approved` or `owner-approved`) on PR #3 (`QuantStrategyLab/FuseControl#3`).
