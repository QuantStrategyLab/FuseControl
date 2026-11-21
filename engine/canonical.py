"""Pure canonical JSON serialization and SHA-256 helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize obj to canonical JSON string (sorted keys, compact separators, ASCII)."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_bytes(obj: Any) -> bytes:
    """Encode canonical JSON representation of obj as UTF-8 bytes."""
    return canonical_json(obj).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Return lowercase hex SHA-256 digest of UTF-8 encoded text."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_canonical(obj: Any) -> str:
    """Return lowercase hex SHA-256 digest of canonical JSON bytes for obj."""
    return sha256_bytes(canonical_bytes(obj))
