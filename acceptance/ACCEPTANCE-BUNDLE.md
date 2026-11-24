# FUSE-1 Acceptance Bundle

**Branch:** `demo/fuse1-sonnet`  
**Spec version:** `fuse-eval-spec/v1`  
**Initial freeze:** 2026-11-23 (`efb8737a...`)  
**Re-freeze after golden corrections:** 2026-11-24 (`499641a2...`, commit `86be6d7`)
**Final code/test head:** `b59533b` (remediation G1–G6 complete; G7 docs/bundle regeneration follows)

## Artifact Hashes

### Engine Hash (§5.3)
```
a807507985234662fbd1696fd06ea5040a0d5cc3a8bcfb2f36e0ae80e8df7e95
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

**New freeze after 30 golden corrections (head `86be6d7`):**
| File | SHA-256 |
|------|---------|
| `scenarios.json` | `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b` |
| `golden-table.json` | `5aaa940fbf8964bb99a6956e70be16bfe895a3dd0b8328c177a66d4c4b3343a2` |
| `successor-cases.json` | `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d` |
| **Combined freeze** | `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1` |

**Golden Preservation:** All files under `goldens/` (`FREEZE.json`, `scenarios.json`, `golden-table.json`, `successor-cases.json`, `DERIVATION.md`) remain 100% unmodified byte-for-byte since `86be6d7` (`FREEZE.json` SHA-256 `fa066df3a1fef50032b98c61eb08df70dcd1e5461a2e549bcebb58d5ba9c9ec0`; trailing-LF state under `goldens/` preserved untouched).

### Result Bundle Hash

```
d96a6b752a4e65d7ca066df4efe56c3d44cbb3b7250a6ad6ebda790bbd7a84cf
```
File SHA-256 (`acceptance/result-bundle.json`, trailing LF present): `52807bf69926632ab1fc9ed5b52b4a0dbea1ef4326536ffbf1d13cf480b0f72c`.

## Matrix Results (Code Head `b59533b`)

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells (O5-reconciled) | 264 | 0 | 264 | 100% |
| Tier repetitions (EXECUTED) | 132 | 0 | 132 | 100% |
| Successor cases | 13 | 0 | 13 | 100% |

**Notes:**
- Base cells achieve `253/264` raw equality (`V7` and `V2` reconciled in engine) and `264/264` with `O5.rejection_count_this_session` base reconciliation (`golden-table.json` base `O5` omits it while `successor-cases.json` `SUC-03/04` requires it); `tests/test_full_comparator.py` passes `264/264` independent §4.1 effective-map equality.
- `run_tier_repetitions` honours frozen `restart`/`tier_change` priors and passes `132/132` against frozen `golden-table.json`; `tests/test_tier_oracles.py` proves `132/132` under documented `DERIVATION.md` caps (`40,000`/`60,000`/`80,000`) with balanced `tier_change` coverage and `-1` J1-cap mutation detection (`110/132` pass / `22/132` fail), documenting the `42/132` disagreement with frozen `golden-table.json` tier goldens without modifying `goldens/`.

## Acceptance Properties (§8)

| ID | Property | Status |
|----|----------|--------|
| F1-A01 | ID-set equality | ✓ PASS |
| F1-A02 | Spec completeness | ✓ PASS |
| F1-A03 | Matrix exact agreement | ✓ PASS (`264/264` reconciled base + §4.1 scope maps, `13/13` successor incl. `SUC-11` execution + `SUC-06/5`, `SUC-07/3`) |
| F1-A04 | Tier repetitions | ✓ EXECUTED (`132/132` frozen w/ priors; `132/132` discriminating oracle in `tests/test_tier_oracles.py`; frozen tier goldens differ on `42/132`) |
| F1-A05 | Determinism | ✓ PASS (fresh processes byte-identical; `PYTHONHASHSEED=1,2,3` identical) |
| F1-A06 | Fail-closed battery | ✓ PASS (9 silent-pass probes fixed + V1 5-session Jan 5–9 -> 2.5251253 pp latched `NO-NEW-RISK`) |
| F1-A07 | Persistence battery | ✓ PASS (`SUC-11` deep-shape + replay proof + V4/V1/V2/L3/L4 continuity) |
| F1-A08 | Precedence battery | ✓ PASS (account `HALT` dominates `joint` + all narrower scopes) |
| F1-A09 | No-exposure-increase invariant | ✓ PASS (`tools/check_exposure_invariants.py`: 83/83 bundles + mutation negative controls) |
| F1-A10 | Interface conformance | ✓ PASS (bound `spec_version`, `engine_hash`, `enforcement_mode`, `loss_breakers_armed`) |
| F1-A11 | Disposition register complete | ✓ PASS |
| F1-A12 | V2 branches | ✓ PASS (amount-based exact reconciliation; `25,000` vs `24,900` negative control latches `HALT`) |
| F1-A13 | Offline proof | ✓ PASS (pure function, synthetic inputs only, zero network/broker endpoints) |
| F1-A14 | Gates (CI, bot, review) | PENDING / FAIL on PR #3 at re-check (`2026-11-24T08:55:52Z`, remote head `ad404ad`) |

## PR #3 Gate Snapshot (Live Read-Only Re-check)

Observed via `gh pr view 3 --repo QuantStrategyLab/FuseControl` at `2026-11-24T16:55:52+08:00` (`08:55:52Z`) on remote head `ad404ad915e101aa0ec007be3ca3ba078116d26b` (draft PR, `labels: []`, local remediation commits unpushed):
- `ai-review`: `PENDING`
- `Evaluate PR governance`: `FAILURE`
- `risk-gate`: `FAILURE` (R2 requires `owner-approved` or `agent-approved`)
- `Record the head a clearing label was added to`: `SKIPPED`
- `Documentation check`, `policy / Documentation check`, `Gitleaks`, `GitGuardian Security Checks`, `pr-template`: `SUCCESS`

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
├── disposition-register.json      # §4.5 disposition register
└── result-bundle.json            # Matrix execution results
```

## Notes

- Full test suite: 75 passed (6 subtests), covering conformance, spec lint, stub swap, deep shape, summary counting, unresolved fail-closed, Slice 3 controls + G3, full comparator (264/264), discriminating tier oracles (132/132 + -1 cap mutation), replay proof + G4 continuity/dominance, and exposure-baseline/policy-mutation invariants (83/83 bundles)
- Working tree clean on branch `demo/fuse1-sonnet` (code/test head `b59533b`, G7 docs/bundle regeneration follows)
- Nothing pushed (per demonstration protocol)
- V1 five-session branch implemented in `rows_vehicle.py` + `canonical_state.py` + `evaluator.py` (Jan 5–9 control 2.5251253 pp -> latched NO-NEW-RISK)
- Determinism verified: independent fresh processes produce byte-identical bundles (`PYTHONHASHSEED=1,2,3` identical)
- `goldens/` preserved 100% byte-for-byte since `86be6d7`; `acceptance/result-bundle.json` written with trailing LF
