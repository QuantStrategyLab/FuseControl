# FUSE-1 Acceptance Bundle

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, 0 bytes changed vs `710758c`)
- **Code / fixture / tool / test head:** `d21980d7d6678ed108ba4da83689a7ae4d2aa1c2` (`@codex` prior_row_state, V3 malformed `fund_event`, O4 terminal-before-timeout & import-time `.pyc` verification hardening at `d21980d` on top of `affa79b`/`b4dc687`/`c5a6c19`/`2f23e71`/`02ba196`/`5a10391`/`62892c1`/`8909372`/`87e9e70`/`ce51c92`/`a684584`/`98f15b7`/`0d092dd`/`4f8f482`/`e9639f5`/`57c813b`/`882df2a`/`c39f4d0`/`0c9eb43`/`d816cca`/`72d5020`/`de50e4f`/`5ad8072`/`440373c`/`3a14e18`/`f9b6b3a`/`841b7cb`/`e3a7aba`/`18f8cdd`/`3277881`/`ef79aee`/`b1e2ec6`/`9335f26`/`710758c`/`d27f51a`/`b3084d7`; this bundle/docs commit follows)

## Artifact Hashes

### Engine Hash (§5.3)
```
12e9b502367a4993d0c36e75ac5c8d24acaee2d1247c5b594796d5adda04ca45
```

Computed from canonical bundle (8 sorted Python files):
```
src/fuse_engine/__init__.py
src/fuse_engine/canonical.py
src/fuse_engine/canonical_state.py
src/fuse_engine/evaluator.py
src/fuse_engine/rows_loss.py
src/fuse_engine/rows_ops.py
src/fuse_engine/rows_vehicle.py
src/fuse_engine/state.py
```

### Golden Table Freeze Hashes (§6.2)

**Original freeze (head `f60986a`):**
| File | SHA-256 |
|------|---------|
| `scenarios.json` | `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b` |
| `golden-table.json` | `5aaa940fbf8964bb99a6956e70be16bfe895a3dd0b8328c177a66d4c4b3343a2` |
| `successor-cases.json` | `08ee38c966e4c2a8a9609e940c7ef0a4d82b9b60b527c2f5dad62e5fc0b994d3` |
| **Combined freeze** | `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50` |

**Adjudication re-freeze v1 (head `86be6d7`, 30 successor golden corrections):**
| File | SHA-256 |
|------|---------|
| `scenarios.json` | `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b` |
| `golden-table.json` | `5aaa940fbf8964bb99a6956e70be16bfe895a3dd0b8328c177a66d4c4b3343a2` |
| `successor-cases.json` | `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d` |
| **Combined freeze** | `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1` |

**Owner-approved v2 refreeze (head `d27f51a`, R1/R4/R5 reconciliation):**
| File | SHA-256 |
|------|---------|
| `scenarios.json` (unchanged) | `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b` |
| `golden-table.json` (R1/R4/R5 updated) | `a9750d390fe194e947e9593dee53f3a0dbbba9e465a6dad374f449d24c265e8d` |
| `successor-cases.json` (unchanged) | `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d` |
| `DERIVATION.md` (v2 addendum) | `eaa8034df0271cbeca9297a77c76ca3c6b4bd0968dd433ed7082af28c80a4682` |
| `FREEZE.json` (`fuse-eval-spec/v2`) | `2262eabd746d2c6ff9e0e5f49853244d638b550330db049d2af9c41c659dd89d` |
| **Combined v2 freeze** | `1da74ca508161ba6d9a424101321381a9f5156d8cb2c84c03be2fd2fe3f22a74` |

### Result Bundle Hash

```
78fed9dfc9b0b0a618fce6bb5a956063135f34845545e6a5154a32e119354cc9
```
File SHA-256 (`acceptance/result-bundle.json`, trailing LF present): `ca3af33909c2fd5c26364458406de710197dd87dc8c9f1234adef0c1f60cbd42`.

## Matrix Results (Head `d21980d`, `@codex` Prior-State, V3-Event, O4-Terminal & Pycache Security Remediation Applied; Option A v2 `goldens/` Freeze Unchanged)

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells (strict raw dict equality) | 264 | 0 | 264 | 100% |
| Tier repetitions (EXECUTED, discriminating caps) | 132 | 0 | 132 | 100% |
| Successor cases | 13 | 0 | 13 | 100% |

