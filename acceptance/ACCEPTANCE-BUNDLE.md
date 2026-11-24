# FUSE-1 Acceptance Bundle

- **Branch:** `demo/fuse1-sonnet`
- **Spec version:** `fuse-eval-spec/v1`
- **Golden freeze version:** `fuse-eval-spec/v2` (`1da74ca5...`, owner-approved v2 refreeze `2026-11-24`)
- **Code / test / v2-freeze / bundle head:** `d27f51a4f7d0c5f441503ddd28b9b239638c8e65` (`R2/R3/R6/R7` at `b3084d7`, `R1/R4/R5` + v2 refreeze at `d27f51a`; this docs commit follows on top)

## Artifact Hashes

### Engine Hash (§5.3)
```
96b0ebc4869225577e23358b530a5428b0d0d9b53d75c536f4abd84063185fa9
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
5244c3a365c5eaf7b19f04ab592fd506c2fd7d7b1e4119f908bde4e02561c746
```
File SHA-256 (`acceptance/result-bundle.json`, trailing LF present): `a40a0c309aabda9f2d923774ea3fdf6284da962ee8b36dadcde3735a61e21515`.

## Matrix Results (Head `d27f51a`, R1–R7 Fixed + v2 Refreeze)

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells (strict raw dict equality) | 264 | 0 | 264 | 100% |
| Tier repetitions (EXECUTED, discriminating caps) | 132 | 0 | 132 | 100% |
| Successor cases | 13 | 0 | 13 | 100% |

**Notes:**
- Base cells achieve **264/264 strict raw dictionary equality** (zero `O5` field stripping; `missing.V1` fails closed to `NO-NEW-RISK/missing_input` with `funds=['TQQQ', 'SOXL']`; all 11 base `O5` cells include `rejection_count_this_session=1`) AND **264/264 independent §4.1 effective-map equality** (`tests/test_full_comparator.py`).
- Formal `tools/run_matrix.py::run_tier_repetitions` enforces real tier-specific caps (`40,000 / 60,000 / 80,000` on 100k baseline; `0.40 / 0.60 / 0.80 × bankroll`), exercises `balanced` + `aggressive` on `tier_change`, honours frozen `restart`/`tier_change` priors, passes **132/132** against v2 `golden-table.json`, and detects `-1` J1-cap mutation (`110 passed / 22 failed`).
- `SUC-08` executes all **70 sequential sessions** (`1..70`) threading live engine state without frozen `prior_row_state` checkpoint injections (`R6` resolved); `SUC-11` executes 2 real `evaluate()` calls; `SUC-06/5` (`12` calls) and `SUC-07/3` (`7` calls) execute continuous session timelines.

## Acceptance Properties (§8)

| ID | Property | Status |
|----|----------|--------|
| F1-A01 | ID-set equality | ✓ PASS (`spec=24, engine=24, expected=24`) |
| F1-A02 | Spec completeness | ✓ PASS (`tools/lint_spec.py`) |
| F1-A03 | Matrix exact agreement | ✓ PASS (`264/264` strict raw dict + `264/264` §4.1 scope maps; `13/13` successor incl. `SUC-08` 70 continuous calls, `SUC-11`, `SUC-06/5`, `SUC-07/3`) |
| F1-A04 | Tier repetitions | ✓ EXECUTED (`132/132` formal runner w/ real `0.4/0.6/0.8 × bankroll` caps, `tier_change` balanced+aggressive coverage, frozen priors, and `-1` cap mutation detection `110/22`) |
| F1-A05 | Determinism | ✓ PASS (independent runs & `PYTHONHASHSEED=1,2,3` produce byte-identical `result-bundle.json`) |
| F1-A06 | Fail-closed battery | ✓ PASS (R1 missing `index_return` refuses `NO-NEW-RISK`; original 9 probes + V1 5-session Jan 5–9 -> `2.5251253 pp` latched `NO-NEW-RISK`) |
| F1-A07 | Persistence battery | ✓ PASS (R2 V1 5-session history preserved across Jan 13–20 holiday/closed calls + V4/V1/V2/L3/L4 continuity + `SUC-11` deep shape) |
| F1-A08 | Precedence battery | ✓ PASS (account `HALT` dominates `joint` + narrower scopes) |
| F1-A09 | No-exposure-increase invariant | ✓ PASS (`tools/check_exposure_invariants.py`: `168/168` bundles incl. real multi-step successor chains & `SUC-08` 70 sessions, pre-call baseline snapshots catching `o5_collar=0.99` tampering) |
| F1-A10 | Interface conformance | ✓ PASS (bound `spec_version`, `engine_hash`, `enforcement_mode`, `loss_breakers_armed`; hash-change probe) |
| F1-A11 | Disposition register complete | ✓ PASS |
| F1-A12 | V2 branches | ✓ PASS (R3 strict `ledger_val == broker_val`; `25,000` vs `24,900` w/ `reconciliation_tolerance=100` latches `HALT`) |
| F1-A13 | Offline proof | ✓ PASS (pure function, synthetic inputs only, zero network/broker endpoints) |
| F1-A14 | Gates (CI, bot, review) | **PENDING** — local commits on `demo/fuse1-sonnet` are unpushed; exact-head CI, `ai-review`, and R2 clearing gates on PR #3 remain pending push and CI execution (remote PR head is `ad404ad`, draft, no labels). **NOT READY FOR MERGE until remote gates clear.** |

## PR #3 Gate Snapshot (Historical Remote Read-Only State)

PR #3 (`QuantStrategyLab/FuseControl#3`) remains a draft PR whose remote `headRefOid` (`ad404ad915e101aa0ec007be3ca3ba078116d26b`) predates all local remediation commits (`31500c9..d27f51a` + this doc commit):
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

- Full unit test suite: `Ran 81 tests` OK (`pytest`: `81 passed, 9 subtests passed`), plus `check_id_set.py` PASS, `lint_spec.py` PASS, and `check_exposure_invariants.py` (`168/168` bundles) PASS.
- Nothing pushed and PR #3 untouched per demonstration protocol; exact-head remote CI remains pending push.
- Owner-approved v2 refreeze (`d27f51a`) updated only `goldens/golden-table.json`, `goldens/DERIVATION.md`, and `goldens/FREEZE.json` for R1/R4/R5; `goldens/scenarios.json` and `goldens/successor-cases.json` remain unchanged since `86be6d7`.
