# FUSE-1 Acceptance Bundle

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`, 0 bytes changed vs `710758c`)
- **Code / fixture / tool / test head:** `ef79aee30e6e3a5ec904cad236f9bbfa30beb30f` (R4 remediation at `ef79aee` on top of `b1e2ec6`/`9335f26`/`710758c`/`d27f51a`/`b3084d7`; this bundle/docs commit follows)

## Artifact Hashes

### Engine Hash (§5.3)
```
116014fc6ede62c76a07f79e3e690da0f09833d030b2ef3623e0aaf282d3bd99
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
660b1a97fa1df663dc8f6ef2b387ede5790bc8a63a7216c1c4fcadd8a1af2e01
```
File SHA-256 (`acceptance/result-bundle.json`, trailing LF present): `b1cf7d6de39a010d457a46b3c6d58841391868540ab6cacbf1cd8bebc2532831`.

## Matrix Results (Head `ef79aee`, R1–R8 + Codex R3/R4 Findings Fixed)

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells (strict raw dict equality) | 264 | 0 | 264 | 100% |
| Tier repetitions (EXECUTED, discriminating caps) | 132 | 0 | 132 | 100% |
| Successor cases | 13 | 0 | 13 | 100% |

**Notes:**
- Base cells achieve **264/264 strict raw dictionary + type equality** (`bool` vs `int` rejected; zero `O5` field stripping; `missing.V1` fails closed; all 11 base `O5` cells include `rejection_count_this_session=1`) AND **264/264 independent §4.1 effective-map equality** enforced directly inside formal `tools/run_matrix.py::run_base_cells` as well as `tests/test_full_comparator.py`.
- Formal `tools/run_matrix.py::run_tier_repetitions` enforces real tier-specific caps (`40,000 / 60,000 / 80,000` on 100k baseline; `0.40 / 0.60 / 0.80 × bankroll`), exercises `balanced` + `aggressive` on `tier_change`, honours frozen `restart`/`tier_change` priors, enforces full-key strict equality (`compare_base_outcome_exact`), passes **132/132** against v2 `golden-table.json`, and detects `-1` J1-cap mutation (`110 passed / 22 failed`).
- `SUC-08` executes all **70 sequential sessions** (`1..70`) threading live engine state without frozen `prior_row_state` checkpoint injections (`R6` resolved); `SUC-11` executes 2 real `evaluate()` calls; `SUC-06/5` (`12` calls) and `SUC-07/3` (`7` calls) execute continuous session timelines; successor `next_row_state` rejects `bool` vs `int` mismatches.

## Acceptance Properties (§8)

| ID | Property | Status |
|----|----------|--------|
| F1-A01 | ID-set equality | ✓ PASS (`spec=24, engine=24, expected=24`) |
| F1-A02 | Spec completeness | ✓ PASS (`tools/lint_spec.py`) |
| F1-A03 | Matrix exact agreement | ✓ PASS (`264/264` strict type/raw dict + formal runner `264/264` §4.1 scope maps; `13/13` successor incl. `SUC-08` 70 continuous calls, `SUC-11`, `SUC-06/5`, `SUC-07/3`) |
| F1-A04 | Tier repetitions | ✓ EXECUTED (`132/132` formal runner full-key strict equality w/ real `0.4/0.6/0.8 × bankroll` caps, `tier_change` balanced+aggressive coverage, frozen priors, and `-1` cap mutation detection `110/22`) |
| F1-A05 | Determinism | ✓ PASS (independent runs, `PYTHONHASHSEED=1,2,3`, `canonical_json` round-trip of `missing`, and swapped-order dual-fund V5/V6 produce identical outputs) |
| F1-A06 | Fail-closed battery | ✓ PASS (O3 share counts + omitted tolerance + missing positions; L4 NaN; L6 mixed/invalid indices & missing `bankroll`; V6 canonical precedence + missing inputs; V7 missing quotes; O5 qty×price, canonical `settled_cash`, whitelists; O7 missing heartbeat; O2 invalid token `"n/a"`; J1 `NaN` cap) |
| F1-A07 | Persistence battery | ✓ PASS (V2 multi-action queue, strict `bool` flags, known ratio check, `{}` retention; V1 `five_session_history=[]` & holiday preservation; V4 holiday freeze & omitted-fund scope; L3/L4 persisted dates ignoring caller counters; L5/O1 intra-session retention; L6 `O3` reconciliation gate; O4 strict terminal status) |
| F1-A08 | Precedence battery | ✓ PASS (account `HALT` dominates `joint`; O7 `NO-NEW-RISK` priority; omitted active `V4` kept in `effective_state_by_scope`; Q4 session/date + `account` scope required on account re-arms; O9 single-card authorization) |
| F1-A09 | No-exposure-increase invariant | ✓ PASS (`tools/check_exposure_invariants.py`: `168/168` bundles, catches missing `J1.outputs.cap` & inflated `headroom`, permits `45k -> 40k` reductions & buying unrestricted `SOXL`, pre-call snapshots catching `o5_collar=0.99`) |
| F1-A10 | Interface conformance | ✓ PASS (strict `mode == 'shadow'`, bound `spec_version`, authentic computed `engine_hash` rejecting spoofed digests, aligned `stub_adapter.py` `O4.symbols`/`symbol:*` scopes on timed-out `BIL`) |
| F1-A11 | Disposition register complete | ✓ PASS (`NaN`/inf/bool/neg tolerances fail closed; worst-case multi-fund V5 `disposition`; `disposition-register.json` synced to 5-session implementation) |
| F1-A12 | V2 branches | ✓ PASS (multi-action queue preserving unresolved `split`, strict `bool` completion flags, required ratio match, share+value reconciliation, `{}` pending retention) |
| F1-A13 | Offline proof | ✓ PASS (pure function, synthetic inputs only, zero network/broker endpoints) |
| F1-A14 | Gates (CI, bot, review) | **PENDING** — local commits on `demo/fuse1-sonnet` are unpushed; exact-head CI, `ai-review`, and R2 clearing gates on PR #3 remain pending push and CI execution (remote PR head is `ad404ad`, draft, no labels). **NOT READY FOR MERGE until remote gates clear.** |

## PR #3 Gate Snapshot (Historical Remote Read-Only State)

PR #3 (`QuantStrategyLab/FuseControl#3`) remains a draft PR whose remote `headRefOid` (`ad404ad915e101aa0ec007be3ca3ba078116d26b`) predates all local remediation commits (`31500c9..ef79aee` + this bundle/doc commit):
- On remote `ad404ad` (`gh pr view 3` at `2026-11-24T08:55:52Z`): `labels: []`, `ai-review: PENDING`, `Evaluate PR governance: FAILURE`, `risk-gate: FAILURE`, `Record the head a clearing label was added to: SKIPPED`, docs/Gitleaks/GitGuardian/`pr-template: SUCCESS`.
- No remote CI run or `ai-review` exists for current local HEAD yet because pushing and PR edits are withheld per demonstration protocol.

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

- Full unit test suite: `Ran 119 tests` OK (`pytest`: `119 passed, 18 subtests passed`), plus `check_id_set.py` PASS, `lint_spec.py` PASS, and `check_exposure_invariants.py` (`168/168` bundles) PASS.
- Nothing pushed and PR #3 untouched per demonstration protocol; exact-head remote CI remains pending push.
- Owner-approved v2 refreeze (`d27f51a`) updated only `goldens/golden-table.json`, `goldens/DERIVATION.md`, and `goldens/FREEZE.json` for R1/R4/R5; all files under `goldens/` remain 0 bytes modified relative to `710758c`.
