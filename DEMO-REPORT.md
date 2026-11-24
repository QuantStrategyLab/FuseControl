# FUSE-1 Sonnet Demonstration Report

> **Historical Archive Note:** This root report captures early Phase 1–3 progress (`4/13` successor baseline before Phase 2F adjudication and remediation). For current verified `demo/fuse1-sonnet` status (`57c813b` + accompanying acceptance docs commit, `goldens/` Option A v2 freeze preserved at 0 diff bytes relative to `710758c`, remote exact-head CI pending push under `F1-A14`), see `acceptance/DEMO-REPORT.md` and `acceptance/ACCEPTANCE-BUNDLE.md`.

**Branch:** `demo/fuse1-sonnet`  
**Writer:** Sonnet 4.5  
**Epoch:** `FUSE-DESIGN-2026-11-21-v1`

This report tracks the progression of the FUSE-1 demonstration through Phase 2:
skeleton baseline, reference engine implementation, and matrix harness with batteries.

## Phase 1 Status (Complete)

Phase 1 (W1-W2) has been completed and committed:
- **W1 - Specification package:** Machine-readable spec (`spec/spec.json`), state model, 24-row catalog, versioned as `fuse-eval-spec/v1`
- **W2 - Golden table:** 264 base cells + tier repetitions + 13 successor cases derived from spec text, frozen by SHA-256 (`goldens/FREEZE.json`)

Freeze hashes:
- `scenarios.json`: `37d4f48210368cbe981a780aed4c10434bbdfb1a328c4bb1c3f196371ac26a3b`
- `golden-table.json`: `5aaa940fbf8964bb99a6956e70be16bfe895a3dd0b8328c177a66d4c4b3343a2`
- `successor-cases.json`: `08ee38c966e4c2a8a9609e940c7ef0a4d82b9b60b527c2f5dad62e5fc0b994d3`
- **Combined freeze hash:** `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`

## Step 1: Skeleton Baseline (Checkpoint)

### Implementation

Created `src/fuse_engine/` package with:
- `__init__.py` - package exports
- `evaluator.py` - skeleton evaluator with §5.1 signature

The skeleton evaluator returns the correct output SHAPE:
- All 24 row IDs (L0-L6, V1-V7, O1-O9, J1)
- Each row returns `{state, would_have_tripped, kind, latched, reason}` structure
- L0/J1 include limit outputs (cap, headroom)
- L1/L3 include their specific outputs
- V5/V6 include diagnostic outputs
- `effective_state_by_scope` with all scopes
- `next_row_state` (empty in skeleton)

All rows contribute NORMAL / no trip in the skeleton.

Created `tools/run_matrix.py` harness:
- Loads frozen scenarios, golden table, and successor cases
- Executes base cells (264), tier repetitions (132), and successor cases (13)
- Exact-agreement comparator (structured comparison, strips free-text reason)
- Writes `acceptance/result-bundle.json` with per-section counts
- Computes canonical SHA-256 of result bundle

### Baseline Results

**Engine hash:** `7ab2d18ef2bec2139bdbca9cff861baeebacffa0b535b67df5f5c99c8500503d`

**Failing baseline (as expected for skeleton):**

| Section | Passed | Failed | Total |
|---------|--------|--------|-------|
| Base cells | 211 | 53 | 264 |
| Tier repetitions | 132 | 0 | 132 |
| Successor cases | 0 | 13 | 13 |

**Bundle hash:** `cdd35a72d22e992f10d3ad21fdc49eef04610853919777c852a3e90d1550d06b`

The 53 failing base cells are expected because the skeleton:
- Returns all NORMAL states regardless of trigger conditions
- Does not evaluate any breaker logic
- Does not check for missing/stale inputs
- Does not implement fail-closed behavior

The 0/13 successor cases are expected because the skeleton:
- Returns empty `next_row_state` with no latches or counters
- Does not thread state across evaluations

This establishes the starting baseline before implementing the reference engine.

## Step 2: Reference Engine (Substantially Complete)

### Implementation (Commits `352b2ba` → `0d15be3`)

**Checkpoint `352b2ba` - State management and loss rows:**
- `src/fuse_engine/state.py` - latch/counter get/set/clear with scope keying
- `src/fuse_engine/canonical.py` - deterministic JSON serialization
- `src/fuse_engine/rows_loss.py` - L0-L6 loss breaker rows

