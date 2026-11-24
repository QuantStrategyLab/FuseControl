# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, unchanged relative to `710758c`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / fixture / tool / test head:** `d816ccaf151fdde0b5d18efca5e936bcf127184e` (`d816cca`, preceded by `72d5020`, `de50e4f`, `5ad8072`, `440373c`, `3a14e18`, `f9b6b3a`, `841b7cb`, `e3a7aba`, `18f8cdd`, `3277881`, `ef79aee`, `b1e2ec6`, `9335f26`, `710758c`, `d27f51a`, `b3084d7`; followed by this bundle/docs commit)

## Status

**LOCAL R9 P1 REMEDIATION VERIFIED ON `d816cca` (v2 `goldens/` FREEZE PRESERVED AT 0 DIFF BYTES; REMOTE CI / PR #3 `F1-A14` PENDING PUSH)**

- Base: **264/264** ✓ strict raw dict equality + type equality (`True != 1`) AND **264/264** full independent §4.1 scope maps inside formal `run_matrix.run_base_cells`
- Tier (formal runner): **132/132 EXECUTED** ✓ full-key strict dict + type equality (`compare_base_outcome_exact` catches extra keys & `bool`/`int` mismatches; R5 real tier caps `0.40/0.60/0.80 × bankroll`, `tier_change` covers `balanced`+`aggressive`, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (every declared key in `expected` enforced; canonical-extra-only output/state enforcement rejects spoofed keys; summary integer vs float `6 != 6.0` enforced; `SUC-08` runs all `70` sequential sessions via live state; `SUC-11` runs `2` real calls; `SUC-06/5` runs `12` calls; `SUC-07/3` runs `7` calls)
- Unit tests: **146 tests OK** (`unittest`: `Ran 146 tests` OK; `pytest`: **146 passed, 18 subtests passed**) ✓
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

## Artifact Hashes (Head `d816cca` + Unchanged v2 Refreeze)

- **Engine hash (8 sorted files incl. `canonical.py`):** `7105ad09e26d0903ffa86f48df336cafd30612da1361287d8ddff02b84054f91`
- **Bundle hash:** `4ca56cfe25feab9dbd31fb6c4e5e8bf1c1948d0771d6ea8ed775db7a235e9b0c`
- **`acceptance/result-bundle.json` SHA-256 (973 bytes, trailing LF):** `065a587f8ec579c0d00cbcded1e4a5cec1c79847859649297b1f4acc07a161d5`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (at `d27f51a` / `710758c`, 0 bytes modified in R3–R9 remediation):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## Codex R9 P1 & Decimal Fixes (`d816cca` & this docs/bundle commit)

1. **`V2` omitted-fund pending identity carryover (`evaluator.py`):** Carries forward `latched_mismatch_actions` and `pending_action_identities` when a fund with unresolved corporate-action adjustments is omitted from `funds`, preventing earlier reconciliations from falsely clearing distinct pending dates or actions.
2. **`V2` exact string CA identifiers & dates (`canonical_state.py`):** Restricts float/Decimal normalization in `canonical_ca_identity()` to `_CA_NUMERIC_FIELDS` so string identifiers (`action_id="001"` vs `"1"`) and date fields (`effective_date`, `ex_date`, etc.) retain exact stripped string identity.
3. **`O9` rejection of opaque `limits` / `funds` cards (`rows_ops.py`):** Rejects `"param": "limits"` and `"param": "funds"` on `O9` parameter-change cards (`HALT`, even when paired with valid Q4 `rearm`) instead of passing unenumerated multi-parameter blocks.
4. **`O5` unified alias conflict checks & strict `order_size > 0` (`rows_ops.py`):** Applies `_resolve_o5_alias()` uniformly across `symbol`, `symbol_whitelist`, `account`, `account_whitelist`, `order_size`/`qty`, `side`, `order_value`, `unit_price`, and `ref_price` (preserving canonical `settled_cash` precedence), failing closed on conflicting aliases or non-positive `order_size <= 0` on active orders.
5. **`O5` exact `Decimal` notional & collar arithmetic (`rows_ops.py`):** Evaluates `order_size * unit_price`, cash bounds, `order_value` comparisons, and collar deviations (`|unit_price - ref_price| / ref_price`) via `_to_decimal()`, eliminating IEEE-754 false rejects such as `3 * 33.20 > 99.60`.

## Codex R8 P1 Loophole Fixes (`de50e4f`, retained in `d816cca`)

1. **`O5` Q4 re-arm fallthrough validation (`rows_ops.py`):** Valid `O5` Q4 `rearm` clears the prior latch and session counter, then continues into same-session collar, whitelist, notional, and qty checks so simultaneous invalid orders reject and block exposure increases.
2. **`O5` conflicting side aliases & `order_value <= 0` buy guard (`rows_ops.py`):** Inspects all supplied side keys (`o5_side`, `side`, `order_side`), failing closed on conflicting/invalid values (`not_long_only`) without skipping buy cash validation; explicit positive-qty buys with `order_value <= 0` or `< order_size * price` fail closed (`exceeds_settled_cash`).
3. **`V2` exact identity queue matching (`canonical_state.py`, `rows_vehicle.py`):** Removes type-only fallback matching from `_find_v2_pending_target` and enforces full `canonical_ca_identity` matching (including `effective_date`, `ex_date`, `record_date`, `action_id`, `ratio`, `amount`) via `ca_identity_matches()` so replaying a `split(ratio=2)` mismatch preserves queued `split(ratio=3)` and distinct-date same-ratio splits cannot cross-clear.
4. **`O9` Q4 re-arm fallthrough validation (`rows_ops.py`):** Valid `O9` Q4 `rearm` clears the prior `O9` latch then evaluates any current-session `tier_change_event` / `o9_change_descriptors`, catching unauthorized same-session changes (`HALT`).
5. **`O9` removal of non-consumed `limits` fallback (`rows_ops.py`):** Removes the dead `inputs['limits']` fallback in `_targets_match_live_inputs()` because runtime consumer rows (`O3`, `L0..L4`, `V5..V7`) read top-level `inputs` and/or `funds[sym]` directly, preventing `limits` from masking missing `SOXL` overrides or top-level `O3` `reconciliation_tolerance`.

## Prior Codex R7 & History (`31500c9 -> 5ad8072`)

Retains all validated R5–R7 fixes (`18f8cdd`, `841b7cb`, `f9b6b3a`, `3a14e18`, `440373c`, `5ad8072`), including `O5` conflicting qty aliases & empty whitelist, `V2` active mismatch queue preservation & non-maskable `hwm_adjusted`, `O9` required tier targets & consumer-scope matching, `O1` open-market & contradictory `market_closed` guards, `V5` 40-session escalation preservation on missing data, unified `canonical_session_date()`, `O8` latch/clear, zero-I/O `evaluate()`, and disk manifest checks.

## Pending Before Merge

1. Push `demo/fuse1-sonnet` to origin.
2. Trigger and verify passing remote exact-head GitHub CI, `ai-review`, and R2 clearing label (`agent-approved` or `owner-approved`) on PR #3 (`QuantStrategyLab/FuseControl#3`).
