#!/usr/bin/env python3
"""F1-A02 spec linter: verifies completeness of FUSE-1 breaker specification.

Checks:
1. All 24 IDs present exactly once: L0-L6, V1-V7, O1-O9, J1
2. Every row has non-empty required fields:
   - trigger
   - required_inputs (list)
   - action
   - kind
   - scope
   - clearing

Exit 0 on pass, non-zero on failure.
"""

import json
import sys
from pathlib import Path


EXPECTED_IDS = {
    "L0", "L1", "L2", "L3", "L4", "L5", "L6",
    "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8", "O9",
    "J1"
}

REQUIRED_FIELDS = ["trigger", "required_inputs", "action", "kind", "scope", "clearing"]


def lint_spec(spec_path: Path) -> tuple[bool, list[str]]:
    """Lint the specification file.

    Returns:
        (success, errors): success is True if all checks pass, errors is list of error messages
    """
    errors = []

    # Load spec
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = json.load(f)
    except Exception as e:
        return False, [f"Failed to load spec: {e}"]

    # Check rows exist
    if "rows" not in spec:
        return False, ["Spec missing 'rows' field"]

    rows = spec["rows"]
    if not isinstance(rows, list):
        return False, ["'rows' must be a list"]

    # Extract IDs
    found_ids = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"Row {i} is not a dictionary")
            continue

        if "id" not in row:
            errors.append(f"Row {i} missing 'id' field")
            continue

        found_ids.append(row["id"])

    # Check ID set equality
    found_id_set = set(found_ids)
    if found_id_set != EXPECTED_IDS:
        missing = EXPECTED_IDS - found_id_set
        extra = found_id_set - EXPECTED_IDS
        if missing:
            errors.append(f"Missing IDs: {sorted(missing)}")
        if extra:
            errors.append(f"Extra IDs: {sorted(extra)}")

    # Check for duplicates
    if len(found_ids) != len(found_id_set):
        from collections import Counter
        counts = Counter(found_ids)
        duplicates = [id for id, count in counts.items() if count > 1]
        errors.append(f"Duplicate IDs: {sorted(duplicates)}")

    # Check each row has all required fields non-empty
    for row in rows:
        if not isinstance(row, dict) or "id" not in row:
            continue

        row_id = row["id"]

        for field in REQUIRED_FIELDS:
            if field not in row:
                errors.append(f"{row_id}: missing field '{field}'")
            elif not row[field]:
                # Empty string, empty list, None, etc.
                errors.append(f"{row_id}: field '{field}' is empty")
            elif field == "required_inputs" and not isinstance(row[field], list):
                errors.append(f"{row_id}: field '{field}' must be a list")

    return len(errors) == 0, errors


def main():
    if len(sys.argv) > 1:
        spec_path = Path(sys.argv[1])
    else:
        # Default path relative to repo root
        repo_root = Path(__file__).parent.parent
        spec_path = repo_root / "spec" / "spec.json"

    if not spec_path.exists():
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    success, errors = lint_spec(spec_path)

    if success:
        print(f"PASS: {spec_path}")
        print(f"All 24 IDs present, all required fields non-empty")
        sys.exit(0)
    else:
        print(f"FAIL: {spec_path}", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
