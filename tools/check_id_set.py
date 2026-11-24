#!/usr/bin/env python3
"""F1-A01: ID-set equality gate script.

Machine-compares the ID set emitted by the engine and named in spec.json
against exactly {L0-L6, V1-V7, O1-O9, J1} as sets. Exit 0 iff equal.

This is the exact gate script consumers (SH-2/PILOT) will run before taking
FUSE-1 evidence (per adjudication Blocking item 2, §8 F1-A01).
"""

import json
import sys
from pathlib import Path


# The 24 named row IDs per §4.3
EXPECTED_IDS = {
    "L0", "L1", "L2", "L3", "L4", "L5", "L6",
    "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8", "O9",
    "J1"
}


def check_id_set(spec_path: Path, engine_module_path: Path) -> tuple[bool, str]:
    """Check that spec and engine emit exactly the 24 expected IDs.

    Args:
        spec_path: Path to spec/spec.json
        engine_module_path: Path to src/fuse_engine directory

    Returns:
        (success, message) tuple
    """
    # Load spec.json and extract row IDs
    with open(spec_path, 'r') as f:
        spec = json.load(f)

    spec_ids = {row['id'] for row in spec.get('rows', [])}

    # Import engine and check its declared ROW_IDS
    sys.path.insert(0, str(engine_module_path.parent))
    from fuse_engine.evaluator import ROW_IDS

    engine_ids = set(ROW_IDS)

    # Check all three sets match exactly
    if spec_ids == EXPECTED_IDS and engine_ids == EXPECTED_IDS:
        return True, f"✓ ID set equality: spec={len(spec_ids)}, engine={len(engine_ids)}, expected={len(EXPECTED_IDS)}"

    # Build detailed error message
    errors = []
    if spec_ids != EXPECTED_IDS:
        missing = EXPECTED_IDS - spec_ids
        extra = spec_ids - EXPECTED_IDS
        if missing:
            errors.append(f"  Spec missing: {sorted(missing)}")
        if extra:
            errors.append(f"  Spec extra: {sorted(extra)}")

    if engine_ids != EXPECTED_IDS:
        missing = EXPECTED_IDS - engine_ids
        extra = engine_ids - EXPECTED_IDS
        if missing:
            errors.append(f"  Engine missing: {sorted(missing)}")
        if extra:
            errors.append(f"  Engine extra: {sorted(extra)}")

    return False, "✗ ID set mismatch:\n" + "\n".join(errors)


def main():
    """Run ID-set equality check and exit with status code."""
    repo_root = Path(__file__).parent.parent
    spec_path = repo_root / "spec" / "spec.json"
    engine_path = repo_root / "src" / "fuse_engine"

    success, message = check_id_set(spec_path, engine_path)
    print(message)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
