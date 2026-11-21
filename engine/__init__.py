"""FUSE-1 reference engine package."""

from engine.canonical import (
    canonical_bytes,
    canonical_json,
    sha256_bytes,
    sha256_canonical,
    sha256_text,
)
from engine.evaluate import EvaluationResult, evaluate, wrap_outputs
from engine.rows import ROW_IDS

__all__ = [
    "EvaluationResult",
    "ROW_IDS",
    "canonical_bytes",
    "canonical_json",
    "evaluate",
    "sha256_bytes",
    "sha256_canonical",
    "sha256_text",
    "wrap_outputs",
]
