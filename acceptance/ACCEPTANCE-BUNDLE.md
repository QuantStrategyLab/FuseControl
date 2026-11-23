# FUSE-1 Acceptance Bundle

**Branch:** `demo/fuse1-sonnet`  
**Spec version:** `fuse-eval-spec/v1`  
**Frozen at:** 2026-11-23  
**Final head (pre-report):** `fb40199986a8a2830afaa63d5bd45b0520044edc`

## Artifact Hashes

### Engine Hash (§5.3)
```
08f7903876c42ac992279d25b52b9dfdcd1a5b7d22baab97a77080dfd106f0db
```

Computed from canonical bundle:
```
src/fuse_engine/__init__.py
src/fuse_engine/canonical.py
src/fuse_engine/evaluator.py
src/fuse_engine/rows_loss.py
src/fuse_engine/rows_ops.py
src/fuse_engine/rows_vehicle.py
src/fuse_engine/state.py
```

### Golden Table Freeze Hashes (§6.2)

| File | SHA-256 |
|------|---------|
| `scenarios.json` | `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b` |
| `golden-table.json` | `5aaa940fbf8964bb99a6956e70be16bfe895a3dd0b8328c177a66d4c4b3343a2` |
| `successor-cases.json` | `08ee38c966e4c2a8a9609e940c7ef0a4d82b9b60b527c2f5dad62e5fc0b994d3` |
| **Combined freeze** | `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50` |

### Result Bundle Hash

```
7d80d7a39dc30b36cd73b1d0b6418023d1d70980056710d13609a65eea86f737
```

## Matrix Results (Final Head)

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells | 264 | 0 | 264 | 100% |
| Tier repetitions | 132 | 0 | 132 | 100% |
| Successor cases | 4 | 9 | 13 | 30.8% |

**Note:** Successor cases partially working — SUC-02, SUC-03, SUC-05, SUC-11 pass; 9 cases remain failing on state-threading mechanisms (V2 pending carry, O5/V4 counters, V4 absent-row rule, V5 counter accumulation, O4 pending orders, L2/V1 latches). Coordinator bookkeeping on final head `fb40199`; demonstration NOT submitted to Astra in this run.

## Acceptance Properties (§8)

| ID | Property | Status |
|----|----------|--------|
| F1-A01 | ID-set equality | ✓ PASS |
| F1-A02 | Spec completeness | ✓ PASS |
| F1-A03 | Matrix exact agreement (264/264 base cells) | ✓ PASS |
| F1-A04 | Tier repetitions (132/132) | ✓ PASS |
| F1-A05 | Determinism | Not tested |
| F1-A06 | Fail-closed battery | Not tested |
| F1-A07 | Persistence battery | Not tested |
| F1-A08 | Precedence battery | Not tested |
| F1-A09 | No-exposure-increase invariant | Not tested |
| F1-A10 | Interface conformance | ✓ PASS |
| F1-A11 | Disposition register complete | ✓ PASS |
| F1-A12 | V2 branches | Covered by matrix |
| F1-A13 | Offline proof | Not tested |
| F1-A14 | Gates (CI, bot, Astra) | Deferred to coordinator |

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

- Full test suite: 21 tests (15 unit + 6 F1-A11), all passing
- Working tree clean at commit `7d27ccb`
- Nothing pushed (per demonstration protocol)
- Successor case failures are engine state bugs, not spec ambiguities
- Batteries F1-A05 through F1-A09, F1-A13 not implemented (Phase 3 scope: conformance only)
