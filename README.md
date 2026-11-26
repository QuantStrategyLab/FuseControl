# FuseControl

FUSE breaker specification and reference engine for QuantStrategyLab (batch FUSE-1).

## What this repository is

This repository holds the FUSE-1 deliverables for the QuantStrategyLab shadow
programme:

- the specification of the 24 named breakers (L0–L6, V1–V7, O1–O9, J1), each
  with its trigger, action, kind, and clearing semantics;
- the frozen golden matrix (24 breakers × 11 scenarios = 264 cells, with
  independently derived expected outcomes and tier repetitions), hash-frozen
  before any full engine run;
- the reference engine implementing the pinned evaluator interface, consumed
  downstream as a digest-pinned, read-only package.

FUSE-1 is a high-track safety component. The SH-2 stage of the shadow
programme consumes only an *accepted* FUSE-1 engine, and pins the engine's
content hash in every consumer record; the acceptance predicate includes
breaker ID-set equality, not a row count.

## Status

Design demonstration in progress.

A probe demonstration built by Orchestrator Neon exists on branch
`demo/fuse1-neon-probe`. It is **evidence only — it was not accepted**. The
probe passed its frozen matrix exactly (264/264 cells, 42/42 tier
repetitions), but the independent Astra re-verification failed it on
cross-step state-continuity findings (counter, latch, and persistence
behaviour across successive evaluations), none of which a single-step matrix
cell can reach. The accepted demonstration will be built by the pinned
Sonnet writer under the FUSE-1 brief, with successor-state continuity cases
frozen into the acceptance battery before implementation.

## Pre-trade session gate (C-FUSE-GATE)

`src/fuse_gate/` sits in front of the engine. From a timestamp and a published
XNYS calendar it derives `V7` `session_time` and the `O2` calendar status. The
`O2` exchange status must be observed separately from the venue; it can only
veto, so an observed closure blocks orders even on a scheduled trading day.
`apply_gate_decision` writes these values into every engine input that `V7` and
`O2` read. Orders are eligible only inside the core regular
session (09:30–16:00 ET, 13:00 ET on half days). Pre-market, after-hours, the
20:00–21:00 ET maintenance pause and the US 23/5 overnight window (21:00–04:00
ET, from 2026-12-06) never are. Activity from 21:00 ET is attributed to the next
trading day. Calendar files are accepted only when their SHA-256 matches a pin
in `PINNED_CALENDARS`, and dates outside a pinned calendar fail closed. The
gate does not modify the digest-pinned engine package.

## Coordination note

This repository carries active, coordinated work (coordinator: Muse).
**Do not delete or archive it.** Its apparently small footprint is
deliberate: work state for this lane is kept visible here — branches,
records, and this status note — precisely so that its active state can be
seen from the repository itself.

## Safety posture

Live trading, Kelly sizing, and stop-loss arming are OFF system-wide. In
this batch the breakers are computed and recorded only
(`loss_breakers_armed: false`); nothing in this repository places orders or
arms a trading path.