**Notes:**
- Base cells achieve **264/264 strict raw dictionary + type equality** (`bool` vs `int` rejected; zero `O5` field stripping; `missing.V1` fails closed; all 11 base `O5` cells include `rejection_count_this_session=1`) AND **264/264 independent §4.1 effective-map equality** enforced directly inside formal `tools/run_matrix.py::run_base_cells` as well as `tests/test_full_comparator.py`.
- Formal `tools/run_matrix.py::run_tier_repetitions` enforces real tier-specific caps (`40,000 / 60,000 / 80,000` on 100k baseline; `0.40 / 0.60 / 0.80 × bankroll`), exercises `balanced` + `aggressive` on `tier_change`, honours frozen `restart`/`tier_change` priors, enforces full-key strict equality (`compare_base_outcome_exact`), passes **132/132** against v2 `golden-table.json`, and detects `-1` J1-cap mutation (`110 passed / 22 failed`).
- `run_matrix.py` independently recomputes `scenarios.json`, `golden-table.json`, `successor-cases.json`, and `combined_freeze_hash` SHA-256 digests from disk and fails `--strict` on mismatch.
- `SUC-08` executes all **70 sequential sessions** (`1..70`) threading live engine state without frozen `prior_row_state` checkpoint injections (`R6` resolved); `SUC-11` executes 2 real `evaluate()` calls; `SUC-06/5` (`12` calls) and `SUC-07/3` (`7` calls) execute continuous session timelines; successor comparisons enforce `strict_value_equal` across summary counters (`6 != 6.0`), every key declared in `expected`, and canonical-schema checks rejecting unexpected extra keys in outcomes and `next_row_state`.

## Acceptance Properties (§8)

