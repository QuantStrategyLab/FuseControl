# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, unchanged relative to `710758c`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / fixture / tool / test head:** `18f8cdd12e82358068f75e333391a46af103331e` (`18f8cdd`, preceded by `3277881`, `ef79aee`, `b1e2ec6`, `9335f26`, `710758c`, `d27f51a`, `b3084d7`; followed by this bundle/docs commit)

## Status

**LOCAL R5 REMEDIATION VERIFIED ON `18f8cdd` (v2 `goldens/` FREEZE PRESERVED AT 0 DIFF BYTES; REMOTE CI / PR #3 `F1-A14` PENDING PUSH)**

- Base: **264/264** ✓ strict raw dict equality + type equality (`True != 1`) AND **264/264** full independent §4.1 scope maps inside formal `run_matrix.run_base_cells`
- Tier (formal runner): **132/132 EXECUTED** ✓ full-key strict dict + type equality (`compare_base_outcome_exact` catches extra keys & `bool`/`int` mismatches; R5 real tier caps `0.40/0.60/0.80 × bankroll`, `tier_change` covers `balanced`+`aggressive`, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (every declared key in `expected` enforced; canonical-extra-only output/state enforcement rejects spoofed keys; summary integer vs float `6 != 6.0` enforced; `SUC-08` runs all `70` sequential sessions via live state; `SUC-11` runs `2` real calls; `SUC-06/5` runs `12` calls; `SUC-07/3` runs `7` calls)
- Unit tests: **129 tests OK** (`unittest`: `Ran 129 tests` OK; `pytest`: **129 passed, 18 subtests passed**) ✓
- ID-set gate (`tools/check_id_set.py`): **PASS** (`spec=24, engine=24, expected=24`) ✓
- Spec lint (`tools/lint_spec.py`): **PASS** ✓
- Exposure/policy invariant gate (`tools/check_exposure_invariants.py`): **168/168 bundles PASS** ✓ (`symbol` field included in target scope, per-symbol V7 scoping avoids clamping unrestricted `SOXL`, negative `joint_exposure` fail-closed headroom `0.0` handled cleanly)
- Golden generator (`tools/generate_golden_table.py`): **SYNCED (MEM + CLI LF)** ✓ (`140,031` bytes, `git diff 710758c -- goldens/` = **0 bytes**)
- Freeze manifest integrity: **VERIFIED FROM DISK** ✓ (`run_matrix.py` independently recomputes `scenarios.json`, `golden-table.json`, `successor-cases.json`, and `combined_freeze_hash` SHA-256 digests and fails `--strict` on mismatch)
- Deterministic: **YES** ✓ (`run_matrix --strict` + `PYTHONHASHSEED=1,2,3` produce byte-identical `acceptance/result-bundle.json`, and `evaluate()` performs zero file I/O)
- **Documented v2 Frozen-Oracle Bounds (Preserving `710758c` Freeze `1da74ca5...` at 0 Diff Bytes):**
  1. `L6` open-market `index_one_session_returns=None` vs frozen `missing.L6` (`goldens/golden-table.json` requires `NORMAL`): `{}` and partial `< 2` dicts fail closed (`HALT`), while open-market `None` matches frozen `missing.L6` and any new exposure increase remains blocked by `O1`/`V1` (`NO-NEW-RISK`).
  2. `O1` `missing_required_source_*` intra-session clearing vs frozen `SUC-05` Step 7 (`goldens/successor-cases.json` chains Steps 1–7 on single session `2026-01-05` with minimal `['source_records', 'tier']` inputs expecting `NORMAL` at Step 7): all real operational calls (`stale_or_missing_input`) retain same-session `clearing_period` (`NO-NEW-RISK`); only non-operational minimal `SUC-05` `missing_required_source_*` preserves Step 7 parity.
- Remote CI / PR #3 (`F1-A14`): **PENDING** (local branch unpushed; exact-head CI, `ai-review`, and R2 governance labels pending push)

## Artifact Hashes (Head `18f8cdd` + Unchanged v2 Refreeze)

- **Engine hash (8 sorted files incl. `canonical.py`):** `377140cc434b01e1697fcbf9cb8e9e5f08651ffe76c6e12afd0e94f7e6302532`
- **Bundle hash:** `6becd05a24c75cad5e3573168f91199ee66be916c7a3b8221e1cd9e001745a29`
- **`acceptance/result-bundle.json` SHA-256 (973 bytes, trailing LF):** `ccafc9f01afa8fcbd3cc927dd340e378765844cb9e19d2b8ba1260b5e311f498`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (at `d27f51a` / `710758c`, 0 bytes modified in R3/R4 remediation):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## Codex R5 Remediation Sweep (`18f8cdd` & this docs/bundle commit)

1. **Unified session date & Q4 re-arm authorization (`canonical_state.py`, `rows_loss.py`, `rows_ops.py`, `rows_vehicle.py`, `evaluator.py`):** Added `canonical_session_date()` preferring `session` over `as_of[:10]` across `L4`/`L5`/`O1` and re-arm checks (fixing UTC-midnight premature clearing). Rejected conflicting dual `row != row_id` cards, enforced `require_date=True` across all account re-arms (`L2`/`L3`/`L4`/`L6`/`O3`/`O5`/`O6`/`O7`/`O9`), and added `matches_fund_rearm()` with Q4 date/fund/`fund:<id>`-scope enforcement on `V1`/`V2`/`V3`.
2. **`O8` kill-switch persistence (`rows_ops.py`, `evaluator.py`, `canonical_state.py`):** Active `kill_switch` commands persist `next_row_state['O8'] = {'latched': True, 'trip_session': ...}` until an explicit Q4-validated `kill_switch_clear`/`rearm` clears it to `{}` (un-tripped evaluations omit `'O8'`).
3. **`V2` partial mismatch queue preservation, strict `hwm_adjusted`, finite mismatch (`evaluator.py`, `rows_vehicle.py`):** Reconciliation mismatch removes only the targeted action from `pending_adjustments`, retaining un-reconciled `split` across `V2` mismatch re-arm until reconciled; `hwm_adjusted` requires strict boolean `True` (rejecting `"false"`); mismatch details sanitize `NaN`/`Inf` via `finite_float()`.
4. **`O9` card date & live-value binding (`rows_ops.py`):** Both `tier_change_card` and `parameter_change_card` enforce Q4 session/`as_of` dates; `o9_change_descriptors` and matched cards are checked against actual runtime values in `validated_inputs`.
5. **`O5` reducing sells, notional/settled_cash & strict whitelists (`rows_ops.py`):** Permits genuine long-only reducing sells within `share_count`/`position` while rejecting shorts/oversells/missing qty; recognizes `unit_price`; checks `max(order_value, qty * unit_price)` against settled cash; gives canonical `'settled_cash'` sole precedence when present; fails closed on null/non-list `account_whitelist` and validates both `account` and `o5_account`.
6. **Row & null-input hardening (`rows_loss.py`, `rows_vehicle.py`, `rows_ops.py`, `evaluator.py`):** `L0`/`L1`/`L2` use `finite_float` + range checks (`NaN`/`bool` fail closed); `L3` always reports dynamic `cooling_off_days_remaining`; `L4` stays latched on `market_closed=True`; `L6` fails closed on `{}` and `< 2` indices during open markets (`None` remains blocked on frozen `missing.L6`); `O3` requires non-empty `funds`; `evaluator.py` safely guards `funds=None`/`pending_orders=None`; `O4` preserves `BIL` lock across malformed reports and unidentified timeouts; `O6` rejects blank policy hashes; `V4` freezes active counter before `triggered` on holidays and emits `V4.outputs` when any fund triggers; `V5` preserves escalated omitted funds and emits `excess_shortfall=None` on missing data; `V7` requires explicit `bool` `trading_pause`.
7. **Zero-I/O `evaluate()`, harness & invariant fixes (`evaluator.py`, `check_exposure_invariants.py`, `run_matrix.py`, `fixtures/stub_adapter.py`, tests):** Precomputes `_CANONICAL_ENGINE_HASH` at import (zero I/O in `evaluate()`) and validates `spec_version == 'fuse-eval-spec/v1'`; `check_exposure_invariants.py` inspects `symbol`, scopes `V7` per target symbol, and expects `0.0` headroom on negative `joint_exposure`; `run_matrix.py` verifies `FREEZE.json` SHA-256 digests from disk, uses `strict_value_equal` on summary counters, and catches extra outcome/state keys and undeclared expected keys; `stub_adapter.py` emits single-fund `fund` and single-symbol `symbol` keys; `tests/test_full_comparator.py` uses in-memory serialization cleanly in read-only environments.
8. **Prior Codex R4 & History (`31500c9 -> 3277881`):** Retains all validated fixes from Slices 1–4 (`86be6d7`), Remediation G1–G7, R1–R7 & v2 refreeze (`d27f51a`), R3 (`9335f26`), and R4 (`ef79aee`). Note on frozen `goldens/`: `goldens/` remains 0 bytes changed vs `710758c` (including J1 signed `-5000.0` at `golden-table.json:3894`, `missing.L6`, and `SUC-05` Step 7 pending v3 decision).

## Pending Before Merge

1. Push `demo/fuse1-sonnet` to origin after local Blocker-scoped R6 verification.
2. Trigger and verify passing remote exact-head GitHub CI, `ai-review`, and R2 clearing label (`agent-approved` or `owner-approved`) on PR #3 (`QuantStrategyLab/FuseControl#3`).
