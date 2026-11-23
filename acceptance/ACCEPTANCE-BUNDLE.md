# FUSE-1 Acceptance Bundle

**Branch:** `demo/fuse1-sonnet`  
**Spec version:** `fuse-eval-spec/v1`  
**Initial freeze:** 2026-11-23 (`efb8737a...`)  
**Re-freeze after golden corrections:** 2026-11-24 (`499641a2...`)  
**Final head:** `39f85f9` (Slice 4(c) complete)

## Artifact Hashes

### Engine Hash (§5.3)
```
a79a6ca3eb63276d025ae29d9c659df4f1b81b552f75ad43caa122062456ca6a
```

Computed from canonical bundle:
```
src/fuse_engine/__init__.py
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

**New freeze after 30 golden corrections (head `59f1b4a`):**
| File | SHA-256 |
|------|---------|
| `scenarios.json` | `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b` |
| `golden-table.json` | `5aaa940fbf8964bb99a6956e70be16bfe895a3dd0b8328c177a66d4c4b3343a2` |
| `successor-cases.json` | `19fbb0d1ecc023740ab81d3bb5035a2fae96c8889b7b11e7099e270a20d8d12d` |
| **Combined freeze** | `499641a2185131bccc49f93c1784eab3fd226336d6ac0edc66a1d983df1d89f1` |

### Result Bundle Hash

```
44b73d60fe5ae331c4b78255b897f4269a91b66191dba9db8295fb72a9ba1a06
```

## Matrix Results (Final Head)

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells | 264 | 0 | 264 | 100% |
| Tier repetitions (EXECUTED) | 132 | 0 | 132 | 100% |
| Successor cases | 13 | 0 | 13 | 100% |

**Note:** All successor cases passing after design adjudication corrections (30 golden fixes), canonical state migration (Q6), O4 wiring, fail-closed inputs (Q5), account dominance (Q5), and Q4 re-arm short-circuit. Tier repetitions EXECUTED by real parameterized runner (Slice 4a). Demonstration ready for review.

## Acceptance Properties (§8)

| ID | Property | Status |
|----|----------|--------|
| F1-A01 | ID-set equality | ✓ PASS |
| F1-A02 | Spec completeness | ✓ PASS |
| F1-A03 | Matrix exact agreement (264/264 base cells, 13/13 successor) | ✓ PASS |
| F1-A04 | Tier repetitions (132/132 EXECUTED) | ✓ PASS |
| F1-A05 | Determinism (6 runs, byte-identical bundles) | ✓ PASS |
| F1-A06 | Fail-closed battery (Slice 3 controls) | ✓ PASS |
| F1-A07 | Persistence battery (deep-shape + replay proof) | ✓ PASS |
| F1-A08 | Precedence battery (Slice 3 controls) | ✓ PASS |
| F1-A09 | No-exposure-increase invariant | Covered by matrix |
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

- Full test suite: 46 tests (34 original + 10 Slice 3 + 5 Slice 4d + 7 Slice 4c), all passing
- Working tree clean at commit `39f85f9`
- Nothing pushed (per demonstration protocol)
- V1 five-session branch hardwired to `None` (coverage gap noted for full implementation)
- Determinism verified: 6 fresh processes, byte-identical result bundles
- Real tier runner implemented (Slice 4a): 132/132 tier repetitions EXECUTED, not stub credits
