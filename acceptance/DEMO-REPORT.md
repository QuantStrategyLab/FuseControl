# FUSE-1 Demonstration & Remediation Report

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, unchanged relative to `710758c`)
- **Writer:** Sonnet
- **Demonstration epoch:** `FUSE-DESIGN-2026-11-21-v1`
- **Verified code / fixture / tool / test head:** `2f23e71f73d13ce10dd6dc4e0558bbd373deaa07` (`2f23e71`, preceded by `02ba196`, `5a10391`, `62892c1`, `8909372`, `87e9e70`, `ce51c92`, `a684584`, `98f15b7`, `0d092dd`, `4f8f482`, `e9639f5`, `57c813b`, `882df2a`, `c39f4d0`, `0c9eb43`, `d816cca`, `72d5020`, `de50e4f`, `5ad8072`, `440373c`, `3a14e18`, `f9b6b3a`, `841b7cb`, `e3a7aba`, `18f8cdd`, `3277881`, `ef79aee`, `b1e2ec6`, `9335f26`, `710758c`, `d27f51a`, `b3084d7`; followed by this bundle/docs commit)

## Status

**LOCAL O4/V5 STATE-DURABILITY & SYMBOL-NORMALIZATION REMEDIATION VERIFIED ON `2f23e71` (v2 `goldens/` FREEZE PRESERVED AT 0 DIFF BYTES; REMOTE CI / PR #3 `F1-A14` PENDING PUSH)**

- Base: **264/264** ✓ strict raw dict equality + type equality (`True != 1`) AND **264/264** full independent §4.1 scope maps inside formal `run_matrix.run_base_cells`
- Tier (formal runner): **132/132 EXECUTED** ✓ full-key strict dict + type equality (`compare_base_outcome_exact` catches extra keys & `bool`/`int` mismatches; R5 real tier caps `0.40/0.60/0.80 × bankroll`, `tier_change` covers `balanced`+`aggressive`, `-1` J1-cap mutation `110 pass / 22 fail` detected)
- Successor: **13/13** ✓ (every declared key in `expected` enforced; canonical-extra-only output/state enforcement rejects spoofed keys; summary integer vs float `6 != 6.0` enforced; `SUC-08` runs all `70` sequential sessions via live state; `SUC-11` runs `2` real calls; `SUC-06/5` runs `12` calls; `SUC-07/3` runs `7` calls)
- Unit tests: **160 tests OK** (`unittest`: `Ran 160 tests` OK; `pytest`: **160 passed, 18 subtests passed**) ✓
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

## Artifact Hashes (Head `2f23e71` + Unchanged v2 Refreeze)

- **Engine hash (8 strictly whitelisted framed `.py` files + strict `rglob('*')` `__pycache__/<stem>.cpython-<digits>.pyc` guard):** `3ef61470ab322c576256ad79b8ec09b84aac45a0f3634ce6d496676808fb0623`
- **Bundle hash:** `8456582fb6c55c83cfe54842492a7b001002ff290911342153cc3a4a476e053b`
- **`acceptance/result-bundle.json` SHA-256 (973 bytes, trailing LF):** `9c47d29c22d118be49e8a587b1c9dcccfbb0f3ce0fd5deee950e877d5508b287`
- **Original freeze (`f60986a`):** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`
- **Adjudication freeze v1 (`86be6d7`):** `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1`
- **Owner-approved v2 refreeze (at `d27f51a` / `710758c`, 0 bytes modified in R3–R14 remediation):**
  - `goldens/FREEZE.json` (`fuse-eval-spec/v2`): `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d`
  - `goldens/scenarios.json` (unchanged): `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
  - `goldens/golden-table.json` (R1/R4/R5): `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d`
  - `goldens/successor-cases.json` (unchanged): `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d`
  - `goldens/DERIVATION.md` (v2 addendum): `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682`
  - **Combined v2 freeze:** `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74`

## Local `gpt-6.2-astra` O4/V5 State-Durability & Symbol-Normalization Fixes (`2f23e71` / `5a10391` & this docs/bundle commit)

- **No spurious `V5` `last_session` on unevaluated ticks (`src/fuse_engine/evaluator.py`)**: When `V5` cannot evaluate (`missing_input`, `unresolved_fail_closed`, `invalid_input`, `market_closed`, or omitted fund) and no prior `V5` state exists, `next_row_state['V5']` no longer records `{consecutive_beyond_tolerance: 0, escalated: False, last_session: session}`, ensuring subsequent same-session telemetry recovery counts cleanly (`1..40 -> NO-NEW-RISK`) rather than being skipped as duplicate; verified `V1`–`V4` similarly do not record blocking session state on initial unevaluated ticks.
- **O4 fund-level `o4_pending_order` recording under `malformed_pending_orders` (`src/fuse_engine/evaluator.py`)**: Evaluates `rows_ops.evaluate_O4` on `funds[symbol]` even when top-level `pending_orders` is malformed (`None`/non-`dict`), recording any newly reported timed-out or malformed fund `o4_pending_order` into `next_row_state['O4'][symbol]` while keeping active `prior_pending` locks un-clearable and failing O4 closed (`ORDER-UNKNOWN`, `malformed_pending_orders`).
- **V5 & V1–V4 state preservation when a target fund is omitted or lacks telemetry (`src/fuse_engine/evaluator.py`, `src/fuse_engine/rows_vehicle.py`)**: Preserves `prior_row_state['V5'][symbol]` (including `consecutive_beyond_tolerance=39`, `escalated`, and `last_session`) across `symbol not in funds`, `missing_input`, `unresolved_fail_closed`, `invalid_input`, and `market_closed` without fabricating fresh entries on closed/omitted calls; verified `V1`–`V4` (`five_session_history`, `V2` pending/mismatch identities, `V3` latch, `V4` clearing counter) all remain durable when omitted from `funds`.
- **Target symbol whitespace normalization across invariant checks (`tools/check_exposure_invariants.py`)**: Shared helper `_extract_target_symbols()` / `_target_scope_and_v7_blocked()` and `_v7_blocks_target()` strip whitespace across `target_fund`, `proposed_fund`, `o5_symbol`, and `symbol` (failing closed on invalid/blank values), preventing leading/trailing whitespace such as `" TQQQ "` from bypassing `fund:TQQQ` / `symbol:TQQQ` / `V7` exposure clamps.

## Remote PR #3 `@codex` Pending-Orders, Vehicle-Order, Order-Symbol & Engine-Binary Remediation (`8909372` & `62892c1`)

- **O4 fail closed on malformed `pending_orders` (`src/fuse_engine/evaluator.py`)**: When `'pending_orders' in validated_inputs` has a non-`dict` value (e.g., `list`, scalar, or explicit `None`), `evaluate()` preserves prior `O4` locks, marks `malformed_pending_orders=True` -> `O4` `ORDER-UNKNOWN` (`reason='malformed_pending_orders'`), and blocks raises on all active symbol scopes (including `'__pending_orders__'` fallback when no symbols are populated).
- **V1–V6 fail closed on non-`BIL` order targets omitted from `funds` (`src/fuse_engine/evaluator.py`)**: Order target symbols outside `funds` other than `'BIL'` are folded into `eval_fund_symbols` with empty per-fund inputs, causing `V1`/`V4` to fail closed (`NO-NEW-RISK`) and block raises on `fund:<sym>`, while keeping `V7` on `funds` + `quotes`/`symbols` and keeping omitted-fund prior lock/escalation tracking intact.
- **O5 fail closed on omitted/blank active order `symbol` (`src/fuse_engine/rows_ops.py`)**: When `order_present` is `True` and `symbol` is `None` or blank whitespace, `O5` appends `'symbol_not_whitelisted'` and halts order submission.
- **Strict recursive engine-directory binary/artifact whitelist (`src/fuse_engine/evaluator.py`, `tools/run_matrix.py`)**: Both `engine_hash` computation helpers now walk `engine_dir.rglob('*')`, rejecting symlinks, non-`__pycache__` subdirectories, non-whitelisted files (`.so`, `.pyd`, `.dylib`, `.pth`, root `.pyc`, extra `.py`), and unexpected `__pycache__` binaries outside `<expected_stem>.cpython-<digits>(.opt-<digits>)?\.pyc`.

## Remote PR #3 `@codex` & `gpt-6.2-astra` O5 P1 & Framed Engine Hash Fixes (`ce51c92` / `98f15b7` & this docs/bundle commit)

1. **`O5` dollar-order & dual `qty+order_value` `max_order_size` enforcement (`rows_ops.py`):** Computes `eff_price_dec` independently of `qty` and enforces BOTH explicit `order_size <= max_order_size_val` (when `qty` is supplied) AND implied `ov_dec <= max_order_size_val * eff_price_dec` (whenever `order_value` is present or `qty` is omitted), failing closed if `order_value` or `eff_price_dec` is missing/invalid/conflicting or if either bound is exceeded.
2. **`O5` mandatory session counters on active orders (`rows_ops.py`):** When `max_orders_per_session` or `max_turnover_per_session` is set and `order_present` is True, missing or `null` `session_order_count` / `session_turnover` fail closed (`exceeds_max_orders` / `exceeds_max_turnover`) rather than defaulting to `0` (preserving `0` fallback when `not order_present`).
3. **`O5` mandatory price collar on active orders (`rows_ops.py`):** Enforces positive finite `unit_price` and `reference_price` (`collar >= 0`) whenever `order_present` is True, failing closed (`invalid_price`) if either price is omitted.
4. **Framed canonical engine hash & file whitelist (`evaluator.py`, `run_matrix.py`, `test_conformance.py`):** Enforces exact `_EXPECTED_ENGINE_FILES` match over `rglob('*.py')` (`RuntimeError` on extra, nested, or missing `.py` files) and writes length-framed records `len(rel_bytes)[4B] + rel_bytes + len(data)[8B] + data` into SHA-256.

## Prior Remote PR #3 Codex Inline P1 Fixes (`4f8f482` / `0d092dd`, retained in `98f15b7`)

1. **`V1` 5-session history bootstrap current-session inclusion (`rows_vehicle.py`):** Removes the 5-item `five_session_history` skip condition in `evaluate_V1` so bootstrapping with 5 prior sessions always appends the current open session (when its `session` is not already present) and slices `[-5:]` before checking 5-session deviation.
2. **`O4` malformed `pending_order` persistence & Q4 symbol re-arm (`canonical_state.py`, `rows_ops.py`, `evaluator.py`):** Assigns `'original_order_id': f'unidentified_order_{symbol}'` when a malformed non-dict `pending_order` arrives with empty `prior_pending` so `O4` locks durably across subsequent `pending_orders={}` calls; adds `cst.matches_symbol_rearm()` so owner dated symbol-scoped Q4 `rearm` (`row='O4', symbol=<sym>`) clears the lock when `pending_orders` is resolved.

## Prior Remote PR #3 Codex Review Fixes (`57c813b` / `e9639f5`, retained in `4f8f482`)

1. **`V5` Q4 re-arm & persistent 40-session escalation (`F1`, `canonical_state.py`, `rows_vehicle.py`, `evaluator.py`):** Once escalated (`>= 40`), `V5` remains `NO-NEW-RISK` (`escalated_to_v1=True`, `latched=False` per `SUC-08`, counter preserved `>= 40` on benign sessions and incremented on new open excess sessions) until cleared by a dated fund-scoped Q4 `rearm` card (including omitted funds via `evaluator.py`).
2. **`V5` closed-market exclusion (`F5`, `rows_vehicle.py`, `evaluator.py`):** Validates `v5_tolerance` first (preserving `holiday.V5` `UNRESOLVED-FAIL-CLOSED` parity), then excludes `market_closed=True` (`holiday`/`closed`) days from persistence counting and preserves prior `V5[symbol]` / `last_session` without fabricating holiday entries.
3. **`O5` mandatory whitelisted account on active orders (`F2`, `rows_ops.py`):** Fails closed (`account_not_whitelisted`) whenever `order_present` omits both `account` and `o5_account` or supplies an unapproved/invalid account.
4. **`O5` projected session turnover check (`F3`, `rows_ops.py`):** Includes proposed order notional (`max(order_value, derived_notional)` across buys and sells in exact `Decimal`) in `tt + proposed_notional > max_turnover`, failing closed on missing/invalid/conflicting order notional when `max_turnover_per_session` is configured.
5. **`V7` evaluation of proposed order symbols outside `funds` (`F4`, `evaluator.py`, `tools/check_exposure_invariants.py`):** Evaluates `V7` and adds `symbol:<sym>` scopes for proposed `o5_symbol`/`symbol` values outside `funds` using `quotes`/`symbols` lookups (failing closed on missing quotes or blank/invalid non-empty symbol types), with matching `_v7_blocks_target` alignment.

## Prior Codex R10 P1 `O5` Fixes (`c39f4d0` / `882df2a`, retained in `57c813b`)

1. **`O5` Sell-side `order_value` conflict validation (`rows_ops.py`):** Rejects conflicting/negative `order_value`/`o5_order_value` aliases uniformly across both buy and sell orders (`invalid_order_value` on sell).
2. **`O5` Daily counter & limit alias conflict checks (`rows_ops.py`):** Applies `_resolve_o5_alias()` across `o5_orders_today`/`session_order_count`, `o5_max_orders_per_session`/`max_orders_per_session`, `o5_turnover_today`/`session_turnover`, `o5_max_turnover_per_session`/`max_turnover_per_session`, and `o5_max_order_size`/`max_order_size`, failing closed on mismatched/negative values.
3. **`O5` Explicit `symbol_whitelist=null` fail-closed (`rows_ops.py`):** Never substitutes default whitelists when `symbol_whitelist` or `o5_symbol_whitelist` is explicitly `None` (or empty on active orders).
4. **`O5` Order-insensitive whitelist equality (`rows_ops.py`):** Canonicalizes valid `str_list` aliases as sorted unique sets so reversed/permuted equivalent whitelists (`symbol_whitelist` vs `o5_symbol_whitelist`) do not false-trip.

## Prior Codex R9 P1 & Decimal Fixes (`d816cca` / `0c9eb43`, retained in `c39f4d0`)

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