| ID | Property | Status |
|----|----------|--------|
| F1-A01 | ID-set equality | ✓ PASS (`spec=24, engine=24, expected=24`) |
| F1-A02 | Spec completeness | ✓ PASS (`tools/lint_spec.py`) |
| F1-A03 | Matrix exact agreement | ✓ PASS (`264/264` strict type/raw dict + formal runner `264/264` §4.1 scope maps; `13/13` successor incl. `SUC-08` 70 continuous calls, `SUC-11`, `SUC-06/5`, `SUC-07/3`; `FREEZE.json` SHA-256 verified from disk) |
| F1-A04 | Tier repetitions | ✓ EXECUTED (`132/132` formal runner full-key strict equality w/ real `0.4/0.6/0.8 × bankroll` caps, `tier_change` balanced+aggressive coverage, frozen priors, and `-1` cap mutation detection `110/22`) |
| F1-A05 | Determinism | ✓ PASS (independent runs, `PYTHONHASHSEED=1,2,3`, `canonical_json` round-trip, zero file I/O in `evaluate()`, and swapped-order multi-fund V5/V6 produce identical outputs) |
| F1-A06 | Fail-closed battery | ✓ PASS (Option A / frozen v2 bounds preserved at 0 diff bytes: `L0`/`L1`/`L2` `NaN`/`bool`; `L5`/`L6` invalid/non-int/bool/out-of-range `market_halt_level` (`'3'`, `'unavailable'`, `True`, `False`, `-1`, `4`, `1.5`, `NaN`); `L6` `{}` & `< 2` indices; `O1` blocks open-market `index_one_session_returns=None`/empty/non-finite even with contradictory `market_closed=True` alongside open calendar/exchange statuses, preserving `missing.L6 == NORMAL` and genuine `holiday`/`closed` `O1 == NORMAL`; `SUC-05` minimal `['source_records','tier']` Step 7; `O3` empty `funds`; `O4` non-`dict`/null `pending_orders` (`ORDER-UNKNOWN`), terminal status checked cleanly before creating fresh timeouts while preserving order-ID guards; `O5` omitted/blank order `symbol`, omitted/null active-order `side` (`not_long_only`), conflicting symbol/whitelist/account/qty/side/order_value/price aliases, dollar-order & dual `qty+order_value` `max_order_size` check via `ov_dec / eff_price`, missing/`null` `session_order_count`/`session_turnover` under caps, mandatory price collar when `order_present`, mandatory whitelisted `account` on active orders, projected turnover overrun `tt + proposed_notional > max_turnover`, `order_size <= 0`, exact `Decimal` notional/collar bounds (`3 * 33.20 == 99.60`), unbounded buys, empty `account_whitelist=[]` & null `account`/`account_whitelist`/notional/`settled_cash`/long-only sells; `O6` blank hashes; `O9` rejecting `"param": "limits"`/`"funds"`; `V1`–`V6` non-`BIL` active order target omitted from `funds` (`NO-NEW-RISK`); `V3` malformed/unrecognized `fund_event` (`DE-RISK / invalid_input`); `V5` `excess_shortfall=None` & holiday `UNRESOLVED-FAIL-CLOSED`; `V7` non-bool `trading_pause` & proposed order symbols outside `funds`; `evaluate()` non-`None` non-`dict` `prior_row_state` & null guards) |
| F1-A07 | Persistence battery | ✓ PASS (O8 kill-switch latch & Q4 clear; V2 carries forward `pending_action_identities` & `latched_mismatch_actions` on omitted/vehicle-order funds, enqueues distinct CA incl. same-type different-details during active mismatch latch & retains pending items across mismatch rearm until reconciled, exact string `action_id` (`"001" != "1"`) & date identity matching, strict non-maskable `bool` `hwm_adjusted` across top/fund/CA incl. rejecting explicit `null`, finite mismatch state; V1 `five_session_history=[]` & omitted-fund history preservation, 5-entry `five_session_history` bootstrap still appends current session, & holiday preservation; V4 holiday freeze before `triggered`, missing-fund preservation, & 2nd-fund/omitted-fund `V4.outputs`; V5 omits fake `last_session` on fresh unevaluated ticks (`missing_input`/`unresolved_fail_closed`/`invalid_input`) so same-day recovery + 39 days reaches `40`, preserves `39`-session count & `last_session` across omitted/vehicle-order/missing-telemetry funds until recovery (`39 -> 40`), escalation persists `NO-NEW-RISK` & count >= 40 across benign/omitted/missing-shortfall sessions until dated fund Q4 re-arm, and `market_closed` preserves prior count/session without advancing `39 -> 40`; L3/L4 canonical `session > as_of[:10]`, L3 dynamic day-10 counter, L4 holiday rearm refusal; L5/O1 canonical session intra-day retention; O4 `BIL` lock survival, newly reported fund `o4_pending_order` recording under malformed `pending_orders`, & durable `unidentified_order_<sym>` persistence until resolved Q4 re-arm) |
| F1-A08 | Precedence & authorization | ✓ PASS (account `HALT` dominates `joint`; O7 `NO-NEW-RISK` priority; omitted active `V4`/escalated `V5` kept in scopes & clearable via dated fund Q4 `rearm`; O4 clears `unidentified_order_<sym>` only via dated symbol-scoped Q4 `rearm` when `pending_orders` resolved; V7 evaluates proposed order symbols outside `funds` with matching `_v7_blocks_target`; Q4 rejects `row != row_id` across re-arms and O9 tier/parameter cards, runs same-session validation after `O5`/`O9` Q4 re-arm including rejecting `"param": "limits"`/`"funds"`, requires date on account + V1/V2/V3/V5 fund + O4 symbol re-arms & O9 cards, requires explicit non-empty tier targets & param targets, enforces consumer-row scope matching on `reconciliation_tolerance` and full-fund binding on account-level overridable policy cards) |
| F1-A09 | No-exposure-increase invariant | ✓ PASS (`tools/check_exposure_invariants.py`: `168/168` bundles, includes `symbol` target + stripped whitespace normalization across `target_fund`/`proposed_fund`/`o5_symbol`/`symbol`/`_v7_blocks_target`, per-symbol V7 scoping incl. non-fund `quotes`/`symbols` without falsely clamping unrestricted targets, `0.0` headroom on negative `joint_exposure`, pre-call immutability snapshots) |
| F1-A10 | Interface conformance | ✓ PASS (enforces `spec_version == 'fuse-eval-spec/v1'`, `mode == 'shadow'`, & `prior_row_state is None or isinstance(prior_row_state, dict)`, import-time verification in `__init__.py` & `evaluator.py` before submodule imports + length-framed `engine_hash` over strict `_EXPECTED_ENGINE_FILES` whitelist + recursive `rglob('*')` rejecting symlinks, extra subdirs, `.so`/`.pyd`/`.dylib`/`.pth`, root `.pyc`, non-whitelisted/tampered `__pycache__/*.pyc` bytecode mismatch, zero file I/O with precomputed `engine_hash`, aligned `stub_adapter.py` single-fund `fund` & single-symbol `symbol` keys) |
| F1-A11 | Disposition register complete | ✓ PASS (`NaN`/inf/bool/neg tolerances fail closed; worst-case multi-fund V5 `disposition`; `disposition-register.json` synced to 5-session implementation) |
| F1-A12 | V2 branches | ✓ PASS (carries forward `pending_action_identities` & `latched_mismatch_actions` on omitted funds, enqueues new/distinct CA incl. same-type differing details even while mismatch is latched, keeps unrelated `split` pending across mismatch re-arm until all actions match exact `canonical_ca_identity()` incl. string `action_id` (`"001" != "1"`) & dates; strict non-maskable `bool` completion & `hwm_adjusted` across top/fund/CA incl. rejecting explicit `null`; known ratio match; finite mismatch storage; `{}` pending retention) |
| F1-A13 | Offline proof | ✓ PASS (pure function, zero file I/O in `evaluate()`, synthetic inputs only, zero network/broker endpoints) |
| F1-A14 | Gates (CI, bot, review) | **PENDING** — local commits on `demo/fuse1-sonnet` await push; exact-head CI, `ai-review`, and R2 clearing label on PR #3 will execute upon push (remote PR head is `ad404ad`). |

