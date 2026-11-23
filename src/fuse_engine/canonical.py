"""Canonical serialization for FUSE-1 reference engine.

Per §5.2 and §5.3: identical inputs produce byte-identical outputs under
canonical JSON serialization (sorted keys, compact separators, no trailing whitespace).
"""

import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize object to canonical JSON format.

    Uses sorted keys and compact separators for deterministic serialization.
    Per §5.2: identical inputs must produce byte-identical canonical JSON.
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def canonical_hash_input(obj: Any) -> bytes:
    """Convert object to bytes for hashing via canonical JSON."""
    return canonical_json(obj).encode('utf-8')
