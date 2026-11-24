# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, unchanged relative to `710758c`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / fixture / tool / test head:** `f9b6b3ae561471418a5391465d1a71a856bcc34b` (`f9b6b3a`, preceded by `841b7cb`, `e3a7aba`, `18f8cdd`, `3277881`, `ef79aee`, `b1e2ec6`, `9335f26`, `710758c`, `d27f51a`, `b3084d7`; followed by this bundle/docs commit)

## Status

**LOCAL R6 P1 REMEDIATION VERIFIED ON `f9b6b3a` (v2 `goldens/` FREEZE PRESERVED AT 0 DIFF BYTES; REMOTE CI / PR #3 `F1-A14` PENDING PUSH)**

- Base: **264/264** ✓ strict raw dict equality + type equality (`True != 1`) AND **264/264** full independent §4.1 scope maps inside formal `run_matrix.run_base_cells`
- Tier (formal runner): **132/132 EXECUTED** ✓ full-key strict dict + type equality (`compare_base_outcome_exact` catches extra keys & `bool`/`int` mismatches; R5 real tier caps `0.40/0.60/0.80 × bankroll`, `tier_change` covers `balanced`+`aggressive`, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (every declared key in `expected` enforced; canonical-extra-only output/state enforcement rejects spoofed keys; summary integer vs float `6 != 6.0` enforced; `SUC-08` runs all `70` sequential sessions via live state; `SUC-11` runs `2` real calls; `SUC-06/5` runs `12` calls; `SUC-07/3` runs `7` calls)
- Unit tests: **135 tests OK** (`unittest`: `Ran 135 tests` OK; `pytest`: **135 passed, 18 subtests passed**) ✓
- ID-set gate (`tools/check_id_set.py`): **PASS** (`spec=24, engine=24, expected=24`) ✓
- Spec lint (`tools/lint_spec.py`): **PASS** ✓
- Exposure/policy invariant gate (`tools/check_exposure_invariants.py`): **168/168 bundles PASS** ✓ (`symbol` field included in target scope, per-symbol V7 scoping avoids clamping unrestricted `SOXL`, negative `joint_exposure` fail-closed headroom `0.0` handled cleanly)
- Golden generator (`tools/generate_golden_table.py`): **SYNCED (MEM + CLI LF)** ✓ (`140,031` bytes, `git diff 710758c -- goldens/` = **0 bytes**)
- Freeze manifest integrity: **VERIFIED FROM DISK** ✓ (`run_matrix.py` independently recomputes `scenarios.json`, `golden-table.json`, `successor-cases.json`, and `combined_freeze_hash` SHA-256 digests and fails `--strict` on mismatch)
- Deterministic: **YES** ✓ (`run_matrix --strict` + `PYTHONHASHSEED=1,2,3` produce byte-identical `acceptance/result-bundle.json`, and `evaluate()` performs zero file I/O)
- **Option A / Documented v2 Frozen-Oracle Bounds (Preserving `710758c` Freeze `1da74ca5...` at 0 Diff Bytes):**
  1. `L6` & `O1` open-market `index_one_session_returns=None`: frozen `missing.L6` (`goldens/golden-table.json`) stays `NORMAL` (while `{}` and `< 2` dicts fail closed as `HALT`), AND `O1` now flags missing/non-finite open-market `index_one_session_returns` whenever an operational payload is present (`NO-NEW-RISK / stale_or_missing_input`, leaving `holiday`/`closed` `O1 == NORMAL`), clamping `compute_permitted_exposure` against exposure raises (`45,000` stays `45,000`).
  2. `O1` `missing_required_source_*` intra-session clearing vs frozen `SUC-05` Step 7 (`goldens/successor-cases.json` chains Steps 1–7 on single session `2026-01-05` with minimal `['source_records', 'tier']` inputs expecting `NORMAL` at Step 7): all real operational calls (`stale_or_missing_input`) retain same-session `clearing_period` (`NO-NEW-RISK`); only non-operational minimal `SUC-05` `missing_required_source_*` preserves Step 7 parity.
- Remote CI / PR #3 (`F1-A14`): **PENDING** (local branch unpushed; exact-head CI, `ai-review`, and R2 governance labels pending push)

## Artifact Hashes (Head `f9b6b3a` + Unchanged v2 Refreeze)

- **Engine hash (8 sorted files incl. `canonical.py`):** `e58c5234d28682101aa108bb547323d9ab4af2eebb29a699c2eca208bfc299f2`
- **Bundle hash:** `9d763173d7f1b92cdec968d664f42243c1c8e2dcd44e68a900dc2f3236324e40`
- **`acceptance/result-bundle.json` SHA-256 (973 bytes, trailing LF):** `2b3e7f75228988e863cd5b2c35957e5a5cc3109afef7c64474b668a8cd339109`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (at `d27f51a` / `710758c`, 0 bytes modified in R3–R6 remediation):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## Codex R6 P1 Blocker Fixes (`f9b6b3a` & this docs/bundle commit)

1. **`O5` spec-canonical `order_size` & null account/whitelist fail-closed (`rows_ops.py`):** Added `'order_size'` to the size lookup (`o5_order_size`, `order_size`, `o5_order_qty`, `order_qty`, `qty`) so buy notional checks and long-only reducing sells resolve uniformly; fails closed (`account_not_whitelisted`) whenever explicit `account`/`account_whitelist` is `None` or an order check runs without a valid account and whitelist.
2. **`V2` active mismatch queue preservation (`rows_vehicle.py`, `evaluator.py`):** Distinct/new `corporate_action` announcements arriving while `latched_mismatches[symbol]` is active (`latched_prior_mismatch`) are enqueued into `pending_adjustments[symbol]` without clearing the mismatch latch, so Q4 re-arming clears only the mismatch latch and keeps `HALT` (`pending_corporate_action_carried`) until reconciled.
3. **`V2` explicit `hwm_adjusted: null` fail-closed (`rows_vehicle.py`, `evaluator.py`):** Replaced `.get('hwm_adjusted')` truthiness with strict key-presence validation so omitted `hwm_adjusted` (`SUC-01`/`SUC-02`) passes while explicit `None`, `False`, `"false"`, or non-bool in `corporate_action`, fund inputs, or top-level inputs triggers `reconciliation_mismatch` (`HALT`).
4. **`O9` required targets, fund-level runtime binding & `row != row_id` (`rows_ops.py`):** Rejects `parameter_change_card` and `tier_change_card` when conflicting `row`/`row_id` or wrong row tags exist; rejects `o9_change_descriptors` / cards missing explicit non-`None` target values (`to`/`new_value`/`new`/`target`/`value`); validates fund-scoped targets (`fund`/`symbol`/`scope='fund:X'`) against effective `funds[fund][param]` (with fallback to top level), and validates account-level overridable params (`v7_spread_width`, `v5_tolerance`, etc.) against all fund-level overrides.
5. **Open-market single missing `index_one_session_returns=None` clamped by `O1` (`rows_ops.py`):** When `has_operational_payload` is active and market is open (not `holiday`/`closed`/`market_closed`), missing/non-dict/`< 2`/non-finite `index_one_session_returns` trips `O1` (`NO-NEW-RISK / stale_or_missing_input`), preventing exposure increases while preserving frozen `missing.L6 == NORMAL` and `holiday.O1 == NORMAL`.
6. **`V5` active 40-session escalation preservation on missing data (`rows_vehicle.py`):** Across unresolved/invalid `v5_tolerance` and missing/invalid `shortfall_observed`/`shortfall_predicted`, funds with prior `escalated == True` or `persistence_count >= 40` retain `state='NO-NEW-RISK'`, `would_have_tripped=True`, `reason='escalated_to_v1_treatment'`, `consecutive_sessions_beyond_tolerance=persistence_count`, `escalated_to_v1=True`, `excess_shortfall=None`, and `disposition='escalated_to_v1'`.

## Prior Codex R5 & History (`31500c9 -> 841b7cb`)

Retains all validated R5 fixes (`18f8cdd`, `841b7cb`) covering unified `canonical_session_date()`, `O8` latch/clear, V2 partial mismatch preservation, `O4` BIL lock survival, `L3`/`L4`/`L6`/`O3`/`O6`/`V1`/`V4`/`V7` hardening, zero-I/O `evaluate()`, disk manifest verification, `check_exposure_invariants.py`, and v2 frozen-oracle Option A bounds.

## Pending Before Merge

1. Push `demo/fuse1-sonnet` to origin.
2. Trigger and verify passing remote exact-head GitHub CI, `ai-review`, and R2 clearing label (`agent-approved` or `owner-approved`) on PR #3 (`QuantStrategyLab/FuseControl#3`).
