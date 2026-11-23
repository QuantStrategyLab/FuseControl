# FUSE-1 Sonnet Demonstration Report

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

## Step 2: Reference Engine (In Progress)

Status: Not started

## Step 3: Testing Batteries (Not Started)

Status: Not started

## Final Report

Status: Phase 2 in progress