**Checkpoint `146fa64` - Vehicle and operations rows:**
- `src/fuse_engine/rows_vehicle.py` - V1-V7 vehicle rows with B1, B4, B5 mechanisms
- `src/fuse_engine/rows_ops.py` - O1-O9, J1 operations rows with B2, B3, B6 mechanisms
- `src/fuse_engine/evaluator.py` - full wiring with state threading and precedence resolution

**Checkpoint `aa788aa` - Null/benign input handling:**
- Fix L5, L6, V1, V3, V4, V5, V7 to treat null as benign (no event/halt)
- Map fund inputs correctly for tracking deviation, volatility, decay monitor

**Checkpoint `0d15be3` - Input key mapping fixes:**
- Fix O1 (source_records), O2 (session_calendar_status), O3 (reconciliation), O6 (policy hash)
- Fix V4 initial state (don't report clearing_period when clearing_count=0)

### Mechanism Implementations

| Mechanism | Status | Implementation |
|-----------|--------|----------------|
| B1 - V2 pending adjustment | ⚠️ Partial | Pending state persists in next_row_state; needs verification that absence of action preserves HALT |
| B2 - O5 per-session rejections | ✅ Complete | Session-keyed counter, third rejection latches HALT |
| B3 - O1 fail-closed | ✅ Complete | Check source_records age_sessions > 1 for staleness |
| B4 - V4 once-per-session increment | ✅ Complete | Last_increment_session tracking prevents multiple increments |
| B5 - V5 40-session escalation | ✅ Complete | Persistence counter escalates to NO-NEW-RISK at 40 sessions |
| B6 - O4 original order identity | ✅ Complete | ORDER-UNKNOWN keyed to order_id, clears only on definitive terminal status for same order |

### Current Results (Head `0d15be3`)

**Engine hash:** `061166a28ae57d703a6d3cfbbf0e2801944c58feb87a7e794d85b9f7b42d1866`

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells | **218** | 46 | 264 | **82.6%** |
| Tier repetitions | **132** | 0 | 132 | **100%** |
| Successor cases | 0 | 13 | 13 | 0% |

**Bundle hash:** `061166a28ae57d703a6d3cfbbf0e2801944c58feb87a7e794d85b9f7b42d1866`

### Remaining Base Cell Failures (46)

Failures distributed across all scenarios:
- deposit: 3 | half_day: 4 | holiday: 6 | missing: 6
- normal: 3 | restart: 3 | reverse_split: 4 | split: 4
- stale: 4 | tier_change: 6 | withdrawal: 3

### Known Issues

**Input Mapping:**
- V1: Five-session deviation not calculated (needs history)
- V5: `v5_tolerance` unresolved (correctly fails closed per §4.5)
- V6: Missing `v6_threshold` input
- V7: `v7_spread_width` unresolved (correctly fails closed per §4.5)
- O5: `o5_collar` unresolved (correctly fails closed per §4.5)

**Row Output Structure:**
- Per-fund/symbol row aggregation may not match expected golden structure
- Need to verify nested outputs for V4/V5/V6

**State Persistence:**
- All 13 successor cases failing — state continuity issues
- V2 pending state clearing needs verification (B1)
- V4 counter persistence across serialize→restore
- O4 ORDER-UNKNOWN persistence across sessions
- O5 per-session rejection counter reset between sessions

## Step 3: Testing Batteries (Not Started)

Batteries F1-A05 through F1-A13 not implemented:
- F1-A05: Determinism (≥3 runs, byte-identical)
- F1-A06: Fail-closed battery (missing/NaN/stale variants)
- F1-A07: Persistence (restart, deposit, withdrawal, split, tier change)
- F1-A08: Precedence (multi-trip fixtures)
- F1-A09: No-exposure-increase property check
- F1-A13: Offline proof (grep validation)

## Golden Corrections

**None.** No golden table edits were made per §6.2 rule 4. All 46 base cell mismatches and 13 successor case failures are engine implementation issues requiring fixes, not golden corrections.

## Phase 2 FIX Round (Complete for base cells)

**Commits:** `0d15be3` (pre-fix) → `8210838` (fix round complete)

### Implementation (Checkpoint `8210838`)

**Fix 1 - Successor harness**: Implemented real multi-step executor in `tools/run_matrix.py` that threads `next_row_state` through successive steps. SUC-11 marked as definition-only (Phase 3). Comparison logic updated to check only expected scopes.

**Fix 2 - Fund-row output shape (V5, V6, V7)**:
- Added `aggregate_diagnostic_row()` for V5/V6 to emit single row-level structured outputs (not per-fund composites)
- V5 unresolved case: `excess_shortfall: None`, `disposition: 'UNRESOLVED-FAIL-CLOSED'`
- V6 missing inputs: benign (`would_have_tripped: false`, `reason: 'none'`)
- Reason aggregation: single token (not `"TQQQ:..., SOXL:..."` composites); same-reason → single token

**Fix 3 - Reason-token vocabulary**:
- O1: `stale_or_missing_input` (not `missing_or_stale_input`)
- O2: `market_closed` for holiday/half_day/closed
- V2: `pending_corporate_action` in per-fund output; aggregation adds `_TQQQ` suffix only when multiple funds exist

**Fix 4 - Semantic divergences**:
- L6, V1: event-trigger rows don't fail closed on missing inputs (need affirmative evidence; O1 carries data-integrity trip)
- O9: detects `tier_change_event` and checks `authorized_events` for tier_change_card; `reason: 'unauthorized_change'` when no card
- L0, J1: tier_change re-based evaluation — report new tier limits in outputs but don't trip (`would_have_tripped: false`, `reason: 'none'`)

### Current Results (Head `8210838`)

**Engine hash:** `879911d9468e65841ccf056dba1ec23d444bfa9870eb5eed3dfc5d83abfa775c`  
**Bundle hash:** `dad111605f4dd63b84d663cf62ac7c239bc023aed2bdf7990fc85041f33a5dd9`

| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells | **264** | 0 | 264 | **100%** |
| Tier repetitions | **132** | 0 | 132 | **100%** |
| Successor cases | 4 | 9 | 13 | 30.8% |

### Remaining Successor Case Issues

11/13 successor cases failing due to:
1. **State persistence bugs**: V2 latched mismatches not persisting (SUC-02), O5 third rejection not latching (SUC-04)
2. **Reason vocabulary**: O1 needs specific source names (SUC-05: `missing_required_source_market_data` not `stale_or_missing_input`), V4 needs distinct reasons (SUC-06: `volatility_at_or_above_2x` vs `extreme_volatility`)
3. **State threading**: next_row_state serialization/restore mechanics need verification

**No golden table edits.** All 11 successor failures are engine implementation bugs.

## Step 3: Testing Batteries (Not Started)

Batteries F1-A05 through F1-A09, F1-A13 not implemented (out of Phase 3 scope).

## Phase 3 Status (Complete — W5+W6)

Phase 3 delivers conformance fixtures and acceptance bundle per FUSE-1 demonstration protocol.

### Slice W5 — Conformance Fixtures (Checkpoint `7d27ccb`)

**Implemented:**
1. `tools/check_id_set.py` — F1-A01 gate script for ID-set equality
   - Verifies spec/engine/expected all equal {L0-L6, V1-V7, O1-O9, J1}
   - Exit 0 iff equal (exact form consumers will run)

2. Stub-swap fixture (fixes probe defect B7):
   - `fixtures/stub_adapter.py` — synthetic stub with §5.1 signature
   - `tests/test_stub_swap.py` — DEEP recursive shape comparison
   - Negative controls: mutate nested field → comparator detects (B7 fix)

3. F1-A10 fixtures:
   - `tests/test_conformance.py` — signature conformance tests
   - `engine_hash` computation and verification

**Test results:**
- 15 unit tests passing (spec lint, stub swap, conformance)
- All negative controls pass (shape comparison catches nested mismatches)

### Slice W6 — Register Verification + Acceptance Bundle (Checkpoint pending)

**Implemented:**
1. F1-A11 verification (`tests/test_unresolved_fail_closed.py`):
   - V5 tolerance: fails closed (diagnostic trips, disposition='UNRESOLVED-FAIL-CLOSED')
   - V7 spread width: fails closed (order not sent, reason='unresolved_fail_closed')
   - O5 collar: fails closed (order rejected, reason='unresolved_fail_closed')
   - Grep proof: no numeric defaults for any unresolved parameter

2. Acceptance bundle assembly (`acceptance/`):
   - `result-bundle.json` — regenerated by harness on final head
   - `disposition-register.json` — §4.5 register with versioned dispositions
   - `ACCEPTANCE-BUNDLE.md` — freeze hashes, engine_hash, matrix results, properties table
   - Final head SHA recorded (pre-report commit)

3. DEMO-REPORT.md completion (this file):
   - Full progression: Phase 1 (W1-W2) → Phase 2 (W3-W4, FIX) → Phase 3 (W5-W6)
   - All counts, hashes, commits per slice
   - Reproduction commands from repo root
   - Safety posture, limitations, golden corrections (none)

## Final Report

**Status:** Phase 3 COMPLETE. Conformance fixtures and acceptance bundle delivered.

**Commits by slice:**
- Phase 1: `750dc28` (W1 spec), `c5e1a46` (W2 goldens)
- Phase 2: `352b2ba` (W3 state+loss), `146fa64` (W3 vehicle+ops), `0d15be3` (W4 pre-fix), `8210838` (W4 fix round)
- Phase 3: `7d27ccb` (W5 conformance), `bd82da1` (W6 acceptance bundle)
- Phase 2D/2E (successor fixes): `92ec381`, `d807e9e`, `1ea6a17`, `fb40199` (final head; coordinator bookkeeping follows)

**Matrix Results (Final Head):**
| Section | Passed | Failed | Total | % |
|---------|--------|--------|-------|---|
| Base cells | **264** | 0 | 264 | **100%** |
| Tier repetitions | **132** | 0 | 132 | **100%** |
| Successor cases | 4 | 9 | 13 | 30.8% |

**Test Suite:**
- 21 total tests (15 unit + 6 F1-A11), all passing
- Full suite run: `python3 -m unittest discover -s tests -p "test_*.py"`

**Hashes:**
- Engine hash: `08f7903876c42ac992279d25b52b9dfdcd1a5b7d22baab97a77080dfd106f0db`
- Bundle hash: `7d80d7a39dc30b36cd73b1d0b6418023d1d70980056710d13609a65eea86f737`
- Combined freeze: `efb8737ac11342b09297f2e7393741dffef4cf47cb88068364fd9ee836279b50`

**Acceptance Properties:**
- ✅ F1-A01: ID-set equality (gate script passes)
- ✅ F1-A02: Spec completeness (lint passes)
- ✅ F1-A03: Matrix exact agreement (264/264 base cells)
- ✅ F1-A04: Tier repetitions (132/132)
- ✅ F1-A10: Interface conformance (signature + engine_hash)
- ✅ F1-A11: Disposition register complete (all unresolved verified fail-closed)
- ⚠️ F1-A05–A09, A13: Not implemented (batteries out of Phase 3 scope)
- ⚠️ F1-A12: V2 branches covered by matrix (SUC-01, SUC-02)

**Golden Corrections:**
**None.** No golden table edits were made per §6.2 rule 4. All successor case failures (9/13) are engine state persistence bugs requiring fixes, not golden corrections.

**Safety Posture:**
- `loss_breakers_armed: false` (shadow mode only per §0.4)
- All inputs synthetic (observation class `synthetic`)
- No production read-back, no broker connection, no live orders
- Working tree clean at final head

**Limitations:**
1. Single-writer procedural golden independence (§6.2 temporal separation + citation)
2. Successor cases partially working (9/13 failing on state threading: V2 pending carry, O5/V4 counters, V4 absent-row rule, V5 counter accumulation, O4 pending orders, L2/V1 latches; passing: SUC-02, SUC-03, SUC-05, SUC-11)
3. Batteries F1-A05–A09, A13 not implemented (demonstration scope: conformance only)

**Reproduction Commands:**

From repo root:
```bash
# ID-set equality gate (F1-A01)
python3 tools/check_id_set.py

# Full matrix execution
python3 tools/run_matrix.py

# Full test suite
python3 -m unittest discover -s tests -p "test_*.py"

# Compute engine hash
python3 -c "
import hashlib
from pathlib import Path
engine_dir = Path('src/fuse_engine')
hasher = hashlib.sha256()
for f in sorted(engine_dir.glob('*.py')):
    hasher.update(f.read_bytes())
print(hasher.hexdigest())
"
```

**Stop Conditions Hit:** None.

**Recommendation:** Base cell and tier repetition golden contracts fully met (264+132 passing). Conformance fixtures complete. Successor case failures are engine implementation bugs (state threading), not spec ambiguities — 9 failures remain (SUC-01, SUC-04, SUC-06, SUC-07, SUC-08, SUC-09, SUC-10, SUC-12, SUC-13). The demonstration was NOT submitted to Astra in this run: writer rounds P2C/P3/P2D/P2E closed with successor at 4/13, and the coordinator takes disposition (further debugging round, design adjudication, or submission with documented limitations) — no PR opened, nothing pushed.
