"""FUSE-1 reference engine package.

This package implements the pinned evaluator interface (BRIEF-FUSE-1 §5.1):

    evaluate(spec_version, engine_hash, policy_hash, session, as_of, mode,
             validated_inputs, prior_row_state, authorized_events)
    -> (rows_by_ID, effective_state_by_scope, next_row_state)

The engine is a pure function: no I/O, no wall-clock, no randomness, no environment reads.
Identical inputs produce byte-identical outputs under canonical serialization.

Row modules:
- rows_loss.py: L0-L6 (Loss rows)
- rows_vehicle.py: V1-V7 (Vehicle rows)
- rows_ops.py: O1-O9, J1 (Data/operations rows)
"""

from .evaluator import evaluate

__all__ = ['evaluate']
__version__ = 'fuse-eval-spec/v1'