## PR #3 Gate Snapshot (Historical Remote Read-Only State)

PR #3 (`QuantStrategyLab/FuseControl#3`) remains a draft PR whose remote `headRefOid` (`ad404ad915e101aa0ec007be3ca3ba078116d26b`) predates all local remediation commits (`31500c9..d21980d` + this bundle/doc commit):
- On remote `ad404ad` (`gh pr view 3` at `2026-11-24T08:55:52Z`): `labels: []`, `ai-review: PENDING`, `Evaluate PR governance: FAILURE`, `risk-gate: FAILURE`, `Record the head a clearing label was added to: SKIPPED`, docs/Gitleaks/GitGuardian/`pr-template: SUCCESS`.
- No remote CI run or `ai-review` exists for current local HEAD yet because pushing and PR edits are withheld pending owner push authorization.

## Disposition Register

See `disposition-register.json` for the complete §4.5 register.

**Summary:**
- 3 parameters CONFIRMED-AS-SPEC (L6, V1, V4)
- 3 parameters UNRESOLVED-FAIL-CLOSED (V5 tolerance, V7 width, O5 collar)
- All unresolved parameters verified to fail closed (F1-A11)
- Grep proof: no numeric defaults for unresolved parameters

## Bundle Contents

```
acceptance/
├── ACCEPTANCE-BUNDLE.md          # This file
├── DEMO-REPORT.md                # Detailed demonstration & remediation status
├── disposition-register.json     # §4.5 disposition register
└── result-bundle.json            # Matrix execution results
```

## Notes

- Full unit test suite: `Ran 162 tests` OK (`-B` & non-`-B`; `pytest`: `162 passed, 18 subtests passed`), plus `check_id_set.py` PASS, `lint_spec.py` PASS, `check_exposure_invariants.py` (`168/168` bundles) PASS, and `generate_golden_table.py --verify-only` (`0` golden diff bytes).
- Option A / frozen v2 bounds (`missing.L6` `NORMAL` guarded by `O1` `NO-NEW-RISK`, and `SUC-05` minimal Step 7) are documented while preserving 0-byte `goldens/` diff from `710758c`. Nothing pushed and PR #3 untouched per local remediation protocol.
- Owner-approved v2 refreeze (`d27f51a`) updated only `goldens/golden-table.json`, `goldens/DERIVATION.md`, and `goldens/FREEZE.json` for R1/R4/R5; all files under `goldens/` remain 0 bytes modified relative to `710758c`.
